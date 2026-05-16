"""Streaming practice-mode hints: two SSE lanes (chat line vs hint panel)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from src.core.llm_usage import UsageInfo, estimate_usage
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.tests.models import TestQuestion
from src.learning.tests.prompts import (
    PRACTICE_HINT_CHAT_MARKER,
    PRACTICE_HINT_PANEL_MARKER,
    build_practice_hint_messages,
)
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


class PracticeHintDelimiterSplitter:
    """Split model output into chat vs hint panel using mandatory markers."""

    __slots__ = ("_buf", "_phase")

    def __init__(self) -> None:
        self._buf = ""
        self._phase = 0  # 0 seek chat tag, 1 in chat, 2 in panel

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """Return (lane, text) where lane is 'chat' or 'panel'."""
        out: list[tuple[str, str]] = []
        if self._phase == 2:
            if chunk:
                out.append(("panel", chunk))
            return out

        self._buf += chunk
        chat_tag, panel_tag = PRACTICE_HINT_CHAT_MARKER, PRACTICE_HINT_PANEL_MARKER
        while True:
            if self._phase == 0:
                i = self._buf.find(chat_tag)
                if i < 0:
                    # Keep the full buffer until we see the chat marker (or finalize).
                    # Only flush early if the buffer grows huge without a tag (non-compliant model).
                    keep = len(chat_tag) - 1
                    max_hold = 8000
                    if len(self._buf) > max_hold:
                        flush_len = len(self._buf) - keep
                        out.append(("chat", self._buf[:flush_len]))
                        self._buf = self._buf[flush_len:]
                    return out
                self._buf = self._buf[i + len(chat_tag) :].lstrip("\n\r \t")
                self._phase = 1
                continue

            if self._phase == 1:
                j = self._buf.find(panel_tag)
                if j < 0:
                    k = len(panel_tag) - 1
                    if len(self._buf) > k:
                        emit = self._buf[:-k]
                        self._buf = self._buf[-k:]
                        if emit:
                            out.append(("chat", emit))
                    return out
                prefix = self._buf[:j]
                if prefix:
                    out.append(("chat", prefix))
                self._buf = self._buf[j + len(panel_tag) :].lstrip("\n\r \t")
                self._phase = 2
                if self._buf:
                    out.append(("panel", self._buf))
                    self._buf = ""
                return out

    def finalize(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if self._phase == 0:
            if self._buf.strip():
                out.append(("chat", self._buf))
        elif self._phase == 1:
            out.append(("chat", self._buf))
        elif self._phase == 2 and self._buf:
            out.append(("panel", self._buf))
        self._buf = ""
        return out


def _question_belongs_to_session(question: TestQuestion, template_id: uuid.UUID) -> bool:
    return question.template_id == template_id


def _resolve_usage_model(llm: YandexGPTLLMGateway, model: str | None) -> str:
    resolver = getattr(llm, "_resolve_model", None)
    if callable(resolver):
        try:
            return str(resolver(model))
        except Exception:
            logger.exception("failed to resolve model for practice hint usage estimate")
    if model:
        return model
    return str(getattr(llm, "_model", None) or "unknown")


async def stream_practice_hint_events(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question: TestQuestion,
    template_id: uuid.UUID,
    model: str | None,
    reasoning: str | None,
    llm: YandexGPTLLMGateway,
    usage_service: Any | None,
    chat_conversation_id: str | None = None,
    pm: PromptManager | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Yields SSE-shaped dicts: {"event": str, "data": dict}.

    Events:
    - hint_meta: session_id, question_id, optional conversation_id (chat sync)
    - hint_chat_token: {content}
    - hint_panel_token: {content}
    - hint_complete: {assistant_chat, hint_panel}
    - error: {message, recoverable}
    """
    if not _question_belongs_to_session(question, template_id):
        yield {
            "event": "error",
            "data": {
                "message": "Question does not belong to this session template",
                "recoverable": False,
            },
        }
        return

    messages = build_practice_hint_messages(
        question_type=question.type,
        question_text=question.question,
        options=list(question.options) if question.options else None,
        author_hint=question.hint,
        pm=pm,
    )

    splitter = PracticeHintDelimiterSplitter()
    full_chat: list[str] = []
    full_panel: list[str] = []

    meta: dict[str, str] = {
        "session_id": str(session_id),
        "question_id": str(question.id),
    }
    if chat_conversation_id:
        meta["conversation_id"] = chat_conversation_id
    yield {"event": "hint_meta", "data": meta}

    usage: UsageInfo | None = None
    try:
        async for part in llm.chat_stream(
            messages,
            model_override=model,
            reasoning_level=reasoning,
        ):
            if isinstance(part, UsageInfo):
                usage = part
                continue
            for lane, text in splitter.feed(part):
                if lane == "chat":
                    full_chat.append(text)
                    yield {"event": "hint_chat_token", "data": {"content": text}}
                else:
                    full_panel.append(text)
                    yield {"event": "hint_panel_token", "data": {"content": text}}

        for lane, text in splitter.finalize():
            if lane == "chat":
                full_chat.append(text)
                yield {"event": "hint_chat_token", "data": {"content": text}}
            else:
                full_panel.append(text)
                yield {"event": "hint_panel_token", "data": {"content": text}}

    except Exception:
        logger.exception(
            "practice hint stream failed user=%s session=%s question=%s",
            str(user_id)[:8],
            session_id,
            question.id,
        )
        yield {
            "event": "error",
            "data": {"message": "Hint generation failed", "recoverable": False},
        }
        return

    if usage_service is not None:
        if usage is None:
            output_text = "\n".join(
                part
                for part in (
                    "".join(full_chat).strip(),
                    "".join(full_panel).strip(),
                )
                if part
            )
            resolved_model = _resolve_usage_model(llm, model)
            logger.warning(
                "practice hint stream usage missing, estimating usage model=%s",
                resolved_model,
            )
            usage = estimate_usage(
                messages=messages,
                output_text=output_text,
                model=resolved_model,
            )
        usage_service.log_usage_fire_and_forget(
            user_id=user_id,
            feature="test_practice_hint",
            usage=usage,
        )

    yield {
        "event": "hint_complete",
        "data": {
            "assistant_chat": "".join(full_chat).strip(),
            "hint_panel": "".join(full_panel).strip(),
        },
    }
