"""Feedback Hub service — saves and queries mistake notes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.feedback.models import FeedbackNote

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"minor", "moderate", "critical"}
_VALID_STATUSES = {"see", "review", "complete"}
_SEVERITY_PRIORITY = {"critical": 2, "moderate": 1, "minor": 0}
_MIN_SAVED_SEVERITY_PRIORITY = _SEVERITY_PRIORITY["moderate"]
_MAX_SAVED_NOTES_PER_CALL = 2
_NORMALIZE_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_NORMALIZE_WS_RE = re.compile(r"\s+")
_TOPIC_SIMILARITY_THRESHOLD = 0.70
_DETAIL_SIMILARITY_THRESHOLD = 0.55


@dataclass(frozen=True)
class _NoteFingerprint:
    topic_norm: str
    mistake_norm: str
    correction_norm: str
    topic_tokens: frozenset[str]
    mistake_tokens: frozenset[str]
    correction_tokens: frozenset[str]


@dataclass(frozen=True)
class _PreparedNote:
    severity: str
    topic: str
    mistake: str
    correction: str
    priority: int
    original_order: int
    fp: _NoteFingerprint


def _normalize_text(value: str) -> str:
    compact = _NORMALIZE_NON_ALNUM_RE.sub(" ", value.lower())
    return _NORMALIZE_WS_RE.sub(" ", compact).strip()


def _tokenize(value: str) -> frozenset[str]:
    return frozenset(token for token in _normalize_text(value).split() if len(token) > 1)


def _token_overlap(lhs: frozenset[str], rhs: frozenset[str]) -> float:
    if not lhs or not rhs:
        return 0.0
    union = lhs | rhs
    if not union:
        return 0.0
    return len(lhs & rhs) / len(union)


def _build_fingerprint(topic: str, mistake: str, correction: str) -> _NoteFingerprint:
    topic_norm = _normalize_text(topic)
    mistake_norm = _normalize_text(mistake)
    correction_norm = _normalize_text(correction)
    return _NoteFingerprint(
        topic_norm=topic_norm,
        mistake_norm=mistake_norm,
        correction_norm=correction_norm,
        topic_tokens=_tokenize(topic),
        mistake_tokens=_tokenize(mistake),
        correction_tokens=_tokenize(correction),
    )


def _is_probable_duplicate(lhs: _NoteFingerprint, rhs: _NoteFingerprint) -> bool:
    if (
        lhs.topic_norm == rhs.topic_norm
        and lhs.mistake_norm == rhs.mistake_norm
        and lhs.correction_norm == rhs.correction_norm
    ):
        return True

    same_topic = lhs.topic_norm == rhs.topic_norm or (
        _token_overlap(lhs.topic_tokens, rhs.topic_tokens) >= _TOPIC_SIMILARITY_THRESHOLD
    )
    if not same_topic:
        return False

    if lhs.correction_norm == rhs.correction_norm:
        return True

    correction_overlap = _token_overlap(lhs.correction_tokens, rhs.correction_tokens)
    if correction_overlap >= _DETAIL_SIMILARITY_THRESHOLD:
        return True

    mistake_overlap = _token_overlap(lhs.mistake_tokens, rhs.mistake_tokens)
    return mistake_overlap >= _DETAIL_SIMILARITY_THRESHOLD


class FeedbackNoteService:
    """Persists and retrieves feedback notes from tests and Feynman sessions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: YandexGPTLLMGateway | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm

    def _get_llm(self) -> YandexGPTLLMGateway:
        if self._llm is None:
            self._llm = YandexGPTLLMGateway()
        return self._llm

    async def _resolve_folder_id(
        self,
        source_type: str,
        source_session_id: uuid.UUID,
        session: AsyncSession,
    ) -> uuid.UUID | None:
        """Return the folder_id for the session, or None if the chain is broken."""
        if source_type == "test":
            from src.learning.tests.models import TestSession, TestTemplate

            ts = await session.get(TestSession, source_session_id)
            if ts is None:
                return None
            tt = await session.get(TestTemplate, ts.template_id)
            return tt.folder_id if tt is not None else None

        if source_type == "feynman":
            from src.learning.models import FeynmanBlock, FeynmanSession, Lesson

            fs = await session.get(FeynmanSession, source_session_id)
            if fs is None:
                return None
            fb = await session.get(FeynmanBlock, fs.feynman_block_id)
            if fb is None:
                return None
            lesson = await session.get(Lesson, fb.lesson_id)
            return lesson.folder_id if lesson is not None else None

        return None

    async def save_notes(
        self,
        user_id: uuid.UUID,
        source_type: str,
        source_session_id: uuid.UUID,
        source_answer_id: uuid.UUID | None,
        notes: list[dict[str, Any]],
    ) -> None:
        """Validate and bulk-insert feedback notes. Silently skips invalid entries."""
        prepared: list[_PreparedNote] = []
        for idx, raw in enumerate(notes):
            severity = raw.get("severity", "")
            topic = raw.get("topic", "")
            mistake = raw.get("mistake", "")
            correction = raw.get("correction", "")

            if severity not in _VALID_SEVERITIES:
                continue
            if _SEVERITY_PRIORITY.get(severity, -1) < _MIN_SAVED_SEVERITY_PRIORITY:
                # Keep feedback hub focused on bigger conceptual mistakes.
                continue
            if not topic or not mistake or not correction:
                continue

            prepared.append(
                _PreparedNote(
                    severity=severity,
                    topic=topic[:500],
                    mistake=mistake,
                    correction=correction,
                    priority=_SEVERITY_PRIORITY[severity],
                    original_order=idx,
                    fp=_build_fingerprint(topic=topic, mistake=mistake, correction=correction),
                )
            )

        if not prepared:
            return

        # Keep strongest notes first, then deduplicate within the incoming batch.
        prepared.sort(key=lambda note: (-note.priority, note.original_order))
        unique_prepared: list[_PreparedNote] = []
        for note in prepared:
            if any(_is_probable_duplicate(note.fp, keep.fp) for keep in unique_prepared):
                continue
            unique_prepared.append(note)

        if not unique_prepared:
            return

        try:
            async with self._session_factory() as session:
                # Dedup: skip if notes already exist for this answer
                if source_answer_id is not None:
                    existing_count = await session.scalar(
                        select(func.count()).where(
                            FeedbackNote.source_answer_id == source_answer_id,
                        )
                    )
                    if existing_count and existing_count > 0:
                        logger.info(
                            "Skipping %d duplicate feedback notes for answer %s",
                            len(unique_prepared),
                            source_answer_id,
                        )
                        return

                existing_rows = (
                    await session.execute(
                        select(
                            FeedbackNote.topic,
                            FeedbackNote.mistake,
                            FeedbackNote.correction,
                        ).where(FeedbackNote.user_id == user_id)
                    )
                ).all()
                existing_fingerprints = [
                    _build_fingerprint(topic=topic, mistake=mistake, correction=correction)
                    for topic, mistake, correction in existing_rows
                ]

                deduped: list[_PreparedNote] = []
                for note in unique_prepared:
                    if any(
                        _is_probable_duplicate(note.fp, existing_fp)
                        for existing_fp in existing_fingerprints
                    ):
                        continue
                    deduped.append(note)

                if not deduped:
                    logger.info(
                        "All feedback notes skipped as duplicates: user=%s source=%s session=%s",
                        user_id,
                        source_type,
                        source_session_id,
                    )
                    return

                folder_id = await self._resolve_folder_id(
                    source_type=source_type,
                    source_session_id=source_session_id,
                    session=session,
                )

                deduped = deduped[:_MAX_SAVED_NOTES_PER_CALL]
                rows = [
                    FeedbackNote(
                        user_id=user_id,
                        source_type=source_type,
                        source_session_id=source_session_id,
                        source_answer_id=source_answer_id,
                        folder_id=folder_id,
                        severity=note.severity,
                        topic=note.topic,
                        mistake=note.mistake,
                        correction=note.correction,
                    )
                    for note in deduped
                ]

                session.add_all(rows)
                await session.commit()
                # Capture note IDs before session closes
                saved_ids = [r.id for r in rows]
            logger.info(
                "Saved %d feedback notes: user=%s source=%s session=%s",
                len(rows),
                user_id,
                source_type,
                source_session_id,
            )
        except Exception:
            logger.exception("Failed to save feedback notes")
            return

        # Eagerly populate review questions in the background so they're
        # ready by the time the student enters the review tab.
        for note_id in saved_ids:
            asyncio.create_task(
                self._generate_review_question_bg(note_id),
                name=f"gen-review-q-{note_id}",
            )

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        source_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FeedbackNote]:
        async with self._session_factory() as session:
            stmt = (
                select(FeedbackNote)
                .where(FeedbackNote.user_id == user_id)
                .order_by(FeedbackNote.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if folder_id is not None:
                stmt = stmt.where(FeedbackNote.folder_id == folder_id)
            if source_type:
                stmt = stmt.where(FeedbackNote.source_type == source_type)
            if status:
                stmt = stmt.where(FeedbackNote.status == status)
            result = await session.scalars(stmt)
            return list(result)

    async def list_for_session(
        self,
        user_id: uuid.UUID,
        source_session_id: uuid.UUID,
    ) -> list[FeedbackNote]:
        async with self._session_factory() as session:
            stmt = (
                select(FeedbackNote)
                .where(
                    FeedbackNote.user_id == user_id,
                    FeedbackNote.source_session_id == source_session_id,
                )
                .order_by(FeedbackNote.created_at.asc())
            )
            result = await session.scalars(stmt)
            return list(result)

    async def get_summary(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        async with self._session_factory() as session:
            stmt = (
                select(FeedbackNote.status, func.count())
                .where(FeedbackNote.user_id == user_id)
                .group_by(FeedbackNote.status)
            )
            if folder_id is not None:
                stmt = stmt.where(FeedbackNote.folder_id == folder_id)
            rows = (await session.execute(stmt)).all()
            counts = {status: cnt for status, cnt in rows}
            total = sum(counts.values())
            return {
                "see": counts.get("see", 0),
                "review": counts.get("review", 0),
                "complete": counts.get("complete", 0),
                "total": total,
            }

    async def _generate_review_question_bg(self, note_id: uuid.UUID) -> None:
        """Background task: populate review_question on a note.

        Test notes  → copy from the original TestQuestion (pure DB read).
        Feynman notes → generate via LLM from the note's topic/mistake/correction.
        If the test FK chain is broken, falls back to LLM generation.
        """
        from src.learning.tests.prompts import build_review_question_messages

        try:
            async with self._session_factory() as session:
                note = await session.get(FeedbackNote, note_id)
                if not note or note.review_question is not None:
                    return

                # Test notes: try pulling from original TestQuestion first
                if note.source_type == "test" and note.source_answer_id:
                    from src.learning.tests.models import SessionAnswer, TestQuestion

                    sa = await session.get(SessionAnswer, note.source_answer_id)
                    if sa:
                        question = await session.get(TestQuestion, sa.question_id)
                        if question:
                            note.review_question = {
                                "question": question.question,
                                "model_answer": question.model_answer or "",
                                "hint": question.hint or "",
                                "points": question.points,
                            }
                            await session.commit()
                            logger.info("Populated review question from TestQuestion for note %s", note_id)
                            return

                # Feynman notes, or test notes with broken FK → generate via LLM
                messages = build_review_question_messages(
                    topic=note.topic,
                    mistake=note.mistake,
                    correction=note.correction,
                )
                raw, _usage = await self._get_llm().chat_complete(messages)
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\s*", "", clean)
                    clean = re.sub(r"\s*```\s*$", "", clean)
                note.review_question = json.loads(clean)
                await session.commit()
                logger.info("Generated review question via LLM for note %s", note_id)
        except Exception:
            logger.exception("Background review-question generation failed for note %s", note_id)

    async def _ensure_review_question(
        self,
        note: FeedbackNote,
        session: AsyncSession,
    ) -> None:
        """Populate review_question on the note if it's still None.

        For test notes we try to pull the original TestQuestion first;
        if the FK chain is broken (deleted session/question) we fall back
        to LLM generation — same path feynman notes always use.
        """
        if note.review_question is not None:
            return

        from src.learning.tests.prompts import build_review_question_messages

        # Try to pull from original TestQuestion for test notes
        if note.source_type == "test" and note.source_answer_id:
            from src.learning.tests.models import SessionAnswer, TestQuestion

            sa = await session.get(SessionAnswer, note.source_answer_id)
            if sa:
                question = await session.get(TestQuestion, sa.question_id)
                if question:
                    note.review_question = {
                        "question": question.question,
                        "model_answer": question.model_answer or "",
                        "hint": question.hint or "",
                        "points": question.points,
                    }
                    return

        # Fallback: generate via LLM from the note's own data
        logger.info(
            "Generating review question via LLM for note %s (source=%s)",
            note.id, note.source_type,
        )
        rq_messages = build_review_question_messages(
            topic=note.topic,
            mistake=note.mistake,
            correction=note.correction,
        )
        raw, _usage = await self._get_llm().chat_complete(rq_messages)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```\s*$", "", clean)
        note.review_question = json.loads(clean)

    async def update_note_status(
        self,
        note_id: uuid.UUID,
        user_id: uuid.UUID,
        new_status: str,
    ) -> FeedbackNote | None:
        """Update the status of a note. Returns None if not found.

        When a note transitions to 'review' we ensure review_question is
        populated so the frontend always has question text to display.
        """
        if new_status not in _VALID_STATUSES:
            return None
        async with self._session_factory() as session:
            note = await session.get(FeedbackNote, note_id)
            if not note or note.user_id != user_id:
                return None

            if new_status == "review" and note.review_question is None:
                await self._ensure_review_question(note, session)

            note.status = new_status
            await session.commit()
            await session.refresh(note)
            return note

    async def answer_note(
        self,
        note_id: uuid.UUID,
        user_id: uuid.UUID,
        answer_text: str,
    ) -> dict[str, Any] | None:
        """Grade the student's answer to a review question.

        Returns None if the note is not found or not owned by the user.
        Raises ValueError if the note is not in "review" status.
        """
        from src.learning.tests.prompts import build_grading_messages

        async with self._session_factory() as session:
            note = await session.get(FeedbackNote, note_id)
            if not note or note.user_id != user_id:
                return None
            if note.status != "review":
                raise ValueError(f"Note status is '{note.status}', expected 'review'")

            # Ensure review_question exists (tries original TestQuestion first,
            # falls back to LLM generation if FK chain is broken)
            await self._ensure_review_question(note, session)
            await session.flush()

            rq = note.review_question
            messages = build_grading_messages(
                question=rq["question"],
                points=rq.get("points", 3),
                mark_scheme=None,
                model_answer=rq.get("model_answer", ""),
                student_answer=answer_text,
            )
            total_marks = rq.get("points", 3)

            # Call LLM to grade
            try:
                raw, _usage = await self._get_llm().chat_complete(messages)
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```(?:json)?\s*", "", clean)
                    clean = re.sub(r"\s*```\s*$", "", clean)
                data = json.loads(clean)
            except Exception:
                logger.exception("Failed to grade answer for note %s", note_id)
                raise

            earned = max(0, min(int(data.get("earned_marks", 0)), total_marks))
            is_correct = earned >= total_marks

            await session.commit()

        return {
            "is_correct": is_correct,
            "earned_marks": earned,
            "total_marks": total_marks,
            "feedback": data.get("feedback", ""),
            "recommendations": data.get("recommendations", ""),
        }
