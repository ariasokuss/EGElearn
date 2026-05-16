from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from src.chat.agent import DocumentChatAgent
from src.chat.entities import Conversation, Message
from src.chat.router import post_chat_message
from src.chat.schemas import ChatMessageRequest
from src.core.llm_usage import UsageInfo
from src.learning.tests.hint_service import stream_practice_hint_events
from src.learning.tests.prompts import (
    PRACTICE_HINT_CHAT_MARKER,
    PRACTICE_HINT_PANEL_MARKER,
)


class _FakeContextManager:
    def truncate_history(self, *, messages, token_budget):
        return messages

    def build_system_prompt(self, **kwargs):
        return "system prompt"

    def build_llm_messages(self, **kwargs):
        return [
            {"role": "system", "content": kwargs["system_prompt"]},
            {"role": "user", "content": kwargs["user_message"]},
        ]

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0


class _FakeChatRepo:
    def __init__(self, *, user_id: str, conversation_id: str) -> None:
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.messages: list[Message] = []

    async def get_conversation(self, conversation_id: str):
        return Conversation(
            id=conversation_id,
            user_id=self.user_id,
            folder_id=None,
            title="Existing chat",
        )

    async def get_active_path_history(self, conversation_id: str, roles):
        return []

    async def get_active_path(self, conversation_id: str):
        return []

    async def get_next_version_index(self, parent_id, conversation_id, role):
        return 1

    async def save_message(self, message: Message, **kwargs):
        self.messages.append(message)
        return message.id

    async def append_to_active_path(self, conversation_id: str, message_id: str):
        return None

    async def touch_conversation(self, conversation_id: str):
        return None


class _NoUsageChatLLM:
    async def chat_stream(self, messages, model_override=None, reasoning_level=None):
        yield "Assistant "
        yield "reply"


class _RecordingUsageService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log_usage_fire_and_forget(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_direct_chat_logs_estimated_usage_when_stream_omits_usage_info():
    user_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    usage_service = _RecordingUsageService()
    agent = DocumentChatAgent(
        chat_repo=_FakeChatRepo(user_id=user_id, conversation_id=conversation_id),
        retrieval=None,
        embedding=None,
        llm=_NoUsageChatLLM(),
        context_manager=_FakeContextManager(),
        citation_extractor=None,
        s3=None,
        usage_service=usage_service,
    )

    events = [
        event
        async for event in agent.handle_message(
            user_id=user_id,
            conversation_id=conversation_id,
            folder_id=None,
            message="Explain elasticity",
            current_document_id=None,
            current_page=None,
            total_pages=None,
            model="fake-chat-model",
        )
    ]

    assert any(event["event"] == "message_complete" for event in events)
    chat_calls = [
        call for call in usage_service.calls if call["feature"] == "chat"
    ]
    assert len(chat_calls) == 1
    usage = chat_calls[0]["usage"]
    assert isinstance(usage, UsageInfo)
    assert usage.model == "fake-chat-model"
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert usage.cost_usd is None


class _SlowAgent:
    def __init__(self) -> None:
        self.completed = False
        self.cancelled = False

    async def handle_message(self, **kwargs):
        yield {"event": "status", "data": {"step": "thinking"}}
        try:
            await asyncio.sleep(0.03)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        self.completed = True
        yield {"event": "message_complete", "data": {"content": "late answer"}}


@pytest.mark.asyncio
async def test_chat_watchdog_leaves_background_agent_running(monkeypatch):
    from src.chat import router as chat_router_module

    monkeypatch.setattr(chat_router_module, "_SSE_WATCHDOG_TIMEOUT", 0.005)
    agent = _SlowAgent()
    response = await post_chat_message(
        payload=ChatMessageRequest(message="hello"),
        current_user=SimpleNamespace(id=uuid.uuid4()),
        request=SimpleNamespace(
            method="POST",
            url=SimpleNamespace(path="/chat/message"),
            app=SimpleNamespace(state=SimpleNamespace(activity_service=None)),
        ),
        container=SimpleNamespace(session_factory=None),
        agent=agent,
        repo=SimpleNamespace(),
        tests_service=SimpleNamespace(),
        pm=SimpleNamespace(get_or_none=lambda *_args: "prompt"),
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    assert "Response timed out" in "".join(chunks)
    await asyncio.sleep(0.05)
    assert agent.completed is True
    assert agent.cancelled is False


class _NoUsageHintLLM:
    async def chat_stream(self, messages, model_override=None, reasoning_level=None):
        yield (
            f"{PRACTICE_HINT_CHAT_MARKER}\n"
            "Try isolating the variable.\n"
            f"{PRACTICE_HINT_PANEL_MARKER}\n"
            "Move constants to the other side first."
        )


@pytest.mark.asyncio
async def test_practice_hint_logs_estimated_usage_when_stream_omits_usage_info():
    template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=template_id,
        type="short",
        question="Solve x + 2 = 5",
        options=None,
        hint=None,
    )
    usage_service = _RecordingUsageService()

    events = [
        event
        async for event in stream_practice_hint_events(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            question=question,
            template_id=template_id,
            model="fake-hint-model",
            reasoning=None,
            llm=_NoUsageHintLLM(),
            usage_service=usage_service,
            chat_conversation_id=str(uuid.uuid4()),
        )
    ]

    assert any(event["event"] == "hint_complete" for event in events)
    hint_calls = [
        call
        for call in usage_service.calls
        if call["feature"] == "test_practice_hint"
    ]
    assert len(hint_calls) == 1
    usage = hint_calls[0]["usage"]
    assert isinstance(usage, UsageInfo)
    assert usage.model == "fake-hint-model"
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert usage.cost_usd is None
