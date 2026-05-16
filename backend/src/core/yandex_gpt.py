"""YandexGPT LLM gateway using the OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, AsyncIterator, TypeVar

from openai import AsyncOpenAI

from src.config import get_settings
from src.core.llm_usage import (
    UsageInfo,
    ensure_usage,
    extract_openai_usage,
)

T = TypeVar("T")

_PLACEHOLDER_FOLDER_IDS = frozenset(
    {
        "<folder_id>",
        "<folder-id>",
        "folder_id",
        "folder-id",
        "your_folder_id",
        "your-folder-id",
        "your_yandex_cloud_folder_id",
        "your-yandex-cloud-folder-id",
    }
)


class YandexGPTLLMGateway:
    """YandexGPT adapter backed by OpenAI-compatible AsyncOpenAI client."""

    def __init__(
        self, client: AsyncOpenAI | None = None, model: str | None = None
    ) -> None:
        settings = get_settings()
        api_key = (settings.llm.api_key or "").strip()
        if not api_key:
            raise ValueError(
                "LLM__API_KEY is not set. Add a Yandex AI Studio API key."
            )

        self._folder_id = settings.llm.folder_id.strip()
        if self._folder_id.lower() in _PLACEHOLDER_FOLDER_IDS:
            raise ValueError(
                "LLM__FOLDER_ID is still set to a placeholder. Set it to the "
                "Yandex Cloud folder ID that owns LLM__API_KEY."
            )

        self._model_id_map: dict[str, str] = settings.llm.model_id_map
        self._model = settings.llm.resolve_model_uri(model)
        if not self._folder_id and not self._model.startswith("gpt://"):
            raise ValueError(
                "LLM__FOLDER_ID is not set and the configured YandexGPT model "
                "is not a full gpt:// URI."
            )

        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=settings.llm.base_url,
            project=self._folder_id or None,
            timeout=settings.llm.timeout_seconds,
        )

    @property
    def model_id_map(self) -> dict[str, str]:
        return dict(self._model_id_map)

    @property
    def reasoning_params_map(self) -> dict[str, dict[str, str]]:
        return dict(get_settings().llm.reasoning_params_map)

    def _resolve_model(self, model_alias: str | None) -> str:
        raw = (
            self._model_id_map.get(model_alias, model_alias)
            if model_alias
            else self._model
        )
        model = get_settings().llm.resolve_model_uri(raw)
        if not self._folder_id and not model.startswith("gpt://"):
            raise ValueError(
                "LLM__FOLDER_ID is not set and the requested YandexGPT model "
                "is not a full gpt:// URI."
            )
        return model

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> dict[str, Any]:
        model = self._resolve_model(model_override)
        response = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                stream=False,
            )
        )

        message = response.choices[0].message
        tool_calls = self._normalize_tool_calls(getattr(message, "tool_calls", None))
        normalized_content = self._normalize_content(
            getattr(message, "content", "") or ""
        )
        return {
            "content": normalized_content,
            "tool_calls": tool_calls,
            "usage": ensure_usage(
                extract_openai_usage(response, model),
                messages=messages,
                output_text=normalized_content,
                model=model,
                tool_calls=tool_calls,
                source="chat_with_tools",
            ),
        }

    async def chat_tools_only(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> tuple[list[dict[str, Any]], UsageInfo | None]:
        model = self._resolve_model(model_override)
        response = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                stream=False,
            )
        )

        message = response.choices[0].message
        tool_calls = self._normalize_tool_calls(getattr(message, "tool_calls", None))
        usage = ensure_usage(
            extract_openai_usage(response, model),
            messages=messages,
            output_text=self._normalize_content(
                getattr(message, "content", "") or ""
            ),
            model=model,
            tool_calls=tool_calls,
            source="chat_tools_only",
        )
        return tool_calls, usage

    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> tuple[str, UsageInfo | None]:
        model = self._resolve_model(model_override)
        response = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
            )
        )
        content = getattr(response.choices[0].message, "content", None) or ""
        normalized = self._normalize_content(content)
        usage = ensure_usage(
            extract_openai_usage(response, model),
            messages=messages,
            output_text=normalized,
            model=model,
            source="chat_complete",
        )
        return normalized, usage

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> AsyncIterator[str | UsageInfo]:
        model = self._resolve_model(model_override)
        stream = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
            )
        )

        usage_info: UsageInfo | None = None
        accumulated: list[str] = []
        async for chunk in stream:
            chunk_usage = extract_openai_usage(chunk, model)
            if chunk_usage is not None:
                usage_info = chunk_usage

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            delta = choices[0].delta
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                accumulated.append(content)
                yield content

        yield ensure_usage(
            usage_info,
            messages=messages,
            output_text="".join(accumulated),
            model=model,
            source="chat_stream",
        )

    async def chat_stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        model = self._resolve_model(model_override)
        stream = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                stream=True,
                stream_options={"include_usage": True},
            )
        )

        full_content: list[str] = []
        tool_calls_accum: dict[int, dict[str, Any]] = {}
        tool_call_detected = False
        usage_info: UsageInfo | None = None

        async for chunk in stream:
            chunk_usage = extract_openai_usage(chunk, model)
            if chunk_usage is not None:
                usage_info = chunk_usage

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            delta = choices[0].delta
            tc_deltas = getattr(delta, "tool_calls", None) or []
            if tc_deltas and not tool_call_detected:
                tool_call_detected = True

            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                full_content.append(content)
                if not tool_call_detected:
                    yield {"type": "token", "content": content}

            for tc in tc_deltas:
                idx = getattr(tc, "index", None)
                if idx is None:
                    continue
                if idx not in tool_calls_accum:
                    tool_calls_accum[idx] = {
                        "id": getattr(tc, "id", None) or "",
                        "name": "",
                        "arguments": "",
                    }
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        tool_calls_accum[idx]["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        tool_calls_accum[idx]["arguments"] += fn.arguments

        tool_calls_list: list[dict[str, Any]] | None = None
        if tool_calls_accum:
            tool_calls_list = [
                tool_calls_accum[k] for k in sorted(tool_calls_accum.keys())
            ]

        final_content = self._normalize_content("".join(full_content))
        yield {
            "type": "done",
            "content": final_content,
            "tool_calls": tool_calls_list,
            "usage": ensure_usage(
                usage_info,
                messages=messages,
                output_text=final_content,
                model=model,
                tool_calls=tool_calls_list,
                source="chat_stream_with_tools",
            ),
        }

    async def generate_title(self, user_message: str) -> tuple[str, UsageInfo | None]:
        prompt = (
            "Given this student question, generate a 2-6 word conversation title. "
            "Return ONLY the title.\n\n"
            f"Question: '{user_message}'"
        )
        messages = [
            {
                "role": "system",
                "content": "Generate concise conversation titles.",
            },
            {"role": "user", "content": prompt},
        ]
        model = self._resolve_model(None)
        response = await self._with_retries(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
            )
        )

        choice = response.choices[0]
        title = self._normalize_content(choice.message.content or "").strip()
        title = title.strip('"').strip("'")
        max_len = get_settings().llm.conversation_title_max_length
        usage = ensure_usage(
            extract_openai_usage(response, model),
            messages=messages,
            output_text=title,
            model=model,
            source="generate_title",
        )
        return title[:max_len], usage

    async def _with_retries(self, fn: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            try:
                return await fn()
            except Exception as exc:
                if not self._is_retryable_error(exc):
                    raise
                settings = get_settings()
                if attempt >= settings.llm.max_retries:
                    raise
                delay = settings.llm.retry_base_delay * (2**attempt)
                await asyncio.sleep(delay)
                attempt += 1

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code is None:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

        if isinstance(status_code, int):
            return not (
                400 <= status_code < 500 and status_code not in {408, 409, 429}
            )

        return True

    @staticmethod
    def _normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool_call in tool_calls or []:
            function = getattr(tool_call, "function", None)
            normalized.append(
                {
                    "id": getattr(tool_call, "id", ""),
                    "name": getattr(function, "name", ""),
                    "arguments": getattr(function, "arguments", ""),
                }
            )
        return normalized

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
            return "".join(parts)

        return str(content)
