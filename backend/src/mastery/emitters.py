"""Evidence event emitters — bridge between learning activities and mastery engine.

Each function translates graded results into evidence_events rows,
handles invalidation of previous attempts, and triggers mastery recalculation.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.learning.models import FeynmanSession
from src.learning.tests.models import SessionAnswer, TestSession
from src.mastery.service import (
    emit_evidence_events,
    recalculate_mastery,
)
from src.mastery.stars import evaluate_stars, sync_stars_to_progress
from src.roadmap.models import RoadmapNode, RoadmapProgress
from src.roadmap.progress_bus import ProgressUpdate as BusProgressUpdate, progress_bus

logger = logging.getLogger(__name__)


def _resolve_source_type(template_type: str, question_type: str) -> str:
    """Map TestTemplate.type + TestQuestion.type to evidence source_type."""
    if template_type == "inline_quiz":
        return "inline_mcq" if question_type == "mcq" else "inline_short"
    if template_type == "lesson_test":
        return "lesson_test"
    if template_type == "practice_questions":
        return "standalone_test"
    if template_type == "past_paper":
        return "past_paper"
    return "lesson_test"


async def _get_node_id_for_lesson(
    db: AsyncSession, lesson_id: uuid.UUID
) -> uuid.UUID | None:
    """Find the level-3 roadmap node linked to a lesson."""
    result = await db.execute(
        select(RoadmapNode.id)
        .where(
            RoadmapNode.lesson_id == lesson_id,
            RoadmapNode.level == 3,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _sync_stars_to_roadmap(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
    stars: int,
) -> None:
    """Update RoadmapProgress.stars and notify SSE subscribers."""
    node = await db.scalar(
        select(RoadmapNode).where(
            RoadmapNode.lesson_id == lesson_id,
            RoadmapNode.level == 3,
        )
    )
    if node is None:
        return
    rp = await db.scalar(
        select(RoadmapProgress).where(
            RoadmapProgress.node_id == node.id,
            RoadmapProgress.user_id == user_id,
        )
    )
    if rp:
        rp.stars = stars
    else:
        rp = RoadmapProgress(node_id=node.id, user_id=user_id, stars=stars, progress=0)
        db.add(rp)

    # Push SSE update
    progress_bus.notify(BusProgressUpdate(
        node_id=node.id,
        folder_id=node.folder_id,
        mastery=rp.mastery if rp else None,
        confidence=rp.confidence if rp else None,
        stars=stars,
    ))


async def emit_test_session_events(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> None:
    """Create evidence events from a graded test session.

    Called after grade_session() completes. Handles:
    - Resolving node_ids from template/question
    - Determining source_type from template.type
    - Invalidating previous attempts for same source
    - Computing repeat discounts
    - Recalculating mastery and stars
    """
    test_session = await db.get(
        TestSession,
        session_id,
        options=[
            selectinload(TestSession.answers).selectinload(SessionAnswer.question),
            selectinload(TestSession.template),
        ],
    )
    if not test_session or test_session.status != "graded":
        return

    template = test_session.template
    user_id = test_session.user_id

    # Group answers by node_id
    node_items: dict[uuid.UUID, list[dict]] = {}

    for ans in test_session.answers:
        q = ans.question
        source_type = _resolve_source_type(template.type, q.type)

        # Determine score: MCQ = 0/1, short = earned/total
        if q.type == "mcq":
            score = 1.0 if ans.is_correct else 0.0
        else:
            score = (
                (ans.earned_marks / q.points)
                if q.points and ans.earned_marks is not None
                else 0.0
            )

        # Determine node_id: from question, template, or lesson
        q_node_ids = q.node_ids or template.node_ids or []
        if not q_node_ids and template.lesson_id:
            node_id = await _get_node_id_for_lesson(db, template.lesson_id)
            if node_id:
                q_node_ids = [node_id]

        item_id = q.item_id or f"q_{q.id}"

        for node_id in q_node_ids:
            if node_id not in node_items:
                node_items[node_id] = []
            node_items[node_id].append(
                {
                    "item_id": item_id,
                    "score": score,
                    "source_type": source_type,
                }
            )

    # Determine if this is a retakeable source (lesson_test, inline_quiz)
    invalidate = template.type in ("lesson_test", "inline_quiz")

    # Emit events per node
    affected_nodes: set[uuid.UUID] = set()
    for node_id, items in node_items.items():
        # All items in a node share the same source_type (from template)
        source_type = items[0]["source_type"]
        # Override quality weights per item based on actual source_type
        for item in items:
            item.setdefault("source_type", source_type)

        await emit_evidence_events(
            db=db,
            user_id=user_id,
            node_id=node_id,
            source_type=source_type,
            source_id=template.id,
            attempt_id=test_session.id,
            items=[{"item_id": i["item_id"], "score": i["score"]} for i in items],
            invalidate_previous=invalidate,
        )
        affected_nodes.add(node_id)

    # Recalculate mastery for all affected nodes
    for node_id in affected_nodes:
        await recalculate_mastery(db, user_id, node_id)

    # Re-evaluate stars if this is a lesson test or inline quiz
    if template.lesson_id:
        stars = await evaluate_stars(db, template.lesson_id, user_id)
        await sync_stars_to_progress(db, template.lesson_id, user_id, stars)
        await _sync_stars_to_roadmap(db, template.lesson_id, user_id, stars.stars)

    await db.commit()
    logger.info(
        "Emitted %d evidence events for session %s across %d nodes",
        sum(len(items) for items in node_items.values()),
        session_id,
        len(affected_nodes),
    )


async def emit_feynman_session_events(
    db: AsyncSession,
    feynman_session_id: uuid.UUID,
) -> None:
    """Create evidence events from a completed feynman session.

    Each covered_point becomes one evidence event.
    Mini-feynman: binary (covered=1.0, not=0.0), source_type=mini_feynman
    Standard feynman: score/5 (0.0-1.0), source_type=feynman
    """
    fs = await db.get(
        FeynmanSession,
        feynman_session_id,
        options=[selectinload(FeynmanSession.feynman_block)],
    )
    if not fs or fs.status not in ("completed", "aborted"):
        return

    block = fs.feynman_block
    lesson_id = block.lesson_id
    user_id = fs.user_id

    node_id = await _get_node_id_for_lesson(db, lesson_id)
    if not node_id:
        logger.warning("No roadmap node found for lesson %s", lesson_id)
        return

    source_type = "mini_feynman" if fs.type == "mini" else "feynman"
    points = fs.covered_points or []

    items: list[dict] = []
    for i, point_result in enumerate(points):
        if fs.type == "mini":
            # mini: bool (True/False)
            score = 1.0 if point_result else 0.0
        else:
            # standard: int 0-5
            score = (
                float(point_result) / 5.0
                if isinstance(point_result, (int, float))
                else 0.0
            )

        items.append(
            {
                "item_id": f"fey_{block.id}_{i}",
                "score": score,
            }
        )

    if not items:
        return

    await emit_evidence_events(
        db=db,
        user_id=user_id,
        node_id=node_id,
        source_type=source_type,
        source_id=block.id,
        attempt_id=fs.id,
        items=items,
        invalidate_previous=True,  # retakeable
    )

    await recalculate_mastery(db, user_id, node_id)

    # Re-evaluate stars
    stars = await evaluate_stars(db, lesson_id, user_id)
    await sync_stars_to_progress(db, lesson_id, user_id, stars)
    await _sync_stars_to_roadmap(db, lesson_id, user_id, stars.stars)

    await db.commit()
    logger.info(
        "Emitted %d feynman evidence events for session %s (type=%s)",
        len(items),
        feynman_session_id,
        fs.type,
    )
