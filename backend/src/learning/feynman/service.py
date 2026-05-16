"""Standard Feynman technique pipeline — unlimited iterations, theme-score tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import and_, select

from src.core.llm_usage import UsageInfo
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.feedback.service import FeedbackNoteService
from src.learning.feynman.prompts import (
    build_evaluator_messages,
    build_feedback_messages,
    build_opening_messages,
)
from src.learning.models import FeynmanBlock, FeynmanSession
from src.learning.parser import LessonTheme, parse_lesson_themes
from src.learning.service import LearningService
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)

# Scores are 0–5 per theme; a theme is considered "covered" once it reaches this value.
COVERED_THRESHOLD = 1
MAX_THEME_POINTS = 5


def _format_sse(event_name: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


async def _stream_words(text: str):
    """Fake-stream text word by word as SSE token events.

    The asyncio.sleep(0) between each word yields control back to the event loop
    so Uvicorn can actually flush each chunk to the socket before the next one is
    produced — without it all words would be batched into a single HTTP write.
    """
    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield _format_sse("token", {"content": chunk})
        await asyncio.sleep(0.05)


class StandardFeynmanService:
    """Drives the unlimited-iteration standard Feynman evaluation loop."""

    def __init__(
        self,
        learning_service: LearningService,
        llm: YandexGPTLLMGateway | None = None,
        prompt_manager: PromptManager | None = None,
        usage_service: object | None = None,
    ) -> None:
        self._learning = learning_service
        self._llm = llm or YandexGPTLLMGateway()
        self._pm = prompt_manager
        if self._pm is None:
            raise ValueError("prompt_manager must be provided")
        self._feedback = FeedbackNoteService(learning_service._session_factory)
        self._usage_service = usage_service

    # ------------------------------------------------------------------
    # Session start — streaming
    # ------------------------------------------------------------------

    async def start_session(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[str]:
        """
        Create a standard Feynman session for a lesson and stream the LLM-generated
        opening question.

        SSE events:
          token           {"content": "..."}         — live LLM output chunks
          session_started {"session_id": "...",
                           "feynman_block_id": "...",
                           "theme_titles": [...],
                           "theme_scores": [...]}     — session metadata after stream
          error           {"detail": "..."}
        """
        lesson = await self._learning.get_lesson(lesson_id, user_id)
        if lesson is None:
            yield _format_sse("error", {"detail": "Lesson not found"})
            return

        themes = parse_lesson_themes(lesson.content)
        if not themes:
            yield _format_sse(
                "error", {"detail": "No PART themes found in lesson markdown"}
            )
            return

        theme_titles = [t.title for t in themes]
        scope = [t.number for t in themes]

        # Create (or reuse) the standard feynman block for this lesson
        block = await self._get_or_create_standard_block(
            lesson_id, user_id, scope, theme_titles
        )

        # Create session and initialise scores
        session = await self._learning.create_session(
            block.id, user_id, type="standard"
        )
        # None = not yet evaluated; stays None until LLM explicitly probes the theme
        initial_scores: list[int | None] = [None] * len(themes)
        await self._learning.update_theme_scores(session.id, initial_scores)

        # Stream opening question from LLM
        messages = build_opening_messages(themes, self._pm)
        accumulated: list[str] = []
        _stream_usage: UsageInfo | None = None
        try:
            async for chunk in self._llm.chat_stream(messages):
                if isinstance(chunk, UsageInfo):
                    _stream_usage = chunk
                    continue
                accumulated.append(chunk)
                yield _format_sse("token", {"content": chunk})
            if self._usage_service:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id, feature="feynman", usage=_stream_usage,
                )
        except Exception as exc:
            logger.exception("LLM opening stream failed: %s", exc)
            yield _format_sse(
                "error", {"detail": "Could not generate opening question"}
            )
            return

        opening_text = "".join(accumulated).strip()

        # Store opening as the first assistant message
        await self._learning.add_message(
            session_id=session.id,
            role="assistant",
            content=opening_text,
            iteration=1,
        )

        yield _format_sse(
            "session_started",
            {
                "session_id": str(session.id),
                "feynman_block_id": str(block.id),
                "theme_titles": theme_titles,
                "theme_scores": initial_scores,
            },
        )

    # ------------------------------------------------------------------
    # Answer handling — streaming
    # ------------------------------------------------------------------

    async def handle_answer(
        self,
        session_id: uuid.UUID,
        user_answer: str,
        user_id: uuid.UUID,
        user_citations: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """
        Process one student answer and stream SSE events back.

        SSE events:
          token            {"content": "..."}
          message_complete {"role": "assistant",
                            "content": "...",
                            "iteration": N,
                            "theme_scores": [...]}
          summary          {"theme_scores": [...],
                            "theme_titles": [...],
                            "all_covered": bool,
                            "feedback": [{"theme": str, "feedback": str}, ...]}
          error            {"detail": "..."}
        """
        feynman_session = await self._learning.get_session_with_block(
            session_id, user_id
        )
        if feynman_session is None:
            yield _format_sse("error", {"detail": "Session not found"})
            return

        if feynman_session.status != "active":
            yield _format_sse(
                "error", {"detail": f"Session is {feynman_session.status}"}
            )
            return

        if feynman_session.type != "standard":
            yield _format_sse(
                "error", {"detail": "Session is not a standard Feynman session"}
            )
            return

        block = feynman_session.feynman_block
        themes = _themes_from_block(block)
        iteration = feynman_session.current_iteration
        scores: list[int | None] = list(
            feynman_session.covered_points or [None] * len(themes)
        )

        # Ensure scores list matches theme count
        while len(scores) < len(themes):
            scores.append(None)
        scores = scores[: len(themes)]

        cleaned_citations = (
            [c.strip() for c in (user_citations or []) if c and c.strip()]
            if user_citations
            else None
        )

        # Persist user's answer
        await self._learning.add_message(
            session_id=session_id,
            role="user",
            content=user_answer,
            iteration=iteration,
            citations=cleaned_citations,
        )

        history = [
            {"role": m.role, "content": m.content} for m in feynman_session.messages
        ]

        messages = build_evaluator_messages(
            themes=themes,
            scores=scores,
            history=history,
            user_answer=user_answer,
            prompt_manager=self._pm,
            user_citations=cleaned_citations,
        )

        # Non-streaming evaluation call — accumulate full JSON, then fake-stream the text.
        try:
            raw, _eval_usage = await self._llm.chat_complete(messages)
            if self._usage_service:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id, feature="feynman", usage=_eval_usage,
                )
        except Exception as exc:
            logger.exception("LLM evaluation failed: %s", exc)
            yield _format_sse(
                "error", {"detail": "Evaluation failed, please try again"}
            )
            return

        try:
            clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            evaluation = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not parse LLM evaluation JSON: %r — %s", raw, exc)
            yield _format_sse(
                "error", {"detail": "Could not parse evaluation response"}
            )
            return

        # Apply theme_updates (function-call semantics).
        # pts >= 0 allowed: 0 means "explicitly probed, student showed nothing" → None → 0.
        theme_updates: list[dict] = evaluation.get("theme_updates", [])
        for update in theme_updates:
            idx = update.get("theme_index")
            pts = update.get("points", -1)
            if (
                isinstance(idx, int)
                and 0 <= idx < len(scores)
                and isinstance(pts, int)
                and pts >= 0
            ):
                current = scores[idx]
                if current is None:
                    scores[idx] = pts  # first evaluation of this theme
                else:
                    scores[idx] = min(MAX_THEME_POINTS, current + pts)

        await self._learning.update_theme_scores(session_id, scores)

        # Save feedback notes (mistakes) for this answer
        raw_feedback_notes: list[dict] = evaluation.get("feedback_notes", [])
        if raw_feedback_notes:
            await self._feedback.save_notes(
                user_id=user_id,
                source_type="feynman",
                source_session_id=session_id,
                source_answer_id=None,
                notes=raw_feedback_notes,
            )

        follow_up: str = evaluation.get("follow_up", "")
        all_done: bool = bool(evaluation.get("all_done", False))
        all_covered = all_done or all(
            s is not None and s >= COVERED_THRESHOLD for s in scores
        )

        if all_covered:
            await self._learning.complete_session(session_id, scores)

            # Build per-theme feedback from evaluator JSON; fall back to pure-Python generation.
            raw_theme_feedback: list[dict] = evaluation.get("theme_feedback", [])
            feedback = _build_feedback_list(themes, scores, raw_theme_feedback)
            await self._learning.save_session_feedback(session_id, feedback)

            # Store a plain-text summary as an assistant message for the conversation log.
            feedback_text = _feedback_list_to_text(themes, feedback)
            await self._learning.add_message(
                session_id=session_id,
                role="assistant",
                content=feedback_text,
                iteration=iteration,
            )

            yield _format_sse(
                "summary",
                {
                    "theme_scores": scores,
                    "theme_titles": block.points,
                    "all_covered": True,
                    "feedback": feedback,
                },
            )
        else:
            new_iteration = iteration + 1
            await self._learning.advance_iteration(session_id, new_iteration)

            question_text = (
                follow_up
                or "Can you tell me more about the parts you haven't covered yet?"
            )
            await self._learning.add_message(
                session_id=session_id,
                role="assistant",
                content=question_text,
                iteration=new_iteration,
            )

            # Fake-stream the follow-up question word by word
            async for chunk in _stream_words(question_text):
                yield chunk

            yield _format_sse(
                "message_complete",
                {
                    "role": "assistant",
                    "content": question_text,
                    "iteration": new_iteration,
                    "theme_scores": scores,
                    "citations": [],
                },
            )

    # ------------------------------------------------------------------
    # Abort — two modes
    # ------------------------------------------------------------------

    async def abort_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        exhausted: bool = False,
    ) -> FeynmanSession | None:
        """
        End a standard Feynman session early.

        exhausted=False (default): user just leaves.
            None scores stay None — themes were never reached.
        exhausted=True: user says "I've told you everything I know".
            None scores flip to 0 — they had the chance and couldn't cover them.
        Both modes generate LLM per-theme feedback for covered themes.
        """
        feynman_session = await self._learning.abort_session(session_id, user_id)
        if feynman_session is None:
            return None

        block = await self._learning.get_feynman_block(
            feynman_session.feynman_block_id, user_id
        )
        if block is not None:
            themes = _themes_from_block(block)
            scores: list[int | None] = list(
                feynman_session.covered_points or [None] * len(themes)
            )

            if exhausted:
                # Flip uncovered themes to 0: student had the chance, didn't explain them
                scores = [0 if s is None else s for s in scores]
                await self._learning.update_theme_scores(session_id, scores)

            feedback = await self._generate_feedback(themes, scores, "aborted", user_id=user_id)
            await self._learning.save_session_feedback(session_id, feedback)

        # Emit mastery evidence events (aborted sessions with scores still count)
        try:
            from src.mastery.emitters import emit_feynman_session_events

            async with self._learning._session_factory() as mastery_session:
                await emit_feynman_session_events(mastery_session, session_id)
        except Exception:
            logger.exception(
                "Failed to emit mastery events for aborted feynman session %s",
                session_id,
            )

        return feynman_session

    async def _generate_feedback(
        self,
        themes: list[LessonTheme],
        scores: list[int | None],
        outcome: str,
        user_id: object | None = None,
    ) -> list[dict]:
        """Call LLM non-streaming to generate per-theme feedback list."""
        messages = build_feedback_messages(themes, scores, outcome, self._pm)
        try:
            raw, _usage = await self._llm.chat_complete(messages)
            if self._usage_service and user_id:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id, feature="feynman_feedback", usage=_usage,
                )
            raw = raw.strip()
            clean = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
            raw_list: list[dict] = json.loads(clean)
            return _build_feedback_list(themes, scores, raw_list)
        except Exception as exc:
            logger.exception("Feedback generation failed: %s", exc)
            return _fallback_feedback(themes, scores)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_or_create_standard_block(
        self,
        lesson_id: uuid.UUID,
        user_id: uuid.UUID,
        scope: list[int],
        theme_titles: list[str],
    ) -> FeynmanBlock:
        """Return existing standard FeynmanBlock for the lesson or create a new one."""
        async with self._learning._session_factory() as db:
            result = await db.execute(
                select(FeynmanBlock).where(
                    and_(
                        FeynmanBlock.lesson_id == lesson_id,
                        FeynmanBlock.user_id == user_id,
                        # Standard blocks have an empty question field
                        FeynmanBlock.question == "",
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                # Update scope/points in case lesson changed
                existing.scope = scope
                existing.points = theme_titles
                await db.commit()
                await db.refresh(existing)
                return existing

            block = FeynmanBlock(
                lesson_id=lesson_id,
                user_id=user_id,
                scope=scope,
                question="",
                points=theme_titles,
            )
            db.add(block)
            await db.commit()
            await db.refresh(block)
            return block


def _themes_from_block(block: FeynmanBlock) -> list[LessonTheme]:
    """Reconstruct LessonTheme list from a FeynmanBlock's points list."""
    return [
        LessonTheme(number=i + 1, title=title, content="")
        for i, title in enumerate(block.points)
    ]


def _build_feedback_list(
    themes: list[LessonTheme],
    scores: list[int | None],
    raw_theme_feedback: list[dict],
) -> list[dict]:
    """
    Convert the LLM's theme_feedback list into the canonical storage format:
      [{"theme": "<title>", "feedback": "<text>"}]

    Only includes themes with score > 0. None and 0 are both excluded from
    positive feedback — but 0-scored themes get a fallback note.
    Themes with score None (never evaluated) are skipped entirely.
    """
    llm_map: dict[int, str] = {}
    for item in raw_theme_feedback:
        idx = item.get("theme_index")
        fb = item.get("feedback", "").strip()
        if isinstance(idx, int) and 0 <= idx < len(themes) and fb:
            llm_map[idx] = fb

    result: list[dict] = []
    for i, (theme, score) in enumerate(zip(themes, scores)):
        if score is None:
            continue  # never evaluated — skip entirely
        fb_text = llm_map.get(i) or _fallback_theme_feedback(theme.title, score)
        result.append({"theme": theme.title, "feedback": fb_text})
    return result


def _fallback_theme_feedback(title: str, score: int) -> str:
    if score >= 4:
        return f"You explained {title} really well — clear and confident."
    if score >= 2:
        return (
            f"You have a reasonable grasp of {title}; a quick review would solidify it."
        )
    if score >= 1:
        return f"{title} was only briefly touched — worth revisiting in more depth."
    return f"You were asked about {title} but couldn't explain it — make sure to revisit it."


def _feedback_list_to_text(themes: list[LessonTheme], feedback: list[dict]) -> str:
    """Flatten per-theme feedback list into a single plain-text message for storage."""
    lines = [f"• {item['theme']}: {item['feedback']}" for item in feedback]
    return "\n".join(lines) if lines else "Session complete."


def _fallback_feedback(
    themes: list[LessonTheme], scores: list[int | None]
) -> list[dict]:
    """Pure-Python fallback that generates per-theme feedback without an LLM call."""
    return [
        {
            "theme": theme.title,
            "feedback": _fallback_theme_feedback(theme.title, score),
        }
        for theme, score in zip(themes, scores)
        if score is not None  # skip never-evaluated themes
    ]
