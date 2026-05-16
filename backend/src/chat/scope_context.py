"""Helpers to fetch lesson/practice scope context for the side chat."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.learning.models import FeynmanBlock, FeynmanMessage, FeynmanSession, Lesson, LessonBlock
from src.learning.tests.models import SessionAnswer, TestQuestion
from src.learning.feedback.models import FeedbackNote


async def fetch_lesson_context(
    session_factory: async_sessionmaker[AsyncSession],
    lesson_id: str,
    user_id: str,
) -> tuple[str, str]:
    """Return (lesson_content, feynman_history_text) for the given lesson.

    *lesson_content* is the raw markdown of the lesson.
    *feynman_history_text* is a formatted summary of the student's feynman
    exercise conversations for this lesson, or an empty string if none exist.
    """
    lid = uuid.UUID(lesson_id)
    uid = uuid.UUID(user_id)

    async with session_factory() as db:
        lesson = await db.get(Lesson, lid)
        lesson_content = lesson.content if lesson else ""

        # 1. Fetch all FeynmanBlocks for this lesson.
        block_rows = await db.execute(
            select(FeynmanBlock)
            .where(FeynmanBlock.lesson_id == lid)
            .order_by(FeynmanBlock.created_at)
        )
        blocks: list[FeynmanBlock] = list(block_rows.scalars().all())

        if not blocks:
            return lesson_content, ""

        block_ids = [b.id for b in blocks]

        # 2. Fetch sessions for this user across all blocks.
        session_rows = await db.execute(
            select(FeynmanSession)
            .where(
                FeynmanSession.feynman_block_id.in_(block_ids),
                FeynmanSession.user_id == uid,
            )
            .order_by(FeynmanSession.created_at)
        )
        sessions: list[FeynmanSession] = list(session_rows.scalars().all())

        if not sessions:
            return lesson_content, ""

        session_ids = [s.id for s in sessions]

        # 3. Fetch all messages for those sessions.
        msg_rows = await db.execute(
            select(FeynmanMessage)
            .where(FeynmanMessage.session_id.in_(session_ids))
            .order_by(FeynmanMessage.created_at)
        )
        messages: list[FeynmanMessage] = list(msg_rows.scalars().all())

    # Group sessions by block_id and messages by session_id.
    sessions_by_block: dict[uuid.UUID, list[FeynmanSession]] = defaultdict(list)
    for s in sessions:
        sessions_by_block[s.feynman_block_id].append(s)

    messages_by_session: dict[uuid.UUID, list[FeynmanMessage]] = defaultdict(list)
    for m in messages:
        messages_by_session[m.session_id].append(m)

    feynman_history_text = _build_feynman_history_text(
        blocks, sessions_by_block, messages_by_session
    )
    return lesson_content, feynman_history_text


def _build_feynman_history_text(
    blocks: list[FeynmanBlock],
    sessions_by_block: dict[uuid.UUID, list[FeynmanSession]],
    messages_by_session: dict[uuid.UUID, list[FeynmanMessage]],
) -> str:
    """Format feynman blocks + session conversations into a readable block."""
    parts: list[str] = []
    exercise_num = 0

    for block in blocks:
        block_sessions = sessions_by_block.get(block.id, [])
        sessions_with_messages = [
            s for s in block_sessions if messages_by_session.get(s.id)
        ]
        if not sessions_with_messages:
            continue

        exercise_num += 1
        parts.append(f"### Feynman Exercise {exercise_num}")
        parts.append(f"**Exercise question:** {block.question}")

        for session in sessions_with_messages:
            status_label = {
                "completed": "✓ completed",
                "aborted": "⊘ aborted",
                "active": "… in progress",
            }.get(session.status, session.status)
            parts.append(f"\n*Session status: {status_label}*")

            for msg in messages_by_session[session.id]:
                role_label = "Student" if msg.role == "user" else "Coach"
                parts.append(f"**{role_label}:** {msg.content}")

        parts.append("")  # blank line between exercises

    if not parts:
        return ""

    header = "## Student's Feynman Exercise Progress\n"
    return header + "\n".join(parts)


async def fetch_practice_question_text(
    session_factory: async_sessionmaker[AsyncSession],
    question_id: str,
) -> str | None:
    """Return the question text for the given question UUID, or None."""
    qid = uuid.UUID(question_id)
    async with session_factory() as db:
        question = await db.get(TestQuestion, qid)
    if question is None:
        return None

    # For MCQ questions, include the options so the AI knows the full question.
    if question.type == "mcq" and question.options:
        options_text = "\n".join(
            f"  {chr(ord('A') + i)}) {opt}"
            for i, opt in enumerate(question.options)
        )
        return f"{question.question}\n\nOptions:\n{options_text}"

    return question.question


async def fetch_current_block_info(
    session_factory: async_sessionmaker[AsyncSession],
    block_id: str,
) -> str | None:
    """Return a short label for the currently visible lesson block, e.g. 'Block 3 — Introduction'.

    Returns None if the block is not found.
    """
    bid = uuid.UUID(block_id)
    async with session_factory() as db:
        block = await db.get(LessonBlock, bid)
    if block is None:
        return None
    label = f"Block {block.block_number}"
    if block.title:
        label = f"{label} — {block.title}"
    return label


async def fetch_answer_context(
    session_factory: async_sessionmaker[AsyncSession],
    test_session_id: str,
    question_id: str,
    scope_type: str | None,
    feedback_note_id: str | None = None,
) -> str | None:
    """Build structured context text from the student's answer and optionally their feedback note.

    Returns None if no answer exists yet (question not answered).
    """
    from sqlalchemy import and_

    ts_uuid = uuid.UUID(test_session_id)
    q_uuid = uuid.UUID(question_id)

    async with session_factory() as db:
        question = await db.get(TestQuestion, q_uuid)
        if question is None:
            return None

        result = await db.execute(
            select(SessionAnswer).where(
                and_(
                    SessionAnswer.session_id == ts_uuid,
                    SessionAnswer.question_id == q_uuid,
                )
            )
        )
        answer = result.scalar_one_or_none()

        note: FeedbackNote | None = None
        if feedback_note_id and scope_type == "feedback_review":
            note = await db.get(FeedbackNote, uuid.UUID(feedback_note_id))

    if answer is None:
        return None

    parts: list[str] = []
    parts.append("## Student's Answer Context\n")

    # Question info
    q_text = question.question
    if question.type == "mcq" and question.options:
        options_text = "\n".join(
            f"  {chr(ord('A') + i)}) {opt}"
            for i, opt in enumerate(question.options)
        )
        q_text = f"{q_text}\n\nOptions:\n{options_text}"
    parts.append(f"**Question:** {q_text}")

    # Student's answer
    if question.type == "mcq" and question.options:
        try:
            idx = int(answer.answer)
            answer_text = f"{chr(ord('A') + idx)}) {question.options[idx]}"
        except (ValueError, IndexError):
            answer_text = answer.answer
    else:
        answer_text = answer.answer
    parts.append(f"**Student answered:** {answer_text}")

    # Grading result
    if answer.is_correct is not None:
        result_text = "correct" if answer.is_correct else "incorrect"
        marks = f"{answer.earned_marks}/{question.points}" if answer.earned_marks is not None else "not yet graded"
        parts.append(f"**Result:** {result_text}, {marks}")

    if answer.feedback:
        parts.append(f"**Feedback:** {answer.feedback}")
    if answer.recommendations:
        parts.append(f"**Recommendations:** {answer.recommendations}")

    # Review scope: include model answer and mark scheme
    if scope_type in ("review", "feedback_review"):
        if question.model_answer:
            parts.append(f"**Model answer:** {question.model_answer}")
        if question.mark_scheme:
            parts.append(f"**Mark scheme:** {question.mark_scheme}")

    # Feedback note context
    if note:
        parts.append("\n## Feedback Note Context\n")
        parts.append(f"**Mistake:** {note.mistake}")
        parts.append(f"**Correction:** {note.correction}")
        parts.append(f"**Topic:** {note.topic}")
        parts.append(f"**Severity:** {note.severity}")
        parts.append(f"**Current stage:** {note.status}")
        if note.review_question:
            parts.append(f"**Review question:** {note.review_question}")

    return "\n".join(parts)
