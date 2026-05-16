"""Provider-neutral LLM usage helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

_TOKEN_ENCODER: tiktoken.Encoding | None = None


@dataclass(slots=True)
class UsageInfo:
    """Token usage returned by a single LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    cost_usd: float | None = None


def _get_token_encoder() -> tiktoken.Encoding:
    global _TOKEN_ENCODER
    if _TOKEN_ENCODER is None:
        _TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
    return _TOKEN_ENCODER


def _count_tokens(text: str) -> int:
    return len(_get_token_encoder().encode(text))


def extract_openai_usage(response: Any, model: str) -> UsageInfo | None:
    """Extract OpenAI-compatible token counts from a response or stream chunk."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", 0) or 0
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return UsageInfo(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model=model,
        cost_usd=None,
    )


def _serialize_message_for_tokens(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text")
                if t:
                    parts.append(str(t))
        text = "".join(parts)
    else:
        text = ""
    role = str(message.get("role", ""))
    extras: list[str] = []
    if message.get("tool_calls"):
        try:
            extras.append(json.dumps(message["tool_calls"], default=str))
        except Exception:
            pass
    if message.get("name"):
        extras.append(str(message["name"]))
    return role + "\n" + text + ("\n" + "\n".join(extras) if extras else "")


def estimate_usage(
    messages: list[dict[str, Any]],
    output_text: str,
    model: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> UsageInfo:
    """Fallback: estimate usage with tiktoken when the API does not return it."""
    try:
        prompt_tokens = sum(
            _count_tokens(_serialize_message_for_tokens(m)) for m in messages
        )
        completion_text = output_text or ""
        if tool_calls:
            try:
                completion_text += "\n" + json.dumps(tool_calls, default=str)
            except Exception:
                pass
        completion_tokens = _count_tokens(completion_text)
    except Exception:
        prompt_tokens = 0
        completion_tokens = 0
    return UsageInfo(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        model=model,
        cost_usd=None,
    )


def ensure_usage(
    usage: UsageInfo | None,
    *,
    messages: list[dict[str, Any]],
    output_text: str,
    model: str,
    tool_calls: list[dict[str, Any]] | None = None,
    source: str,
) -> UsageInfo:
    if usage is not None:
        return usage
    logger.warning(
        "LLM usage missing from response, falling back to tiktoken estimate (source=%s model=%s)",
        source,
        model,
    )
    return estimate_usage(messages, output_text, model, tool_calls)
