from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import get_settings
from src.core.llm_usage import UsageInfo, estimate_usage, extract_openai_usage
from src.core.yandex_gpt import YandexGPTLLMGateway


def test_extract_openai_usage_reads_yandex_token_counts():
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
        )
    )

    usage = extract_openai_usage(response, "gpt://folder123/yandexgpt/latest")

    assert usage is not None
    assert usage.prompt_tokens == 12
    assert usage.completion_tokens == 8
    assert usage.total_tokens == 20
    assert usage.model == "gpt://folder123/yandexgpt/latest"
    assert usage.cost_usd is None


def test_estimated_usage_has_no_exact_cost():
    usage = estimate_usage(
        [{"role": "user", "content": "Привет"}],
        "Готово",
        "gpt://folder123/yandexgpt/latest",
    )

    assert usage.cost_usd is None
    assert usage.total_tokens >= usage.completion_tokens


def test_default_base_url_uses_yandex_openai_compatible_endpoint():
    get_settings.cache_clear()

    assert get_settings().llm.base_url == "https://llm.api.cloud.yandex.net/v1"


def test_configured_processing_clustering_model_resolves_to_yandex_uri(monkeypatch):
    monkeypatch.setenv("LLM__API_KEY", "yandex-test-key")
    monkeypatch.setenv("LLM__FOLDER_ID", "folder123")
    get_settings.cache_clear()
    settings = get_settings()
    gateway = YandexGPTLLMGateway(client=_FakeClient(None))

    assert settings.processing.chunking.clustering_model == "YandexGPT"
    assert (
        gateway._resolve_model(settings.processing.chunking.clustering_model)
        == "gpt://folder123/yandexgpt/latest"
    )


def test_compatibility_maps_are_read_only_copies(monkeypatch):
    monkeypatch.setenv("LLM__API_KEY", "yandex-test-key")
    monkeypatch.setenv("LLM__FOLDER_ID", "folder123")
    get_settings.cache_clear()
    gateway = YandexGPTLLMGateway(client=_FakeClient(None))

    model_id_map = gateway.model_id_map
    reasoning_params_map = gateway.reasoning_params_map
    model_id_map["YandexGPT"] = "changed"
    reasoning_params_map["default"] = {"effort": "changed"}

    assert gateway.model_id_map == {"YandexGPT": "yandexgpt/latest"}
    assert gateway.reasoning_params_map == {"default": {}}


def test_gateway_rejects_placeholder_folder_id(monkeypatch):
    monkeypatch.setenv("LLM__API_KEY", "yandex-test-key")
    monkeypatch.setenv("LLM__FOLDER_ID", "your_yandex_cloud_folder_id")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="LLM__FOLDER_ID.*placeholder"):
        YandexGPTLLMGateway(client=_FakeClient(None))


class _AsyncStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeCompletions:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response) -> None:
        self.completions = _FakeCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


class _ProviderStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def _gateway_with_fake_client(monkeypatch, response):
    monkeypatch.setenv("LLM__API_KEY", "yandex-test-key")
    monkeypatch.setenv("LLM__FOLDER_ID", "folder123")
    get_settings.cache_clear()
    client = _FakeClient(response)
    gateway = YandexGPTLLMGateway(client=client)
    return gateway, client


@pytest.mark.asyncio
async def test_with_retries_does_not_retry_provider_permission_errors(monkeypatch):
    monkeypatch.setenv("LLM__API_KEY", "yandex-test-key")
    monkeypatch.setenv("LLM__FOLDER_ID", "folder123")
    monkeypatch.setenv("LLM__MAX_RETRIES", "2")
    monkeypatch.setenv("LLM__RETRY_BASE_DELAY", "0")
    get_settings.cache_clear()
    gateway = YandexGPTLLMGateway(client=_FakeClient(None))
    attempts = 0

    async def fail_once() -> None:
        nonlocal attempts
        attempts += 1
        raise _ProviderStatusError(403)

    with pytest.raises(_ProviderStatusError):
        await gateway._with_retries(fail_once)

    assert attempts == 1


@pytest.mark.asyncio
async def test_chat_complete_uses_yandex_model_uri(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="готово"))],
        usage=SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        ),
    )
    gateway, client = _gateway_with_fake_client(monkeypatch, response)

    content, usage = await gateway.chat_complete(
        [{"role": "user", "content": "начни"}],
        model_override="YandexGPT",
    )

    assert content == "готово"
    assert usage is not None
    assert isinstance(usage, UsageInfo)
    assert client.completions.kwargs["model"] == "gpt://folder123/yandexgpt/latest"
    assert "extra_body" not in client.completions.kwargs
    assert "reasoning" not in client.completions.kwargs


@pytest.mark.asyncio
async def test_chat_with_tools_passes_yandex_function_tools(monkeypatch):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "rag_search",
                "description": "Search documents",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="rag_search",
                                arguments='{"query":"инфляция"}',
                            ),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=5,
            completion_tokens=4,
            total_tokens=9,
        ),
    )
    gateway, client = _gateway_with_fake_client(monkeypatch, response)

    result = await gateway.chat_with_tools(
        [{"role": "user", "content": "найди"}],
        tools,
        model_override="YandexGPT",
    )

    assert result["tool_calls"] == [
        {
            "id": "call_1",
            "name": "rag_search",
            "arguments": '{"query":"инфляция"}',
        }
    ]
    assert client.completions.kwargs["tools"] == tools
    assert client.completions.kwargs["tool_choice"] == "auto"
    assert client.completions.kwargs["stream"] is False


@pytest.mark.asyncio
async def test_chat_stream_yields_text_then_usage(monkeypatch):
    stream = _AsyncStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="При"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="вет"))]
            ),
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=3,
                    completion_tokens=3,
                    total_tokens=6,
                ),
            ),
        ]
    )
    gateway, client = _gateway_with_fake_client(monkeypatch, stream)

    chunks = [
        chunk
        async for chunk in gateway.chat_stream(
            [{"role": "user", "content": "поприветствуй"}],
            model_override="YandexGPT",
        )
    ]

    assert chunks[0] == "При"
    assert chunks[1] == "вет"
    assert isinstance(chunks[2], UsageInfo)
    assert chunks[2].total_tokens == 6
    assert client.completions.kwargs["stream"] is True
    assert client.completions.kwargs["stream_options"] == {"include_usage": True}
