"""Test session lifecycle — start, auto-save, submit, grade."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import StaleDataError

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.core.s3 import S3Client
from src.activity.service import ActivityEventInput
from src.learning.tests.activity_replay import test_graded_replay_payload
from src.learning.feedback.service import FeedbackNoteService
from src.prompts.manager import PromptManager
from src.learning.tests.models import (
    SessionAiHintUsage,
    SessionAnswer,
    TestQuestion,
    TestSession,
    TestTemplate,
)
from src.learning.tests.prompts import build_grading_messages

logger = logging.getLogger(__name__)


def hint_advisory_lock_key(session_id: uuid.UUID, question_id: uuid.UUID) -> int:
    """64-bit key for pg_try_advisory_xact_lock (same session+question → same lock)."""
    return (session_id.int ^ question_id.int) & ((1 << 62) - 1)


class SessionServiceError(Exception):
    """Raised for business-logic failures in the session domain."""


async def rollup_session_graded_marks(
    session: AsyncSession, session_id: uuid.UUID
) -> None:
    """Sum earned_marks from graded answers into test_sessions (practice progress)."""
    ts = await session.get(TestSession, session_id)
    if ts is None:
        return
    total = await session.scalar(
        select(func.coalesce(func.sum(SessionAnswer.earned_marks), 0)).where(
            SessionAnswer.session_id == session_id,
            SessionAnswer.graded_at.isnot(None),
        )
    )
    earned = int(total or 0)
    ts.earned_marks = earned
    if ts.total_marks and ts.total_marks > 0:
        ts.score = earned / ts.total_marks


class TestSessionService:
    """Manages test session lifecycle — start, save, submit, grade."""
    _active_grade_sessions: set[uuid.UUID] = set()

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: YandexGPTLLMGateway | None = None,
        usage_service: object | None = None,
        prompt_manager: PromptManager | None = None,
        s3: S3Client | None = None,
        activity_service: object | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm
        self._feedback = FeedbackNoteService(session_factory)
        self._usage_service = usage_service
        self._pm = prompt_manager
        self._s3 = s3
        self._activity_service = activity_service

    def _get_llm(self) -> YandexGPTLLMGateway:
        if self._llm is None:
            self._llm = YandexGPTLLMGateway()
        return self._llm

    @staticmethod
    def _requires_llm_grading(question_type: str | None, *, is_unsupported: bool = False) -> bool:
        """True for question types graded via LLM after save/submit.

        Unsupported (diagram/graphical) questions are self-reported by the student,
        so they must never be sent to the LLM grader.
        """
        if is_unsupported:
            return False
        return question_type in ("short", "open")

    @staticmethod
    def _normalize_image_keys(image_keys: list[str] | None) -> list[str] | None:
        """Return deduplicated image keys, or None when caller did not specify images."""
        if image_keys is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_key in image_keys:
            key = str(raw_key).strip()
            if not key or key in seen:
                continue
            normalized.append(key)
            seen.add(key)
        return normalized

    @staticmethod
    def _sync_answer_image_keys(answer: SessionAnswer, image_keys: list[str] | None) -> bool:
        """Apply caller-provided image keys. Returns True when keys changed."""
        if image_keys is None:
            return False
        current = list(answer.image_keys or ([answer.image_key] if answer.image_key else []))
        if current == image_keys:
            return False
        answer.image_keys = image_keys
        answer.image_key = image_keys[0] if image_keys else None
        return True

    # ── Start ───────────────────────────────────────────────────────────

    async def start_session(
        self,
        user_id: uuid.UUID,
        template_id: uuid.UUID,
        mode: str = "practice",
    ) -> tuple[TestSession, TestTemplate]:
        """Create a new session for a template.

        Returns (test_session, template) so the caller can build the full
        SessionDetailOut without a second round-trip — template.questions is
        eagerly loaded and retained via expire_on_commit=False.
        """
        async with self._session_factory() as session:
            template = await session.get(
                TestTemplate,
                template_id,
                options=[selectinload(TestTemplate.questions)],
            )
            if not template:
                raise SessionServiceError("Template not found")
            if template.status != "ready":
                raise SessionServiceError(
                    f"Template is not ready (status={template.status})"
                )

            now = datetime.now(timezone.utc)
            test_session = TestSession(
                template_id=template_id,
                user_id=user_id,
                session_mode=mode,
                status="not_started",
                total_marks=template.total_marks or 0,
                created_at=now,
                updated_at=now,
            )
            session.add(test_session)
            await session.commit()
            # expire_on_commit=False keeps attributes accessible — no refresh needed
            return test_session, template

    # ── Auto-save answer ────────────────────────────────────────────────

    async def save_answer(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_text: str,
        image_keys: list[str] | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> SessionAnswer:
        """Upsert a single answer. MCQ answers are instantly graded."""
        normalized_image_keys = self._normalize_image_keys(image_keys)
        logger.info(
            "save_answer called: session=%s question=%s answer_length=%d image_count=%d",
            session_id,
            question_id,
            len((answer_text or "").strip()),
            len(normalized_image_keys or []),
        )
        if session is not None:
            return await self._save_answer_impl(
                session, session_id, user_id, question_id, answer_text, normalized_image_keys
            )
        async with self._session_factory() as session:
            return await self._save_answer_impl(
                session, session_id, user_id, question_id, answer_text, normalized_image_keys
            )

    async def _save_answer_impl(
        self,
        session: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_text: str,
        image_keys: list[str] | None = None,
    ) -> SessionAnswer:
        # Lock the parent test_sessions row to serialize concurrent
        # save / submit calls and avoid deadlocks on the
        # session_answers <-> test_sessions update pair.
        test_session = await session.scalar(
            select(TestSession).where(TestSession.id == session_id).with_for_update()
        )
        if not test_session or test_session.user_id != user_id:
            raise SessionServiceError("Session not found")
        if test_session.status not in ("not_started", "active"):
            raise SessionServiceError(
                f"Cannot save answers (status={test_session.status})"
            )

        # Verify question belongs to this template
        question = await session.get(TestQuestion, question_id)
        if not question or question.template_id != test_session.template_id:
            raise SessionServiceError("Question does not belong to this template")
        normalized_image_keys = self._normalize_image_keys(image_keys)
        if question.type == "mcq" and normalized_image_keys:
            raise SessionServiceError(
                "Image attachments are not supported for MCQ questions"
            )

        now = datetime.now(timezone.utc)

        # Transition not_started → active
        if test_session.status == "not_started":
            logger.info("Session %s transitioning not_started → active", session_id)
            test_session.status = "active"
            test_session.started_at = now

        # Upsert answer
        existing = await session.scalar(
            select(SessionAnswer).where(
                SessionAnswer.session_id == session_id,
                SessionAnswer.question_id == question_id,
            )
        )

        is_update = existing is not None
        if existing:
            text_changed = existing.answer != answer_text
            image_keys_changed = self._sync_answer_image_keys(
                existing, normalized_image_keys
            )
            existing.answer = answer_text
            existing.answered_at = now
            if text_changed or image_keys_changed:
                # Re-grade if MCQ
                if question.type == "mcq":
                    self._grade_mcq(existing, question)
                else:
                    # Reset grading for updated short answer
                    logger.info(
                        "Resetting grading for short answer: session=%s question=%s (answer updated)",
                        session_id,
                        question_id,
                    )
                    existing.is_correct = None
                    existing.score = None
                    existing.earned_marks = None
                    existing.feedback = None
                    existing.graded_at = None
            sa = existing
        else:
            sa = SessionAnswer(
                session_id=session_id,
                question_id=question_id,
                answer=answer_text,
                image_key=normalized_image_keys[0] if normalized_image_keys else None,
                image_keys=normalized_image_keys or [],
                answered_at=now,
            )
            if question.type == "mcq":
                self._grade_mcq(sa, question)
            session.add(sa)

        await session.commit()
        await session.refresh(sa)
        if sa.graded_at is not None:
            await rollup_session_graded_marks(session, session_id)
            await session.commit()

        logger.info(
            "Answer saved: session=%s question=%s type=%s update=%s graded=%s",
            session_id,
            question_id,
            question.type,
            is_update,
            sa.graded_at is not None,
        )

        if question.type == "mcq" and sa.graded_at is not None:
            mcq_note = self._build_mcq_feedback_note(sa, question)
            if mcq_note:
                await self._feedback.save_notes(
                    user_id=user_id,
                    source_type="test",
                    source_session_id=session_id,
                    source_answer_id=sa.id,
                    notes=[mcq_note],
                )

        return sa

    async def save_diagram_answer(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        image_key: str,
        *,
        session: AsyncSession | None = None,
    ) -> SessionAnswer:
        """Save an uploaded image key as the answer for a diagram question."""
        logger.info(
            "save_diagram_answer session=%s question=%s image_key=%s",
            session_id, question_id, image_key,
        )
        if session is not None:
            return await self._save_diagram_answer_impl(
                session, session_id, user_id, question_id, image_key
            )
        async with self._session_factory() as session:
            return await self._save_diagram_answer_impl(
                session, session_id, user_id, question_id, image_key
            )

    async def _save_diagram_answer_impl(
        self,
        session: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        image_key: str,
    ) -> SessionAnswer:
        # Lock the parent test_sessions row to serialize concurrent
        # save / submit calls and avoid deadlocks on the
        # session_answers <-> test_sessions update pair.
        test_session = await session.scalar(
            select(TestSession).where(TestSession.id == session_id).with_for_update()
        )
        if not test_session or test_session.user_id != user_id:
            raise SessionServiceError("Session not found")
        if test_session.status not in ("not_started", "active"):
            raise SessionServiceError(
                f"Cannot save answers (status={test_session.status})"
            )

        question = await session.get(TestQuestion, question_id)
        if not question or question.template_id != test_session.template_id:
            raise SessionServiceError("Question does not belong to this template")
        if question.type == "mcq":
            raise SessionServiceError(
                "Image attachments are not supported for MCQ questions"
            )

        now = datetime.now(timezone.utc)

        if test_session.status == "not_started":
            test_session.status = "active"
            test_session.started_at = now

        existing = await session.scalar(
            select(SessionAnswer).where(
                SessionAnswer.session_id == session_id,
                SessionAnswer.question_id == question_id,
            )
        )
        if existing:
            keys = list(existing.image_keys or [])
            if image_key not in keys:
                keys.append(image_key)
            existing.image_keys = keys
            existing.image_key = keys[0]
            existing.answered_at = now
            existing.graded_at = None
            existing.earned_marks = None
            existing.score = None
            existing.is_correct = None
            existing.feedback = None
            existing.recommendations = None
            sa = existing
        else:
            sa = SessionAnswer(
                session_id=session_id,
                question_id=question_id,
                answer="",
                image_key=image_key,
                image_keys=[image_key],
                answered_at=now,
            )
            session.add(sa)

        await session.commit()
        await session.refresh(sa)
        return sa

    async def set_question_skipped(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        skipped: bool,
        *,
        session: AsyncSession | None = None,
    ) -> SessionAnswer:
        """Mark a question as skipped or unskipped within a session.

        Skipped questions are excluded from total_marks and earned_marks at
        submission time — as if the question never existed for this session.
        """
        if session is not None:
            return await self._set_question_skipped_impl(
                session, session_id, user_id, question_id, skipped
            )
        async with self._session_factory() as session:
            return await self._set_question_skipped_impl(
                session, session_id, user_id, question_id, skipped
            )

    async def _set_question_skipped_impl(
        self,
        session: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        skipped: bool,
    ) -> SessionAnswer:
        # Lock the parent test_sessions row to serialize concurrent
        # save / submit calls and avoid deadlocks on the
        # session_answers <-> test_sessions update pair.
        test_session = await session.scalar(
            select(TestSession).where(TestSession.id == session_id).with_for_update()
        )
        if not test_session or test_session.user_id != user_id:
            raise SessionServiceError("Session not found")
        if test_session.status not in ("not_started", "active"):
            raise SessionServiceError(
                f"Cannot change skip state (status={test_session.status})"
            )

        question = await session.get(TestQuestion, question_id)
        if not question or question.template_id != test_session.template_id:
            raise SessionServiceError("Question does not belong to this template")

        now = datetime.now(timezone.utc)
        if test_session.status == "not_started":
            test_session.status = "active"
            test_session.started_at = now

        existing = await session.scalar(
            select(SessionAnswer).where(
                SessionAnswer.session_id == session_id,
                SessionAnswer.question_id == question_id,
            )
        )
        if existing:
            existing.is_skipped = skipped
            sa = existing
        else:
            sa = SessionAnswer(
                session_id=session_id,
                question_id=question_id,
                answer="",
                answered_at=now,
                is_skipped=skipped,
            )
            session.add(sa)

        await session.commit()
        await session.refresh(sa)
        return sa

    async def regrade_answer(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> None:
        """Reset graded_at and re-trigger vision grading for an image answer."""
        async with self._session_factory() as session:
            test_session = await session.get(TestSession, session_id)
            if not test_session or test_session.user_id != user_id:
                raise SessionServiceError("Session not found")
            if test_session.status not in ("not_started", "active"):
                raise SessionServiceError(
                    f"Cannot regrade (status={test_session.status})"
                )
            sa = await session.scalar(
                select(SessionAnswer).where(
                    SessionAnswer.session_id == session_id,
                    SessionAnswer.question_id == question_id,
                )
            )
            if not sa:
                raise SessionServiceError("Answer not found")
            if not (sa.image_key or sa.image_keys):
                raise SessionServiceError("Answer has no images to regrade")
            sa.graded_at = None
            sa.earned_marks = None
            sa.score = None
            sa.is_correct = None
            sa.feedback = None
            sa.recommendations = None
            await session.commit()

    async def grade_single_answer(
        self,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> None:
        """Grade a single LLM-graded answer in isolation (no session status changes)."""
        logger.info(
            "grade_single_answer started: session=%s question=%s",
            session_id,
            question_id,
        )
        async with self._session_factory() as session:
            sa = await session.scalar(
                select(SessionAnswer).where(
                    SessionAnswer.session_id == session_id,
                    SessionAnswer.question_id == question_id,
                )
            )
            if not sa or sa.graded_at is not None:
                logger.info(
                    "grade_single_answer skipped: session=%s question=%s (already graded or not found)",
                    session_id,
                    question_id,
                )
                return
            if sa.is_skipped:
                logger.info(
                    "grade_single_answer skipped: session=%s question=%s (user skipped)",
                    session_id,
                    question_id,
                )
                return

            has_text = bool(sa.answer and sa.answer.strip())
            has_image = bool(sa.image_key or sa.image_keys)
            if not has_text and not has_image:
                sa.earned_marks = 0
                sa.score = 0.0
                sa.graded_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    "grade_single_answer skipped: session=%s question=%s (empty answer)",
                    session_id,
                    question_id,
                )
                return

            question = await session.get(TestQuestion, question_id)
            is_vision_gradeable = (
                question is not None
                and question.type != "mcq"
                and sa.image_key is not None
            )
            if not question or (
                not self._requires_llm_grading(question.type, is_unsupported=question.is_unsupported)
                and not is_vision_gradeable
            ):
                logger.info(
                    "grade_single_answer skipped: session=%s question=%s (not gradeable: type=%s is_unsupported=%s image_key=%s)",
                    session_id,
                    question_id,
                    question.type if question else None,
                    question.is_unsupported if question else None,
                    sa.image_key if sa else None,
                )
                return

            test_session = await session.get(TestSession, session_id)
            user_id = test_session.user_id if test_session else None

            await self._grade_one(question, sa, user_id=user_id, session_id=session_id)
            try:
                await session.commit()
            except StaleDataError:
                logger.info(
                    "grade_single_answer aborted (answer re-submitted): session=%s question=%s",
                    session_id,
                    question_id,
                )
                return
            logger.info(
                "grade_single_answer done: session=%s question=%s earned=%s/%s score=%.2f",
                session_id,
                question_id,
                sa.earned_marks,
                question.points,
                sa.score or 0.0,
            )

    def _grade_mcq(self, answer: SessionAnswer, question: TestQuestion) -> None:
        """Instantly grade an MCQ answer."""
        try:
            selected = int(answer.answer)
            answer.is_correct = selected == question.correct_option_index
        except (ValueError, TypeError):
            answer.is_correct = False
        answer.score = 1.0 if answer.is_correct else 0.0
        answer.earned_marks = question.points if answer.is_correct else 0
        answer.graded_at = datetime.now(timezone.utc)
        logger.info(
            "MCQ graded: question=%s selected=%s correct=%s earned=%s/%s",
            question.id,
            answer.answer,
            answer.is_correct,
            answer.earned_marks,
            question.points,
        )

    @staticmethod
    def _build_mcq_feedback_note(
        answer: SessionAnswer,
        question: TestQuestion,
    ) -> dict | None:
        """Build a programmatic feedback note for a wrong MCQ answer."""
        if answer.is_correct:
            return None
        if not answer.answer or not str(answer.answer).strip():
            return None
        try:
            selected_idx = int(answer.answer)
            if selected_idx < 0:  # -1 means no option was selected
                return None
            selected_text = (
                question.options[selected_idx]
                if question.options and 0 <= selected_idx < len(question.options)
                else f"option {answer.answer}"
            )
        except (ValueError, TypeError):
            selected_text = answer.answer
        correct_text = ""
        if question.options and question.correct_option_index is not None:
            try:
                correct_text = question.options[question.correct_option_index]
            except (IndexError, TypeError):
                pass
        question_text = question.question[:200]
        mistake = (
            f"In the question \"{question_text}\", you selected '{selected_text}', which is incorrect."
        )
        if correct_text:
            mistake += f" The correct answer was '{correct_text}'."
        correction = f"The correct answer is '{correct_text}'."
        if question.model_answer:
            correction = f"{correction} {question.model_answer}"
        return {
            "severity": "critical",
            "topic": question_text,
            "mistake": mistake,
            "correction": correction.strip(),
        }

    # ── Check answer ──────────────────────────────────────────────────

    async def check_answer(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_text: str,
        image_keys: list[str] | None = None,
    ) -> dict:
        """Check a single answer: auto-grade MCQ, LLM-grade short answer.

        Saves the answer and returns grading result with feedback.
        """
        async with self._session_factory() as session:
            test_session = await session.get(TestSession, session_id)
            if not test_session or test_session.user_id != user_id:
                raise SessionServiceError("Session not found")
            if test_session.status not in ("not_started", "active"):
                raise SessionServiceError(
                    f"Cannot check answers (status={test_session.status})"
                )

            question = await session.get(TestQuestion, question_id)
            if not question or question.template_id != test_session.template_id:
                raise SessionServiceError("Question does not belong to this template")
            normalized_image_keys = self._normalize_image_keys(image_keys)
            if question.type == "mcq" and normalized_image_keys:
                raise SessionServiceError(
                    "Image attachments are not supported for MCQ questions"
                )

            now = datetime.now(timezone.utc)

            # Transition not_started → active
            if test_session.status == "not_started":
                test_session.status = "active"
                test_session.started_at = now

            # Upsert answer
            existing = await session.scalar(
                select(SessionAnswer).where(
                    SessionAnswer.session_id == session_id,
                    SessionAnswer.question_id == question_id,
                )
            )

            if existing:
                sa = existing
                sa.answer = answer_text
                self._sync_answer_image_keys(sa, normalized_image_keys)
                sa.answered_at = now
            else:
                sa = SessionAnswer(
                    session_id=session_id,
                    question_id=question_id,
                    answer=answer_text,
                    image_key=normalized_image_keys[0] if normalized_image_keys else None,
                    image_keys=normalized_image_keys or [],
                    answered_at=now,
                )
                session.add(sa)

            if question.type == "mcq":
                self._grade_mcq(sa, question)
                await session.commit()
                await session.refresh(sa)
                await rollup_session_graded_marks(session, session_id)
                await session.commit()
                await session.refresh(sa)
                # Save feedback note for wrong MCQ
                mcq_note = self._build_mcq_feedback_note(sa, question)
                if mcq_note:
                    await self._feedback.save_notes(
                        user_id=user_id,
                        source_type="test",
                        source_session_id=session_id,
                        source_answer_id=sa.id,
                        notes=[mcq_note],
                    )
                # Emit mastery evidence for this inline answer
                await self._emit_inline_evidence(
                    session, test_session, question, sa, user_id
                )
                return {
                    "question_id": question.id,
                    "type": "mcq",
                    "answer": sa.answer,
                    "answered_at": sa.answered_at,
                    "graded_at": sa.graded_at,
                    "is_correct": sa.is_correct,
                    "earned_marks": sa.earned_marks,
                    "total_marks": question.points,
                    "score": sa.score,
                    "model_answer": question.model_answer,
                    "correct_option_index": question.correct_option_index,
                    "feedback": None,
                    "recommendations": None,
                }
            else:
                # Short answer — grade via LLM
                await self._grade_one(
                    question,
                    sa,
                    user_id=user_id,
                    session_id=session_id,
                )
                await session.commit()
                await session.refresh(sa)
                await rollup_session_graded_marks(session, session_id)
                await session.commit()
                await session.refresh(sa)
                # Emit mastery evidence for this inline answer
                await self._emit_inline_evidence(
                    session, test_session, question, sa, user_id
                )
                return {
                    "question_id": question.id,
                    "type": "short",
                    "answer": sa.answer,
                    "answered_at": sa.answered_at,
                    "graded_at": sa.graded_at,
                    "is_correct": sa.is_correct,
                    "earned_marks": sa.earned_marks,
                    "total_marks": question.points,
                    "score": sa.score,
                    "model_answer": question.model_answer,
                    "correct_option_index": None,
                    "feedback": sa.feedback,
                    "recommendations": sa.recommendations,
                }

    # ── Inline evidence ─────────────────────────────────────────────────

    async def _emit_inline_evidence(
        self,
        db: AsyncSession,
        test_session: TestSession,
        question: TestQuestion,
        answer: SessionAnswer,
        user_id: uuid.UUID,
    ) -> None:
        """Emit a single mastery evidence event for an inline quiz answer.

        Called after each check_answer so mastery updates in real-time.
        Only applies to inline_quiz templates.
        """
        template = await db.get(TestTemplate, test_session.template_id)
        if not template or template.type != "inline_quiz":
            return

        from src.mastery.emitters import _get_node_id_for_lesson
        from src.mastery.service import (
            emit_evidence_events,
            recalculate_mastery,
        )

        if not template.lesson_id:
            return

        node_ids = question.node_ids or template.node_ids or []
        if not node_ids:
            node_id = await _get_node_id_for_lesson(db, template.lesson_id)
            if node_id:
                node_ids = [node_id]

        if not node_ids:
            return

        source_type = "inline_mcq" if question.type == "mcq" else "inline_short"
        item_id = question.item_id or f"q_{question.id}"

        if question.type == "mcq":
            score = 1.0 if answer.is_correct else 0.0
        else:
            score = (
                (answer.earned_marks / question.points)
                if question.points and answer.earned_marks is not None
                else 0.0
            )

        for node_id in node_ids:
            await emit_evidence_events(
                db=db,
                user_id=user_id,
                node_id=node_id,
                source_type=source_type,
                source_id=template.id,
                attempt_id=test_session.id,
                items=[{"item_id": item_id, "score": score}],
                invalidate_previous=False,  # don't invalidate — each question is independent
            )
            await recalculate_mastery(db, user_id, node_id)

        await db.commit()

    # ── Submit ──────────────────────────────────────────────────────────

    async def submit_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        final_answers: list[dict] | None = None,
    ) -> tuple[TestSession, list[uuid.UUID]]:
        """Finalize a session. Returns (session, ungraded_question_ids)."""
        async with self._session_factory() as session:
            # Lock the parent test_sessions row up front so concurrent
            # save_answer calls serialize behind us and we never deadlock
            # on the session_answers <-> test_sessions update pair.
            test_session = await session.scalar(
                select(TestSession)
                .where(TestSession.id == session_id)
                .options(
                    selectinload(TestSession.answers),
                    selectinload(TestSession.template).selectinload(
                        TestTemplate.questions
                    ),
                )
                .with_for_update()
            )
            if not test_session or test_session.user_id != user_id:
                raise SessionServiceError("Session not found")
            if test_session.status == "grading":
                # Idempotent resubmit while grading: return pending LLM-graded question ids
                # so caller can re-trigger background grading if needed.
                ungraded_ids = list(
                    await session.scalars(
                        select(SessionAnswer.question_id)
                        .join(TestQuestion, TestQuestion.id == SessionAnswer.question_id)
                        .where(
                            SessionAnswer.session_id == session_id,
                            SessionAnswer.graded_at.is_(None),
                            TestQuestion.template_id == test_session.template_id,
                            TestQuestion.type.in_(("short", "open")),
                        )
                    )
                )
                if not ungraded_ids:
                    # Self-heal sessions that are effectively graded but still marked "grading".
                    total_earned = sum(a.earned_marks or 0 for a in test_session.answers)
                    test_session.earned_marks = total_earned
                    test_session.score = (
                        total_earned / test_session.total_marks
                        if test_session.total_marks
                        else 0.0
                    )
                    test_session.graded_at = test_session.graded_at or datetime.now(
                        timezone.utc
                    )
                    test_session.status = "graded"
                    await session.commit()
                    await session.refresh(test_session)
                return test_session, ungraded_ids
            if test_session.status not in ("not_started", "active"):
                raise SessionServiceError(
                    f"Session cannot be submitted (status={test_session.status})"
                )

            now = datetime.now(timezone.utc)

            # Build answer lookup from already-loaded collection to avoid per-answer queries
            answer_map: dict[uuid.UUID, SessionAnswer] = {
                a.question_id: a for a in test_session.answers
            }

            # Save any remaining answers (skip unchanged ones to avoid resetting grading)
            mcq_notes_pending: list[tuple[SessionAnswer, TestQuestion]] = []
            if final_answers:
                # Batch-fetch all referenced questions in one query instead of N queries
                fa_qids = [fa["question_id"] for fa in final_answers]
                q_rows = await session.scalars(
                    select(TestQuestion).where(TestQuestion.id.in_(fa_qids))
                )
                question_batch: dict[uuid.UUID, TestQuestion] = {q.id: q for q in q_rows}

                for fa in final_answers:
                    qid = fa["question_id"]
                    question = question_batch.get(qid)
                    if not question or question.template_id != test_session.template_id:
                        continue
                    normalized_image_keys = self._normalize_image_keys(
                        fa.get("image_keys")
                    )
                    if question.type == "mcq" and normalized_image_keys:
                        raise SessionServiceError(
                            "Image attachments are not supported for MCQ questions"
                        )

                    existing = answer_map.get(qid)
                    if existing:
                        # Skip if the combined answer hasn't changed (already auto-saved)
                        image_keys_changed = self._sync_answer_image_keys(
                            existing, normalized_image_keys
                        )
                        if existing.answer == fa["answer"] and not image_keys_changed:
                            if question.type == "mcq" and existing.graded_at is None:
                                self._grade_mcq(existing, question)
                                mcq_notes_pending.append((existing, question))
                            continue
                        existing.answer = fa["answer"]
                        existing.answered_at = now
                        if question.type == "mcq":
                            self._grade_mcq(existing, question)
                            mcq_notes_pending.append((existing, question))
                        else:
                            existing.is_correct = None
                            existing.score = None
                            existing.earned_marks = None
                            existing.feedback = None
                            existing.recommendations = None
                            existing.graded_at = None
                    else:
                        sa = SessionAnswer(
                            session_id=session_id,
                            question_id=qid,
                            answer=fa["answer"],
                            image_key=(
                                normalized_image_keys[0]
                                if normalized_image_keys
                                else None
                            ),
                            image_keys=normalized_image_keys or [],
                            answered_at=now,
                        )
                        if question.type == "mcq":
                            self._grade_mcq(sa, question)
                            mcq_notes_pending.append((sa, question))
                        session.add(sa)

                await session.flush()
                await session.refresh(test_session)

            # Save feedback notes for wrong MCQs from final answers
            for ans, q in mcq_notes_pending:
                mcq_note = self._build_mcq_feedback_note(ans, q)
                if mcq_note:
                    await self._feedback.save_notes(
                        user_id=user_id,
                        source_type="test",
                        source_session_id=session_id,
                        source_answer_id=ans.id,
                        notes=[mcq_note],
                    )

            # Compute results
            test_session.submitted_at = now
            if test_session.status == "not_started":
                test_session.started_at = now

            # Check for ungraded LLM-graded answers
            answers = list(
                await session.scalars(
                    select(SessionAnswer).where(SessionAnswer.session_id == session_id)
                )
            )

            # Get all template questions to find ungraded LLM-graded answers
            questions = list(
                await session.scalars(
                    select(TestQuestion).where(
                        TestQuestion.template_id == test_session.template_id
                    )
                )
            )
            question_map = {q.id: q for q in questions}

            # Skipped questions are excluded from totals as if they never existed.
            skipped_qids = {a.question_id for a in answers if a.is_skipped}
            effective_total = sum(
                q.points or 0
                for q in questions
                if q.id not in skipped_qids
            )
            test_session.total_marks = effective_total

            has_short = False
            ungraded_ids = []
            mcq_earned = 0

            for ans in answers:
                if ans.is_skipped:
                    continue
                q = question_map.get(ans.question_id)
                if not q:
                    continue
                has_vision_image = q.type != "mcq" and bool(ans.image_key or ans.image_keys)
                needs_llm_grade = (
                    self._requires_llm_grading(q.type, is_unsupported=q.is_unsupported)
                    or has_vision_image
                )
                if needs_llm_grade and ans.graded_at is None:
                    has_short = True
                    ungraded_ids.append(q.id)
                elif ans.earned_marks is not None:
                    mcq_earned += ans.earned_marks

            if has_short:
                test_session.status = "grading"
            else:
                test_session.earned_marks = mcq_earned
                test_session.score = (
                    mcq_earned / effective_total if effective_total else 0.0
                )
                test_session.graded_at = now
                test_session.status = "graded"

            await session.commit()
            await session.refresh(test_session)
            return test_session, ungraded_ids

    # ── Grading (called by worker) ──────────────────────────────────────

    async def grade_session(self, session_id: uuid.UUID) -> None:
        """Grade all ungraded short-answer questions in a session.

        Individual grade_single_answer background tasks may still be in-flight.
        We wait for them to finish (poll DB), then grade any that remain,
        and finalize the session totals.
        """
        if session_id in self._active_grade_sessions:
            logger.info("grade_session: session %s is already running", session_id)
            return
        self._active_grade_sessions.add(session_id)
        try:
            # Wait for in-flight grade_single_answer tasks to commit
            ungraded_count = await self._wait_for_individual_grading(session_id)
            logger.info(
                "grade_session: %d still-ungraded answers after waiting for session %s",
                ungraded_count,
                session_id,
            )

            async with self._session_factory() as session:
                test_session = await session.get(
                    TestSession,
                    session_id,
                    options=[
                        selectinload(TestSession.answers).selectinload(
                            SessionAnswer.question
                        )
                    ],
                )
                if not test_session:
                    logger.error("Session %s not found for grading", session_id)
                    return

                # Grade any answers that individual tasks missed or didn't handle.
                # Skipped answers never go to the LLM.
                tasks = []
                for ans in test_session.answers:
                    if ans.is_skipped or ans.graded_at is not None:
                        continue
                    has_text = bool(ans.answer and ans.answer.strip())
                    has_image = bool(ans.image_key or ans.image_keys)
                    if not has_text and not has_image:
                        ans.earned_marks = 0
                        ans.score = 0.0
                        ans.graded_at = datetime.now(timezone.utc)
                        continue
                    is_vision = (
                        ans.question.type != "mcq"
                        and ans.image_key is not None
                    )
                    if self._requires_llm_grading(ans.question.type, is_unsupported=ans.question.is_unsupported) or is_vision:
                        tasks.append(
                            self._grade_one(
                                ans.question,
                                ans,
                                user_id=test_session.user_id,
                                session_id=session_id,
                            )
                        )

                if tasks:
                    logger.info(
                        "grade_session: grading %d remaining answers for session %s",
                        len(tasks),
                        session_id,
                    )
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Recompute totals excluding skipped questions ("never existed").
                skipped_qids = {
                    a.question_id for a in test_session.answers if a.is_skipped
                }
                template_questions = list(
                    await session.scalars(
                        select(TestQuestion).where(
                            TestQuestion.template_id == test_session.template_id
                        )
                    )
                )
                effective_total = sum(
                    q.points or 0
                    for q in template_questions
                    if q.id not in skipped_qids
                )
                total_earned = sum(
                    (ans.earned_marks or 0)
                    for ans in test_session.answers
                    if not ans.is_skipped
                )

                test_session.total_marks = effective_total
                test_session.earned_marks = total_earned
                test_session.score = (
                    total_earned / effective_total if effective_total else 0.0
                )
                test_session.graded_at = datetime.now(timezone.utc)
                test_session.status = "graded"

                await session.commit()
                await self._log_test_graded_activity(
                    session,
                    test_session,
                    template_questions,
                )

                # Emit mastery evidence events after grading
                try:
                    from src.mastery.emitters import emit_test_session_events

                    async with self._session_factory() as mastery_session:
                        await emit_test_session_events(mastery_session, session_id)
                except Exception:
                    logger.exception(
                        "Failed to emit mastery events for session %s", session_id
                    )
        finally:
            self._active_grade_sessions.discard(session_id)

    async def _log_test_graded_activity(
        self,
        session: AsyncSession,
        test_session: TestSession,
        template_questions: list[TestQuestion],
    ) -> None:
        if self._activity_service is None:
            return
        try:
            template = await session.get(TestTemplate, test_session.template_id)
            answers = list(test_session.answers or [])
            skipped_count = sum(1 for answer in answers if answer.is_skipped)
            answered_count = sum(
                1
                for answer in answers
                if not answer.is_skipped
                and (
                    bool((answer.answer or "").strip())
                    or bool(answer.image_key or answer.image_keys)
                )
            )
            score_percent = (
                float(test_session.score) * 100
                if test_session.score is not None
                else None
            )
            self._activity_service.log_event_fire_and_forget(
                ActivityEventInput(
                    user_id=test_session.user_id,
                    event_type="test_graded",
                    event_group="test",
                    entity_type="test_session",
                    entity_id=test_session.id,
                    lesson_id=getattr(template, "lesson_id", None),
                    test_session_id=test_session.id,
                    metadata={
                        "answered_count": answered_count,
                        "skipped_count": skipped_count,
                        "total_questions": len(template_questions),
                        "earned_marks": test_session.earned_marks,
                        "total_marks": test_session.total_marks,
                        "score_percent": score_percent,
                    },
                    replay_payload=test_graded_replay_payload(
                        test_session=test_session,
                        template_questions=template_questions,
                    ),
                )
            )
        except Exception:
            logger.exception("Failed to enqueue test_graded activity for %s", test_session.id)

    async def _wait_for_individual_grading(
        self,
        session_id: uuid.UUID,
        max_wait: int = 60,
        interval: float = 1.5,
    ) -> int:
        """Poll DB until all LLM-graded individual grading tasks finish.

        Returns the number of still-ungraded LLM-graded answers (0 = all done).
        """
        elapsed = 0.0
        while elapsed < max_wait:
            async with self._session_factory() as session:
                rows = list(
                    await session.scalars(
                        select(SessionAnswer).where(
                            SessionAnswer.session_id == session_id
                        )
                    )
                )
                ungraded_rows = [r for r in rows if r.graded_at is None]
                if not ungraded_rows:
                    return 0
                question_ids = [r.question_id for r in ungraded_rows]
                vision_question_ids = {r.question_id for r in ungraded_rows if r.image_key is not None}
                # Include text-graded types and vision-gradeable diagram questions
                all_questions = list(
                    await session.scalars(
                        select(TestQuestion).where(TestQuestion.id.in_(question_ids))
                    )
                )
                questions = [
                    q for q in all_questions
                    if q.type in ("short", "open") or q.id in vision_question_ids
                ]
                if not questions:
                    return 0
            await asyncio.sleep(interval)
            elapsed += interval
        return len(questions)

    async def _grade_one(
        self,
        question: TestQuestion,
        answer: SessionAnswer,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> None:
        """Grade a single question via LLM (text or vision/diagram)."""
        # For diagram questions the student's answer lives in the attached
        # image, not in the `answer` text field. Tell the grader explicitly so
        # it doesn't read "Student's answer: " as "no answer provided".
        all_image_keys = list(answer.image_keys or ([answer.image_key] if answer.image_key else []))
        is_vision_mode = bool(all_image_keys and self._s3)
        typed_answer = (answer.answer or "").strip()
        logger.info(
            "LLM grading started: question=%s points=%s answer_length=%d image_count=%d typed_answer_present=%s",
            question.id,
            question.points,
            len(typed_answer),
            len(all_image_keys),
            bool(typed_answer),
        )
        if is_vision_mode and typed_answer:
            student_answer_text = (
                "Student typed answer:\n"
                f"{typed_answer}\n\n"
                "The student also attached image(s). Read the image(s) carefully "
                "and grade the typed text and attached image(s) together as one "
                "student answer against the mark scheme."
            )
        elif is_vision_mode:
            student_answer_text = (
                "[The student's handwritten or drawn answer is shown in the "
                "attached image(s). Read the image(s) carefully and grade what is drawn "
                "against the mark scheme. Treat the image(s) as the student's answer.]"
            )
        else:
            student_answer_text = answer.answer
        messages = build_grading_messages(
            question=question.question,
            points=question.points,
            mark_scheme=question.mark_scheme,
            model_answer=question.model_answer or "",
            student_answer=student_answer_text,
            pm=self._pm,
        )

        # Vision branch: embed all diagram images as base64 so the LLM can see them.
        if is_vision_mode:
            import base64
            import io as _io
            from PIL import Image as _Image
            from pillow_heif import register_heif_opener as _register_heif
            _register_heif()

            image_content = []
            for key in all_image_keys:
                image_bytes = await self._s3.download_bytes(key)
                original_size = len(image_bytes)
                # Resize to max 1600px and re-encode as JPEG to keep payloads
                # small enough for the LLM API (camera photos can be 5-8 MB).
                try:
                    img = _Image.open(_io.BytesIO(image_bytes))
                    img = img.convert("RGB")
                    img.thumbnail((1600, 1600), _Image.LANCZOS)
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    image_bytes = buf.getvalue()
                    mime = "image/jpeg"
                except Exception as _resize_err:
                    logger.warning(
                        "Image resize failed for %s: %s — sending original",
                        key, _resize_err,
                    )
                    ext = key.rsplit(".", 1)[-1].lower()
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                            "webp": "image/webp", "heic": "image/heic"}.get(ext, "image/jpeg")
                data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
                image_content.append({"type": "image_url", "image_url": {"url": data_url}})
                logger.info(
                    "vision branch active: question=%s image_key=%s original=%d bytes resized=%d bytes",
                    question.id, key, original_size, len(image_bytes),
                )
            user_msg = messages[-1]
            if isinstance(user_msg["content"], str):
                user_msg["content"] = image_content + [
                    {"type": "text", "text": user_msg["content"]},
                ]
        else:
            logger.info(
                "vision branch skipped: question=%s image_key=%s s3=%s",
                question.id, answer.image_key, self._s3 is not None,
            )

        import json
        import re

        _MAX_GRADE_ATTEMPTS = 2
        try:
            data: dict[str, Any] | None = None
            for _attempt in range(_MAX_GRADE_ATTEMPTS):
                raw, _usage = await self._get_llm().chat_complete(messages)
                if self._usage_service and user_id:
                    self._usage_service.log_usage_fire_and_forget(
                        user_id=user_id, feature="test_grading", usage=_usage,
                    )
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\s*", "", clean)
                    clean = re.sub(r"\s*```\s*$", "", clean)
                try:
                    data = json.loads(clean)
                    break
                except json.JSONDecodeError:
                    logger.warning(
                        "Grading JSON parse failed for question %s (attempt %d), raw=%r",
                        question.id, _attempt + 1, raw[:200],
                    )
            if data is None:
                raise ValueError(f"LLM returned unparseable response after {_MAX_GRADE_ATTEMPTS} attempts")

            earned = min(int(data.get("earned_marks", 0)), question.points)
            earned = max(earned, 0)

            answer.earned_marks = earned
            answer.score = earned / question.points if question.points else 0.0
            answer.is_correct = earned == question.points
            answer.feedback = data.get("feedback", "")
            answer.recommendations = data.get("recommendations", "")
            answer.graded_at = datetime.now(timezone.utc)
            logger.info(
                "LLM grading done: question=%s earned=%s/%s correct=%s feedback=%r",
                question.id,
                earned,
                question.points,
                answer.is_correct,
                (answer.feedback or "")[:120],
            )

            # Save feedback notes for mistakes detected during grading
            # Skip entirely if the student left the answer blank
            raw_notes = data.get("feedback_notes", [])
            if raw_notes and user_id and session_id and (answer.answer.strip() or all_image_keys):
                await self._feedback.save_notes(
                    user_id=user_id,
                    source_type="test",
                    source_session_id=session_id,
                    source_answer_id=answer.id,
                    notes=raw_notes,
                )
        except Exception as exc:
            logger.error("Grading failed for question %s: %s", question.id, exc)
            answer.earned_marks = 0
            answer.score = 0.0
            answer.is_correct = False
            answer.feedback = "Grading failed — please contact support."
            answer.recommendations = ""
            answer.graded_at = datetime.now(timezone.utc)

    # ── Reads ───────────────────────────────────────────────────────────

    async def get_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> TestSession | None:
        async def _run(ses: AsyncSession) -> TestSession | None:
            test_session = await ses.get(
                TestSession,
                session_id,
                options=[
                    selectinload(TestSession.answers),
                    selectinload(TestSession.ai_hint_usages),
                    selectinload(TestSession.template).selectinload(
                        TestTemplate.questions
                    ),
                ],
            )
            if not test_session or test_session.user_id != user_id:
                return None
            return test_session

        if session is not None:
            return await _run(session)
        async with self._session_factory() as session:
            return await _run(session)

    async def try_acquire_hint_inflight_lock(
        self,
        session: AsyncSession,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> bool:
        """Serialize concurrent hint requests for the same (session, question).

        Uses PostgreSQL ``pg_try_advisory_xact_lock``; released when this DB session
        ends (after the SSE stream completes). Prevents double LLM cost on double-submit.
        """
        k = hint_advisory_lock_key(session_id, question_id)
        row = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(CAST(:k AS BIGINT))"),
            {"k": k},
        )
        return bool(row)

    async def is_ai_hint_consumed(
        self,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
        *,
        session: AsyncSession,
    ) -> bool:
        row = await session.scalar(
            select(SessionAiHintUsage.id).where(
                SessionAiHintUsage.session_id == session_id,
                SessionAiHintUsage.question_id == question_id,
            )
        )
        return row is not None

    async def record_ai_hint_consumed(
        self,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Idempotent: unique (session_id, question_id)."""
        async with self._session_factory() as db:
            ts = await db.get(TestSession, session_id)
            if ts is None or ts.user_id != user_id:
                return
            stmt = (
                pg_insert(SessionAiHintUsage)
                .values(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    question_id=question_id,
                )
                .on_conflict_do_nothing(
                    constraint="uq_session_ai_hint_session_question",
                )
            )
            await db.execute(stmt)
            await db.commit()

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        template_id: uuid.UUID | None = None,
        folder_id: uuid.UUID | None = None,
        type: str | None = None,
        lesson_id: uuid.UUID | None = None,
    ) -> list[TestSession]:
        async with self._session_factory() as session:
            stmt = (
                select(TestSession)
                .where(TestSession.user_id == user_id)
                .options(selectinload(TestSession.template))
                .order_by(TestSession.created_at.desc())
            )
            if template_id:
                stmt = stmt.where(TestSession.template_id == template_id)
            needs_join = folder_id or type or lesson_id
            if needs_join:
                stmt = stmt.join(TestTemplate)
                if folder_id:
                    stmt = stmt.where(TestTemplate.folder_id == folder_id)
                if type:
                    stmt = stmt.where(TestTemplate.type == type)
                if lesson_id:
                    stmt = stmt.where(TestTemplate.lesson_id == lesson_id)
                    if not type:
                        stmt = stmt.where(TestTemplate.type != "inline_quiz")
            result = await session.scalars(stmt)
            return list(result)

    async def get_session_status(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        async with self._session_factory() as session:
            test_session = await session.get(TestSession, session_id)
            if not test_session or test_session.user_id != user_id:
                return None
            return {
                "status": test_session.status,
                "earned_marks": test_session.earned_marks,
                "total_marks": test_session.total_marks,
                "score": test_session.score,
            }

    async def abort_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self._session_factory() as session:
            test_session = await session.get(TestSession, session_id)
            if not test_session or test_session.user_id != user_id:
                return False
            if test_session.status not in ("not_started", "active"):
                return False
            test_session.status = "aborted"
            await session.commit()
            return True
