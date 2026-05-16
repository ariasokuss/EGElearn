"""Seed inline quiz templates from lesson content.

Extracts ::: question directives from lesson block markdown and stores them as
TestTemplate(type="inline_quiz") + TestQuestion rows.  Mirrors the feynman block
extraction pattern (parse_feynman_blocks → FeynmanBlock).

Called during the A-Level seed pipeline, after seed_subject_tests().
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.learning.models import Lesson, LessonBlock
from src.learning.parser import parse_inline_questions
from src.learning.tests.models import TestQuestion, TestTemplate

logger = logging.getLogger(__name__)


async def seed_inline_quizzes(
    session: AsyncSession,
    folder_id: uuid.UUID,
    lesson_nodes: list[tuple[str, str, "Lesson", object]],
) -> int:
    """Seed inline quiz templates for all lessons that contain inline questions.

    Parameters
    ----------
    session:
        Active async DB session.
    folder_id:
        UUID of the shared folder this subject belongs to.
    lesson_nodes:
        List of (id_str, name, Lesson, RoadmapNode) tuples from the seeding loop.

    Returns
    -------
    int
        Number of inline quiz templates created.
    """
    # Clear existing shared inline_quiz templates for this folder
    await session.execute(
        delete(TestTemplate).where(
            TestTemplate.folder_id == folder_id,
            TestTemplate.user_id.is_(None),
            TestTemplate.type == "inline_quiz",
        )
    )
    await session.flush()

    seeded = 0

    for _id_str, name, lesson, node in lesson_nodes:
        # Load lesson blocks for this lesson
        result = await session.execute(
            select(LessonBlock)
            .where(LessonBlock.lesson_id == lesson.id)
            .order_by(LessonBlock.block_number)
        )
        blocks = list(result.scalars())

        if not blocks:
            continue

        # Parse all inline questions across blocks
        # Use block UUID (str) as key — matches frontend BlockRenderer which passes block.id
        all_questions = []
        for block in blocks:
            parsed = parse_inline_questions(block.content, str(block.id))
            all_questions.extend(parsed)

        if not all_questions:
            continue

        total_marks = sum(q.points for q in all_questions)

        node_id = node.id if hasattr(node, "id") else None

        template = TestTemplate(
            user_id=None,
            folder_id=folder_id,
            lesson_id=lesson.id,
            name=f"Inline Quiz: {name}",
            type="inline_quiz",
            status="ready",
            node_ids=[node_id] if node_id else None,
            total_questions=len(all_questions),
            total_marks=total_marks,
        )
        session.add(template)
        await session.flush()

        for idx, q in enumerate(all_questions):
            tq = TestQuestion(
                template_id=template.id,
                index=idx,
                type=q.type,
                question=q.question,
                options=q.options,
                correct_option_index=q.correct_option_index,
                model_answer=q.model_answer or None,
                mark_scheme=q.mark_scheme,
                points=q.points,
                node_ids=[node_id] if node_id else None,
                inline_key=q.inline_key,
            )
            session.add(tq)

        seeded += 1
        logger.info(
            "Seeded inline quiz for '%s': %d questions, %d marks",
            name,
            len(all_questions),
            total_marks,
        )

    return seeded


async def seed_inline_quiz_for_lesson(
    session: AsyncSession,
    lesson: Lesson,
    folder_id: uuid.UUID,
    node_id: uuid.UUID | None = None,
) -> TestTemplate | None:
    """Seed inline quiz for a single lesson (used for user-uploaded lessons).

    Idempotent — deletes existing inline_quiz template for this lesson first.
    """
    # Delete existing
    await session.execute(
        delete(TestTemplate).where(
            TestTemplate.lesson_id == lesson.id,
            TestTemplate.type == "inline_quiz",
        )
    )
    await session.flush()

    # Load blocks
    result = await session.execute(
        select(LessonBlock)
        .where(LessonBlock.lesson_id == lesson.id)
        .order_by(LessonBlock.block_number)
    )
    blocks = list(result.scalars())

    all_questions = []
    for block in blocks:
        parsed = parse_inline_questions(block.content, str(block.id))
        all_questions.extend(parsed)

    if not all_questions:
        return None

    total_marks = sum(q.points for q in all_questions)

    template = TestTemplate(
        user_id=lesson.user_id,
        folder_id=folder_id,
        lesson_id=lesson.id,
        name=f"Inline Quiz: {lesson.name or 'Untitled'}",
        type="inline_quiz",
        status="ready",
        node_ids=[node_id] if node_id else None,
        total_questions=len(all_questions),
        total_marks=total_marks,
    )
    session.add(template)
    await session.flush()

    for idx, q in enumerate(all_questions):
        tq = TestQuestion(
            template_id=template.id,
            index=idx,
            type=q.type,
            question=q.question,
            options=q.options,
            correct_option_index=q.correct_option_index,
            model_answer=q.model_answer or None,
            mark_scheme=q.mark_scheme,
            points=q.points,
            node_ids=[node_id] if node_id else None,
            inline_key=q.inline_key,
        )
        session.add(tq)

    logger.info(
        "Seeded inline quiz for lesson %s: %d questions, %d marks",
        lesson.id,
        len(all_questions),
        total_marks,
    )
    return template
