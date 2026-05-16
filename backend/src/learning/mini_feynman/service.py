"""Feynman 3-iteration evaluation pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from src.core.llm_usage import UsageInfo
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.service import LearningService
from src.learning.mini_feynman.prompts import build_evaluate_messages
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

# Number of characters per streamed token chunk for follow-up / summary text.
_STREAM_CHUNK_SIZE = 4


def _format_sse(event_name: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


async def _stream_text_as_tokens(text: str) -> AsyncIterator[str]:
    """Yield SSE token events for *text*, chunked by character groups.

    The LLM response is collected in full before calling this (required because
    the evaluation result is a JSON object), so we re-stream the display text
    in small chunks to give the client real incremental rendering.
    """
    for i in range(0, len(text), _STREAM_CHUNK_SIZE):
        yield _format_sse("token", {"content": text[i : i + _STREAM_CHUNK_SIZE]})


class FeynmanPipelineService:
    """Drives the 3-iteration feynman evaluation loop."""

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
        self._usage_service = usage_service

    async def handle_answer(
        self,
        session_id: uuid.UUID,
        user_answer: str,
        user_id: uuid.UUID,
    ) -> AsyncIterator[str]:
        """
        Process one student answer and stream SSE events back.

        The LLM is called with stream=True and its raw chunks are forwarded as
        `token` events while being accumulated.  Once the stream ends the
        accumulated JSON is parsed and the appropriate terminal events are sent:

          token            {"content": "..."}          — live LLM output chunks
          message_complete {"role": "assistant",
                            "content": "...",
                            "iteration": N,
                            "covered": [...]}           — follow-up question done
          summary          {"text": "...",
                            "covered": [...],
                            "points": [...],
                            "all_covered": bool}        — session finished
          error            {"detail": "..."}
        """
        feynman_session = await self._learning.get_session_with_block(
            session_id, user_id
        )
        if feynman_session is None:
            yield _format_sse("error", {"detail": "Session not found"})
            return

        if feynman_session.status == "completed":
            yield _format_sse("error", {"detail": "Session already completed"})
            return

        block = feynman_session.feynman_block
        iteration = feynman_session.current_iteration

        # Persist student's answer
        await self._learning.add_message(
            session_id=session_id,
            role="user",
            content=user_answer,
            iteration=iteration,
        )

        # Build conversation history (all messages before this answer)
        history = [
            {"role": m.role, "content": m.content} for m in feynman_session.messages
        ]

        is_terminal = iteration >= MAX_ITERATIONS
        messages = build_evaluate_messages(
            points=block.points,
            history=history,
            user_answer=user_answer,
            iteration=iteration,
            is_terminal=is_terminal,
            prompt_manager=self._pm,
        )

        # --- Real streaming LLM call ---
        # The evaluation response is JSON, so we must accumulate the full text
        # before parsing.  We still forward each raw chunk as a `token` event so
        # the client sees output immediately rather than waiting for the whole
        # response.
        raw_chunks: list[str] = []
        _stream_usage: UsageInfo | None = None
        try:
            async for chunk in self._llm.chat_stream(messages):
                if isinstance(chunk, UsageInfo):
                    _stream_usage = chunk
                    continue
                raw_chunks.append(chunk)
                yield _format_sse("token", {"content": chunk})
            if self._usage_service:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id, feature="mini_feynman", usage=_stream_usage,
                )
        except Exception as exc:
            logger.exception("LLM evaluation stream failed: %s", exc)
            yield _format_sse(
                "error", {"detail": "Evaluation failed, please try again"}
            )
            return

        raw = "".join(raw_chunks)

        # Parse structured response
        try:
            clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            evaluation = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not parse LLM evaluation JSON: %r — %s", raw, exc)
            yield _format_sse(
                "error", {"detail": "Could not parse evaluation response"}
            )
            return

        covered: list[bool] = evaluation.get("covered", [False] * len(block.points))
        follow_up: str = evaluation.get("follow_up", "")
        summary: str = evaluation.get("summary", "")

        # Ensure covered list matches point count
        while len(covered) < len(block.points):
            covered.append(False)
        covered = covered[: len(block.points)]

        all_covered = all(covered)

        if all_covered or is_terminal:
            # Terminal: complete session
            await self._learning.complete_session(session_id, covered)

            summary_text = summary or _build_fallback_summary(block.points, covered)
            await self._learning.add_message(
                session_id=session_id,
                role="assistant",
                content=summary_text,
                iteration=iteration,
            )

            yield _format_sse(
                "summary",
                {
                    "text": summary_text,
                    "covered": covered,
                    "points": block.points,
                    "all_covered": all_covered,
                },
            )
        else:
            # Not terminal: advance iteration and confirm the follow-up question
            new_iteration = iteration + 1
            await self._learning.advance_iteration(session_id, new_iteration)

            question_text = (
                follow_up or "Can you explain that concept in a bit more detail?"
            )
            await self._learning.add_message(
                session_id=session_id,
                role="assistant",
                content=question_text,
                iteration=new_iteration,
            )

            yield _format_sse(
                "message_complete",
                {
                    "role": "assistant",
                    "content": question_text,
                    "iteration": new_iteration,
                    "covered": covered,
                },
            )


def _build_fallback_summary(points: list[str], covered: list[bool]) -> str:
    covered_items = [p for p, c in zip(points, covered) if c]
    missed_items = [p for p, c in zip(points, covered) if not c]

    parts: list[str] = []
    if covered_items:
        parts.append("Well done — you covered: " + "; ".join(covered_items) + ".")
    if missed_items:
        parts.append(
            "The following points could use more attention: "
            + "; ".join(missed_items)
            + "."
        )
    if not missed_items:
        parts.append(
            "You've demonstrated a solid understanding of all the key concepts!"
        )
    return " ".join(parts)
