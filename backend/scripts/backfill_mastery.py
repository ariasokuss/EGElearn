"""Backfill evidence_events from existing TestSessions and FeynmanSessions.

Run inside the backend container:
    python scripts/backfill_mastery.py
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def backfill():
    from src.core.db import create_engine, create_session_factory
    from src.core import model_registry  # noqa: F401 — registers all models with SQLAlchemy
    from src.config import get_settings
    from src.learning.models import FeynmanSession
    from src.learning.tests.models import SessionAnswer, TestSession
    from src.mastery.models import EvidenceEvent
    from src.mastery.service import (
        get_quality_weight,
        compute_mastery_from_events,
    )
    from src.mastery.stars import evaluate_stars, sync_stars_to_progress
    from src.roadmap.models import RoadmapNode, RoadmapProgress

    settings = get_settings()
    engine = create_engine(settings.postgres)
    sf = create_session_factory(engine)

    async with sf() as db:
        # ── Clear existing evidence events (idempotent backfill) ──
        await db.execute(EvidenceEvent.__table__.delete())
        logger.info("Cleared existing evidence events")

        # ── Build lesson_id → node_id map ──
        nodes = list(
            await db.scalars(
                select(RoadmapNode).where(
                    RoadmapNode.level == 3, RoadmapNode.lesson_id.isnot(None)
                )
            )
        )
        lesson_to_node: dict[uuid.UUID, uuid.UUID] = {n.lesson_id: n.id for n in nodes}
        logger.info("Found %d lesson→node mappings", len(lesson_to_node))

        events_created = 0

        # ── Backfill from graded test sessions ──
        test_sessions = list(
            await db.scalars(
                select(TestSession)
                .where(TestSession.status == "graded")
                .options(
                    selectinload(TestSession.answers).selectinload(
                        SessionAnswer.question
                    ),
                    selectinload(TestSession.template),
                )
            )
        )
        logger.info("Processing %d graded test sessions", len(test_sessions))

        for ts in test_sessions:
            template = ts.template

            # Determine source type
            type_map = {
                "inline_quiz": lambda qt: (
                    "inline_mcq" if qt == "mcq" else "inline_short"
                ),
                "lesson_test": lambda qt: "lesson_test",
                "practice_questions": lambda qt: "standalone_test",
                "past_paper": lambda qt: "past_paper",
            }
            get_src = type_map.get(template.type, lambda qt: "lesson_test")

            # Resolve node_ids: from template directly, or from lesson
            template_node_ids = template.node_ids or []
            if not template_node_ids and template.lesson_id:
                nid = lesson_to_node.get(template.lesson_id)
                if nid:
                    template_node_ids = [nid]

            if not template_node_ids:
                continue

            for ans in ts.answers:
                q = ans.question
                source_type = get_src(q.type)
                if q.type == "mcq":
                    score = 1.0 if ans.is_correct else 0.0
                else:
                    score = (
                        (ans.earned_marks / q.points)
                        if q.points and ans.earned_marks is not None
                        else 0.0
                    )

                # Use per-question node_ids if available, else template-level
                q_node_ids = q.node_ids or template_node_ids

                for node_id in q_node_ids:
                    ev = EvidenceEvent(
                        user_id=ts.user_id,
                        node_id=node_id,
                        item_id=q.item_id or f"q_{q.id}",
                        source_type=source_type,
                        source_id=template.id,
                        attempt_id=ts.id,
                        attempt_number=1,
                        score=score,
                        quality_weight=get_quality_weight(source_type),
                        repeat_discount=1.0,
                        timestamp=ans.graded_at
                        or ans.answered_at
                        or ts.graded_at
                        or datetime.now(timezone.utc),
                    )
                    db.add(ev)
                    events_created += 1

        # ── Backfill from feynman sessions ──
        # Strategy B: only keep the LATEST session per (user, feynman_block, type).
        # Previous sessions are invalidated. Latest gets attempt=1, discount=1.0.
        feynman_sessions = list(
            await db.scalars(
                select(FeynmanSession)
                .where(FeynmanSession.status.in_(["completed", "aborted"]))
                .options(selectinload(FeynmanSession.feynman_block))
                .order_by(FeynmanSession.created_at.desc())
            )
        )
        logger.info("Processing %d feynman sessions", len(feynman_sessions))

        # Dedupe: keep only the latest session per (user_id, feynman_block_id, type)
        seen_keys: set[tuple] = set()
        latest_sessions: list = []
        for fs in feynman_sessions:
            key = (fs.user_id, fs.feynman_block_id, fs.type)
            if key not in seen_keys:
                seen_keys.add(key)
                latest_sessions.append(fs)

        logger.info("Keeping %d latest feynman sessions (deduped)", len(latest_sessions))

        for fs in latest_sessions:
            block = fs.feynman_block
            if not block:
                continue
            node_id = lesson_to_node.get(block.lesson_id)
            if not node_id:
                continue

            source_type = "mini_feynman" if fs.type == "mini" else "feynman"
            points = fs.covered_points or []

            for i, pt in enumerate(points):
                if pt is None:
                    continue  # Not evaluated
                if fs.type == "mini":
                    score = 1.0 if pt else 0.0
                else:
                    score = float(pt) / 5.0 if isinstance(pt, (int, float)) else 0.0

                ev = EvidenceEvent(
                    user_id=fs.user_id,
                    node_id=node_id,
                    item_id=f"fey_{block.id}_{i}",
                    source_type=source_type,
                    source_id=block.id,
                    attempt_id=fs.id,
                    attempt_number=1,
                    score=score,
                    quality_weight=get_quality_weight(source_type),
                    repeat_discount=1.0,  # latest attempt = full credit
                    timestamp=fs.updated_at or fs.created_at,
                )
                db.add(ev)
                events_created += 1

        await db.flush()
        logger.info("Created %d evidence events", events_created)

        # ── Recalculate mastery for all user×node pairs ──
        user_node_pairs = list(
            await db.execute(
                select(EvidenceEvent.user_id, EvidenceEvent.node_id).distinct()
            )
        )
        logger.info(
            "Recalculating mastery for %d user×node pairs", len(user_node_pairs)
        )

        for user_id, node_id in user_node_pairs:
            events = list(
                await db.scalars(
                    select(EvidenceEvent).where(
                        EvidenceEvent.user_id == user_id,
                        EvidenceEvent.node_id == node_id,
                    )
                )
            )
            result = compute_mastery_from_events(events)
            mastery = result["mastery"]

            rp = await db.scalar(
                select(RoadmapProgress).where(
                    RoadmapProgress.user_id == user_id,
                    RoadmapProgress.node_id == node_id,
                )
            )
            if rp:
                rp.mastery = mastery
                rp.progress = round(mastery)
            else:
                rp = RoadmapProgress(
                    user_id=user_id,
                    node_id=node_id,
                    mastery=mastery,
                    progress=round(mastery),
                )
                db.add(rp)
            logger.info(
                "  node=%s mastery=%.1f%% (%d events)",
                node_id,
                mastery,
                result["active_events"],
            )

        # ── Re-evaluate stars for all user×lesson pairs ──
        lesson_ids_with_data = set()
        for user_id, node_id in user_node_pairs:
            node = await db.get(RoadmapNode, node_id)
            if node and node.lesson_id:
                lesson_ids_with_data.add((user_id, node.lesson_id))

        for user_id, lesson_id in lesson_ids_with_data:
            stars = await evaluate_stars(db, lesson_id, user_id)
            await sync_stars_to_progress(db, lesson_id, user_id, stars)

            # Also sync to RoadmapProgress so lesson cards show stars
            node = await db.scalar(
                select(RoadmapNode).where(
                    RoadmapNode.lesson_id == lesson_id,
                    RoadmapNode.level == 3,
                )
            )
            if node:
                rp = await db.scalar(
                    select(RoadmapProgress).where(
                        RoadmapProgress.node_id == node.id,
                        RoadmapProgress.user_id == user_id,
                    )
                )
                if rp:
                    rp.stars = stars.stars

            logger.info(
                "  lesson=%s stars=%d (study=%s feynman=%s test=%s)",
                lesson_id,
                stars.stars,
                stars.study,
                stars.feynman,
                stars.test,
            )

        await db.commit()
        logger.info("Done! Backfill complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
