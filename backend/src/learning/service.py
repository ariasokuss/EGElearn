"""Learning service — lesson and feynman block database operations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, delete, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.learning.models import (
    FeynmanBlock,
    LessonAccessEvent,
    FeynmanMessage,
    FeynmanSession,
    Lesson,
    LessonBlock,
    LessonProgress,
)
from src.learning.parser import (
    extract_description,
    parse_feynman_blocks,
    parse_lesson_blocks,
)
from src.roadmap.models import RoadmapNode, RoadmapProgress

logger = logging.getLogger(__name__)

# Maps lesson stars (0-3) to roadmap progress (0-100)
_STARS_TO_PROGRESS = {0: 0, 1: 33, 2: 66, 3: 100}


class LearningService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Lessons
    # ------------------------------------------------------------------

    async def list_lessons(
        self,
        user_id: uuid.UUID,
        include_shared: bool = False,
        *,
        limit: int = 500,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list:
        """Return lightweight lesson rows (no content column)."""
        if include_shared:
            condition = or_(Lesson.user_id == user_id, Lesson.user_id.is_(None))
        else:
            condition = Lesson.user_id == user_id
        stmt = (
            select(
                Lesson.id,
                Lesson.user_id,
                Lesson.name,
                Lesson.description,
                Lesson.num_blocks,
                Lesson.created_at,
            )
            .where(condition)
            .order_by(Lesson.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if session is not None:
            result = await session.execute(stmt)
            return list(result.mappings().all())
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return list(result.mappings().all())

    async def get_lesson(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> Lesson | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lesson)
                .where(
                    Lesson.id == lesson_id,
                    or_(Lesson.user_id == user_id, Lesson.user_id.is_(None)),
                )
                .options(
                    selectinload(Lesson.lesson_blocks),
                    selectinload(Lesson.feynman_blocks),
                )
            )
            return result.scalar_one_or_none()

    async def get_lesson_detail(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        folder_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> (
        tuple[
            Lesson,
            list[LessonBlock],
            list[FeynmanBlock],
            LessonProgress | None,
            dict | None,
        ]
        | None
    ):
        """Fetch lesson + blocks + feynman_blocks + progress + roadmap context in ONE session."""
        if session is not None:
            return await self._get_lesson_detail_with_session(
                session, lesson_id, user_id, folder_id=folder_id
            )
        async with self._session_factory() as session:
            return await self._get_lesson_detail_with_session(
                session, lesson_id, user_id, folder_id=folder_id
            )

    async def _get_lesson_detail_with_session(
        self,
        session: AsyncSession,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
    ) -> (
        tuple[
            Lesson,
            list[LessonBlock],
            list[FeynmanBlock],
            LessonProgress | None,
            dict | None,
        ]
        | None
    ):
        # 1. Lesson with eager-loaded blocks and feynman_blocks
        result = await session.execute(
            select(Lesson)
            .where(
                Lesson.id == lesson_id,
                or_(Lesson.user_id == user_id, Lesson.user_id.is_(None)),
            )
            .options(
                selectinload(Lesson.lesson_blocks),
                selectinload(Lesson.feynman_blocks),
            )
        )
        lesson = result.scalar_one_or_none()
        if lesson is None:
            return None

        # 2. Progress (same session — no extra connection overhead)
        progress = await session.scalar(
            select(LessonProgress).where(
                LessonProgress.lesson_id == lesson_id,
                LessonProgress.user_id == user_id,
            )
        )
        if folder_id is not None:
            in_folder = await session.scalar(
                select(RoadmapNode.id).where(
                    RoadmapNode.lesson_id == lesson_id,
                    RoadmapNode.folder_id == folder_id,
                )
            )
            if in_folder is not None:
                await self.touch_lesson_access(
                    lesson_id, user_id, folder_id=folder_id, session=session
                )
            else:
                # Still record access without folder; list_last_accessed matches via roadmap EXISTS.
                await self.touch_lesson_access(lesson_id, user_id, folder_id=None, session=session)
        else:
            await self.touch_lesson_access(lesson_id, user_id, folder_id=None, session=session)

        # 3. Roadmap context via single self-join
        roadmap_ctx = await self._get_roadmap_context_joined(session, lesson_id)

        # Sort blocks by block_number (selectinload doesn't guarantee order)
        blocks = sorted(lesson.lesson_blocks, key=lambda b: b.block_number)

        # get_db does not commit; without this, lesson_access_events inserts are rolled back.
        await session.commit()

        return lesson, blocks, list(lesson.feynman_blocks), progress, roadmap_ctx

    async def touch_lesson_access(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        folder_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        values: dict = {
            "id": uuid.uuid4(),
            "lesson_id": lesson_id,
            "user_id": user_id,
            "last_accessed_at": now,
            "folder_id": folder_id,
        }
        if folder_id is not None:
            stmt = (
                pg_insert(LessonAccessEvent)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["user_id", "lesson_id", "folder_id"],
                    index_where=text("folder_id IS NOT NULL"),
                    set_={"last_accessed_at": now},
                )
            )
        else:
            stmt = (
                pg_insert(LessonAccessEvent)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["user_id", "lesson_id"],
                    index_where=text("folder_id IS NULL"),
                    set_={"last_accessed_at": now},
                )
            )
        if session is not None:
            await session.execute(stmt)
            return

        async with self._session_factory() as db_session:
            await db_session.execute(stmt)
            await db_session.commit()

    async def list_last_accessed_lessons(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        *,
        limit: int | None = None,
        session: AsyncSession | None = None,
    ) -> list:
        settings = get_settings()
        effective_limit = limit or settings.learning.last_accessed_lessons_limit
        in_folder_roadmap = exists(
            select(1)
            .select_from(RoadmapNode)
            .where(
                RoadmapNode.lesson_id == LessonAccessEvent.lesson_id,
                RoadmapNode.folder_id == folder_id,
            )
        )
        access_in_folder = or_(
            LessonAccessEvent.folder_id == folder_id,
            and_(
                LessonAccessEvent.folder_id.is_(None),
                in_folder_roadmap,
            ),
        )
        ranked = (
            select(
                LessonAccessEvent.lesson_id,
                LessonAccessEvent.last_accessed_at,
                func.row_number()
                .over(
                    partition_by=LessonAccessEvent.lesson_id,
                    order_by=LessonAccessEvent.last_accessed_at.desc(),
                )
                .label("rn"),
            )
            .select_from(LessonAccessEvent)
            .join(Lesson, Lesson.id == LessonAccessEvent.lesson_id)
            .where(
                LessonAccessEvent.user_id == user_id,
                access_in_folder,
                or_(Lesson.user_id == user_id, Lesson.user_id.is_(None)),
            )
        ).subquery()

        pick = (
            select(
                ranked.c.lesson_id,
                ranked.c.last_accessed_at,
            ).where(ranked.c.rn == 1)
        ).subquery()

        stmt = (
            select(
                Lesson.id,
                Lesson.user_id,
                Lesson.name,
                Lesson.description,
                Lesson.num_blocks,
                Lesson.created_at,
            )
            .join(pick, pick.c.lesson_id == Lesson.id)
            .order_by(pick.c.last_accessed_at.desc())
            .limit(effective_limit)
        )
        if session is not None:
            result = await session.execute(stmt)
            return list(result.mappings().all())

        async with self._session_factory() as db_session:
            result = await db_session.execute(stmt)
            return list(result.mappings().all())

    async def _get_roadmap_context_joined(
        self,
        session: AsyncSession,
        lesson_id: uuid.UUID,
    ) -> dict | None:
        """Fetch section/subsection names in one query using self-joins."""
        from sqlalchemy.orm import aliased

        child = aliased(RoadmapNode, name="child")
        parent = aliased(RoadmapNode, name="parent")
        grandparent = aliased(RoadmapNode, name="grandparent")

        result = await session.execute(
            select(
                child.id,
                child.level.label("child_level"),
                parent.name.label("parent_name"),
                parent.level.label("parent_level"),
                grandparent.name.label("grandparent_name"),
                grandparent.level.label("grandparent_level"),
            )
            .select_from(child)
            .outerjoin(parent, child.parent_id == parent.id)
            .outerjoin(grandparent, parent.parent_id == grandparent.id)
            .where(child.lesson_id == lesson_id)
        )
        row = result.one_or_none()
        if row is None:
            return None

        section_name = None
        subsection_name = None

        if row.parent_level == 2:
            subsection_name = row.parent_name
            if row.grandparent_level == 1:
                section_name = row.grandparent_name
        elif row.parent_level == 1:
            section_name = row.parent_name

        if section_name is None:
            return None

        return {
            "node_id": row.id,
            "section_name": section_name,
            "subsection_name": subsection_name,
        }

    async def upload_lesson(
        self, user_id: uuid.UUID, name: str | None, content: str
    ) -> tuple[Lesson, list[LessonBlock]]:
        """Create a lesson from raw markdown, parse it into blocks, and persist everything."""
        parsed_blocks = parse_lesson_blocks(content)
        description = extract_description(content)
        logger.info(
            "Parsed lesson %r for user %s — %d blocks found",
            name,
            user_id,
            len(parsed_blocks),
        )

        async with self._session_factory() as session:
            lesson = Lesson(
                user_id=user_id,
                name=name,
                description=description,
                content=content,
                num_blocks=len(parsed_blocks),
            )
            session.add(lesson)
            await session.flush()  # get lesson.id before inserting blocks

            db_blocks: list[LessonBlock] = []
            for pb in parsed_blocks:
                block = LessonBlock(
                    lesson_id=lesson.id,
                    user_id=user_id,
                    content=pb.content,
                    block_number=pb.block_number,
                    is_summary=pb.is_summary,
                )
                session.add(block)
                db_blocks.append(block)

            # Create progress row for the uploading user
            session.add(
                LessonProgress(
                    lesson_id=lesson.id,
                    user_id=user_id,
                    stars=0,
                )
            )

            await session.commit()
            await session.refresh(lesson)
            for b in db_blocks:
                await session.refresh(b)

        logger.info(
            "Created lesson %s (%r) with %d blocks",
            lesson.id,
            lesson.name,
            len(db_blocks),
        )
        return lesson, db_blocks

    async def delete_lesson(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> Lesson | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lesson).where(Lesson.id == lesson_id, Lesson.user_id == user_id)
            )
            lesson = result.scalar_one_or_none()
            if lesson is not None:
                await session.delete(lesson)
                await session.commit()
            return lesson

    async def get_lesson_blocks(self, lesson_id: uuid.UUID) -> list[LessonBlock]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LessonBlock)
                .where(LessonBlock.lesson_id == lesson_id)
                .order_by(LessonBlock.block_number)
            )
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Lesson progress
    # ------------------------------------------------------------------

    async def get_lesson_progress(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LessonProgress | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LessonProgress).where(
                    LessonProgress.lesson_id == lesson_id,
                    LessonProgress.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def mark_star_reward_shown(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LessonProgress | None:
        async with self._session_factory() as session:
            lp = await session.scalar(
                select(LessonProgress).where(
                    LessonProgress.lesson_id == lesson_id,
                    LessonProgress.user_id == user_id,
                )
            )
            if lp is None:
                return None
            lp.star_reward_shown = True
            await session.commit()
            await session.refresh(lp)
            return lp

    async def complete_step(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        step: int,
    ) -> tuple[int, int | None]:
        """Re-evaluate stars based on actual performance data.

        The `step` parameter is kept for API compat but ignored —
        stars are now computed from real results (inline quiz scores,
        feynman coverage, test scores), not sequential steps.
        """
        async with self._session_factory() as session:
            # Verify lesson exists and user has access
            lesson = await session.scalar(
                select(Lesson).where(
                    Lesson.id == lesson_id,
                    or_(Lesson.user_id == user_id, Lesson.user_id.is_(None)),
                )
            )
            if lesson is None:
                raise ValueError("Lesson not found")

            # Evaluate stars from actual performance
            from src.mastery.stars import evaluate_stars, sync_stars_to_progress

            stars_eval = await evaluate_stars(session, lesson_id, user_id)
            await sync_stars_to_progress(session, lesson_id, user_id, stars_eval)

            # Sync stars count to roadmap (without overwriting progress/mastery)
            rp_info = await self._sync_roadmap_progress(
                session,
                lesson_id,
                user_id,
                stars_eval.stars,
            )

            await session.commit()
            return stars_eval, rp_info

    async def _sync_roadmap_progress(
        self,
        session: AsyncSession,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        stars: int,
    ) -> dict:
        """Update RoadmapProgress.stars when lesson stars change.

        NOTE: progress/mastery are now managed by the mastery engine
        (evidence_events → compute_mastery → roadmap_progress.mastery).
        This function only syncs the stars badge count for backward compat.
        It does NOT overwrite progress or mastery.

        Returns dict with progress, mastery, confidence for the frontend.
        """
        node = await session.scalar(
            select(RoadmapNode).where(RoadmapNode.lesson_id == lesson_id)
        )
        if node is None:
            return {"progress": None, "mastery": None, "confidence": None}

        # Upsert: only touch stars, leave progress/mastery untouched
        existing = await session.scalar(
            select(RoadmapProgress).where(
                RoadmapProgress.node_id == node.id,
                RoadmapProgress.user_id == user_id,
            )
        )
        if existing:
            existing.stars = stars
            return {
                "progress": existing.progress,
                "mastery": existing.mastery,
                "confidence": existing.confidence,
            }
        else:
            rp = RoadmapProgress(
                node_id=node.id,
                user_id=user_id,
                stars=stars,
                progress=0,  # mastery engine will set this
            )
            session.add(rp)
            return {"progress": 0, "mastery": None, "confidence": None}

    # ------------------------------------------------------------------
    # Full lesson reset
    # ------------------------------------------------------------------

    async def reset_lesson(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Fully reset a lesson: clear all sessions, stars, evidence, and mastery.

        Used when a student wants to redo a lesson from scratch.
        """
        from src.learning.tests.models import TestSession, TestTemplate
        from src.mastery.service import (
            invalidate_all_lesson_events,
            recalculate_mastery,
        )

        async with self._session_factory() as session:
            # 1. Find roadmap node for this lesson
            node = await session.scalar(
                select(RoadmapNode).where(RoadmapNode.lesson_id == lesson_id)
            )

            # 2. Invalidate all evidence events for this node
            if node:
                await invalidate_all_lesson_events(session, user_id, node.id)

            # 3. Reset all feynman sessions (mini + standard) for this lesson
            feynman_sessions = await session.scalars(
                select(FeynmanSession)
                .join(FeynmanBlock, FeynmanSession.feynman_block_id == FeynmanBlock.id)
                .where(
                    FeynmanBlock.lesson_id == lesson_id,
                    FeynmanSession.user_id == user_id,
                    FeynmanSession.status.in_(["active", "not_started", "completed", "aborted"]),
                )
            )
            for fs in feynman_sessions:
                fs.status = "reset"

            # 4. Reset all test sessions for this lesson's templates
            template_ids_result = await session.scalars(
                select(TestTemplate.id).where(
                    TestTemplate.lesson_id == lesson_id,
                    TestTemplate.type.in_(["inline_quiz", "lesson_test"]),
                )
            )
            template_ids = list(template_ids_result)
            if template_ids:
                test_sessions = await session.scalars(
                    select(TestSession).where(
                        TestSession.template_id.in_(template_ids),
                        TestSession.user_id == user_id,
                        TestSession.status.in_(["not_started", "active", "graded"]),
                    )
                )
                for ts in test_sessions:
                    ts.status = "reset"

            # 5. Reset LessonProgress
            lp = await session.scalar(
                select(LessonProgress).where(
                    LessonProgress.lesson_id == lesson_id,
                    LessonProgress.user_id == user_id,
                )
            )
            if lp:
                lp.stars = 0
                lp.progress = 0
                lp.mastery = None
                lp.star_reward_shown = False
                try:
                    lp.study_star = False
                    lp.feynman_star = False
                    lp.test_star = False
                except AttributeError:
                    pass

            # 6. Reset RoadmapProgress
            if node:
                rp = await session.scalar(
                    select(RoadmapProgress).where(
                        RoadmapProgress.node_id == node.id,
                        RoadmapProgress.user_id == user_id,
                    )
                )
                if rp:
                    rp.progress = 0
                    rp.mastery = None
                    rp.confidence = None
                    rp.stars = 0

            # 7. Recalculate mastery (resets to priors ~10%)
            if node:
                await recalculate_mastery(session, user_id, node.id)

            await session.commit()

    # ------------------------------------------------------------------
    # Roadmap context
    # ------------------------------------------------------------------

    async def get_roadmap_context(
        self,
        lesson_id: uuid.UUID,
    ) -> dict | None:
        """Get roadmap context (section/subsection names) for a lesson."""
        async with self._session_factory() as session:
            # Find the level-3 node linked to this lesson
            node = await session.scalar(
                select(RoadmapNode).where(RoadmapNode.lesson_id == lesson_id)
            )
            if node is None:
                return None

            # Walk up the parent chain to get section/subsection names
            subsection_name = None
            section_name = None

            parent = (
                await session.get(RoadmapNode, node.parent_id)
                if node.parent_id
                else None
            )
            if parent is not None:
                if parent.level == 2:
                    subsection_name = parent.name
                    grandparent = (
                        await session.get(RoadmapNode, parent.parent_id)
                        if parent.parent_id
                        else None
                    )
                    if grandparent is not None and grandparent.level == 1:
                        section_name = grandparent.name
                elif parent.level == 1:
                    section_name = parent.name

            if section_name is None:
                return None

            return {
                "node_id": node.id,
                "section_name": section_name,
                "subsection_name": subsection_name,
            }

    # ------------------------------------------------------------------
    # Feynman blocks
    # ------------------------------------------------------------------

    async def parse_and_store_feynman_blocks(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[FeynmanBlock]:
        """Parse lesson content, delete existing feynman blocks, insert fresh ones."""
        async with self._session_factory() as session:
            lesson = await session.get(Lesson, lesson_id)
            if lesson is None or lesson.user_id != user_id:
                logger.warning(
                    "parse_and_store_feynman_blocks: lesson %s not found or access denied for user %s",
                    lesson_id,
                    user_id,
                )
                return []

            parsed = parse_feynman_blocks(lesson.content)
            logger.info(
                "Parsed %d feynman block(s) from lesson %s", len(parsed), lesson_id
            )

            # Delete existing feynman blocks for this lesson (idempotent)
            await session.execute(
                delete(FeynmanBlock).where(FeynmanBlock.lesson_id == lesson_id)
            )

            new_blocks: list[FeynmanBlock] = []
            for p in parsed:
                block = FeynmanBlock(
                    lesson_id=lesson_id,
                    user_id=user_id,
                    scope=p.scope,
                    question=p.question,
                    points=p.points,
                )
                session.add(block)
                new_blocks.append(block)

            await session.commit()
            for b in new_blocks:
                await session.refresh(b)

        logger.info(
            "Stored %d feynman block(s) for lesson %s", len(new_blocks), lesson_id
        )
        return new_blocks

    async def get_feynman_block(
        self, feynman_block_id: uuid.UUID, user_id: uuid.UUID
    ) -> FeynmanBlock | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeynmanBlock).where(
                    FeynmanBlock.id == feynman_block_id,
                    or_(
                        FeynmanBlock.user_id == user_id, FeynmanBlock.user_id.is_(None)
                    ),
                )
            )
            return result.scalar_one_or_none()

    async def list_feynman_blocks(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[FeynmanBlock]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeynmanBlock).where(
                    FeynmanBlock.lesson_id == lesson_id,
                    or_(
                        FeynmanBlock.user_id == user_id, FeynmanBlock.user_id.is_(None)
                    ),
                )
            )
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Feynman sessions
    # ------------------------------------------------------------------

    async def create_session(
        self,
        feynman_block_id: uuid.UUID,
        user_id: uuid.UUID,
        type: str = "mini",
    ) -> FeynmanSession:
        async with self._session_factory() as session:
            feynman_session = FeynmanSession(
                feynman_block_id=feynman_block_id,
                user_id=user_id,
                status="active",
                type=type,
                current_iteration=1,
            )
            session.add(feynman_session)
            await session.commit()
            await session.refresh(feynman_session)
        logger.info(
            "Created feynman session %s (type=%s) for block %s (user %s)",
            feynman_session.id,
            type,
            feynman_block_id,
            user_id,
        )
        return feynman_session

    async def get_session_with_block(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> FeynmanSession | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeynmanSession)
                .where(
                    FeynmanSession.id == session_id,
                    FeynmanSession.user_id == user_id,
                )
                .options(
                    selectinload(FeynmanSession.feynman_block),
                    selectinload(FeynmanSession.messages),
                )
            )
            return result.scalar_one_or_none()

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        iteration: int,
        citations: list[str] | None = None,
    ) -> FeynmanMessage:
        async with self._session_factory() as session:
            stored_citations = (
                (citations if citations else []) if role == "user" else None
            )
            message = FeynmanMessage(
                session_id=session_id,
                role=role,
                content=content,
                iteration=iteration,
                citations=stored_citations,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def get_messages(self, session_id: uuid.UUID) -> list[FeynmanMessage]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeynmanMessage)
                .where(FeynmanMessage.session_id == session_id)
                .order_by(FeynmanMessage.created_at)
            )
            return list(result.scalars().all())

    async def advance_iteration(
        self, session_id: uuid.UUID, new_iteration: int
    ) -> None:
        async with self._session_factory() as session:
            feynman_session = await session.get(FeynmanSession, session_id)
            if feynman_session:
                feynman_session.current_iteration = new_iteration
                feynman_session.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    "Session %s advanced to iteration %d", session_id, new_iteration
                )

    async def list_sessions_for_lesson(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[FeynmanSession]:
        """Return all sessions the user has for any feynman block in a lesson."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FeynmanSession)
                .join(FeynmanBlock, FeynmanSession.feynman_block_id == FeynmanBlock.id)
                .where(
                    FeynmanBlock.lesson_id == lesson_id,
                    FeynmanSession.user_id == user_id,
                )
                .options(selectinload(FeynmanSession.feynman_block))
                .order_by(FeynmanSession.created_at.desc())
            )
            return list(result.scalars().all())

    async def abort_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> FeynmanSession | None:
        """Set an active session to 'aborted'. Completed sessions are unchanged."""
        async with self._session_factory() as session:
            feynman_session = await session.scalar(
                select(FeynmanSession).where(
                    FeynmanSession.id == session_id,
                    FeynmanSession.user_id == user_id,
                )
            )
            if feynman_session is None:
                return None
            if feynman_session.status == "active":
                feynman_session.status = "aborted"
                feynman_session.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(feynman_session)
                logger.info("Session %s aborted by user %s", session_id, user_id)
            return feynman_session

    async def complete_session(
        self, session_id: uuid.UUID, covered_points: list
    ) -> FeynmanSession | None:
        async with self._session_factory() as session:
            feynman_session = await session.get(FeynmanSession, session_id)
            if feynman_session:
                feynman_session.status = "completed"
                feynman_session.covered_points = covered_points
                feynman_session.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(feynman_session)
                logger.info(
                    "Session %s completed — covered_points=%s",
                    session_id,
                    covered_points,
                )

                # Emit mastery evidence events
                try:
                    from src.mastery.emitters import emit_feynman_session_events

                    async with self._session_factory() as mastery_session:
                        await emit_feynman_session_events(mastery_session, session_id)
                except Exception:
                    logger.exception(
                        "Failed to emit mastery events for feynman session %s",
                        session_id,
                    )

            return feynman_session

    async def update_theme_scores(
        self, session_id: uuid.UUID, scores: list[int | None]
    ) -> None:
        """Update the ongoing theme scores for a standard feynman session."""
        async with self._session_factory() as session:
            feynman_session = await session.get(FeynmanSession, session_id)
            if feynman_session:
                feynman_session.covered_points = scores
                feynman_session.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def save_session_feedback(
        self, session_id: uuid.UUID, feedback: list
    ) -> None:
        """Persist LLM-generated per-theme feedback list on a completed or aborted session."""
        async with self._session_factory() as session:
            feynman_session = await session.get(FeynmanSession, session_id)
            if feynman_session:
                feynman_session.feedback = feedback
                feynman_session.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info("Saved feedback for session %s", session_id)

    # ------------------------------------------------------------------
    # Lesson results
    # ------------------------------------------------------------------

    async def get_latest_standard_session(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> FeynmanSession | None:
        """Return the most recent finished standard Feynman session for a lesson.

        Includes both 'completed' and 'aborted' sessions — aborted sessions
        with scores still count as valid evidence (the student attempted it).
        """
        async with self._session_factory() as session:
            return await session.scalar(
                select(FeynmanSession)
                .join(FeynmanBlock, FeynmanSession.feynman_block_id == FeynmanBlock.id)
                .where(
                    FeynmanBlock.lesson_id == lesson_id,
                    FeynmanSession.user_id == user_id,
                    FeynmanSession.status.in_(["completed", "aborted"]),
                    FeynmanSession.type == "standard",
                )
                .options(selectinload(FeynmanSession.feynman_block))
                .order_by(FeynmanSession.created_at.desc())
            )

    async def get_latest_graded_test_result(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        """Return earned_marks, total_marks and score (0-100) of the latest graded test session."""
        from src.learning.tests.models import TestSession, TestTemplate

        async with self._session_factory() as session:
            test_session = await session.scalar(
                select(TestSession)
                .join(TestTemplate)
                .where(
                    TestTemplate.lesson_id == lesson_id,
                    TestTemplate.type == "lesson_test",
                    TestSession.user_id == user_id,
                    TestSession.status == "graded",
                )
                .order_by(TestSession.graded_at.desc())
            )
            if test_session is None:
                return None
            return {
                "earned_marks": test_session.earned_marks or 0,
                "total_marks": test_session.total_marks,
                "score": (test_session.score or 0) * 100,
            }

    async def get_inline_quiz_score(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        """Return earned_marks, total_marks and score (0-100) of the best inline quiz session."""
        from src.learning.tests.models import TestSession, TestTemplate

        async with self._session_factory() as session:
            test_session = await session.scalar(
                select(TestSession)
                .join(TestTemplate)
                .where(
                    TestTemplate.lesson_id == lesson_id,
                    TestTemplate.type == "inline_quiz",
                    TestSession.user_id == user_id,
                    TestSession.status.in_(["graded", "active"]),
                    TestSession.score.isnot(None),
                )
                .order_by(TestSession.score.desc())
            )
            if test_session is None or test_session.score is None:
                return None
            return {
                "earned_marks": test_session.earned_marks or 0,
                "total_marks": test_session.total_marks or 0,
                "score": (test_session.score or 0) * 100,
            }

    async def get_lesson_block_ids_by_numbers(
        self, lesson_id: uuid.UUID, block_numbers: list[int]
    ) -> dict[int, uuid.UUID]:
        """Map block_number → lesson_block UUID for a given lesson."""
        from src.learning.models import LessonBlock

        async with self._session_factory() as session:
            blocks = await session.scalars(
                select(LessonBlock).where(
                    LessonBlock.lesson_id == lesson_id,
                    LessonBlock.block_number.in_(block_numbers),
                )
            )
            return {b.block_number: b.id for b in blocks}
