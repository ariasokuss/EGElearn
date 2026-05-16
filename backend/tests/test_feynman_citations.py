from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.AsyncOpenAI = object
    sys.modules["openai"] = openai_stub

from src.learning.feynman import service as feynman_service_module
from src.learning.feynman import prompts as feynman_prompts
from src.learning.feynman.prompts import _build_ask_nova_guidance, build_evaluator_messages
from src.learning.feynman.service import StandardFeynmanService
from src.learning.parser import LessonTheme
from src.learning.schemas import FeynmanMessageRead


@dataclass
class _Block:
    id: uuid.UUID
    points: list[str]


@dataclass
class _StoredMessage:
    role: str
    content: str


@dataclass
class _Session:
    id: uuid.UUID
    status: str
    type: str
    current_iteration: int
    covered_points: list[int | None]
    feynman_block: _Block
    messages: list[_StoredMessage] = field(default_factory=list)


class _FakeLearning:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self._session_factory = object()
        self.saved_user_citations: list[str] | None = None
        self.saved_user_answer: str | None = None
        self.last_scores: list[int | None] | None = None

    async def get_session_with_block(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> _Session | None:
        if session_id != self.session.id:
            return None
        return self.session

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        iteration: int,
        citations: list[str] | None = None,
    ) -> None:
        if role == "user":
            self.saved_user_answer = content
            self.saved_user_citations = citations
        self.session.messages.append(_StoredMessage(role=role, content=content))

    async def update_theme_scores(
        self, session_id: uuid.UUID, scores: list[int | None]
    ) -> None:
        self.last_scores = scores

    async def advance_iteration(self, session_id: uuid.UUID, new_iteration: int) -> None:
        self.session.current_iteration = new_iteration

    async def complete_session(
        self, session_id: uuid.UUID, covered_points: list[int | None]
    ) -> None:
        self.session.status = "completed"
        self.session.covered_points = covered_points

    async def save_session_feedback(self, session_id: uuid.UUID, feedback: list[dict]) -> None:
        return None


class _FakeLLM:
    async def chat_complete(self, messages: list[dict[str, Any]]) -> tuple[str, Any]:
        evaluation = {
            "theme_updates": [{"theme_index": 0, "points": 1}],
            "follow_up": "Please explain further.",
            "all_done": False,
            "theme_feedback": [],
            "feedback_notes": [],
        }
        return json.dumps(evaluation), None


class _FakeFeedbackService:
    def __init__(self, session_factory: object) -> None:
        self.session_factory = session_factory

    async def save_notes(self, **kwargs: Any) -> None:
        return None


class _FakePromptManager:
    def get(self, service: str, key: str) -> str:
        if service == "feynman" and key == "evaluator_system":
            return "system prompt"
        if service == "feynman" and key == "ask_nova_guidance_none":
            return feynman_prompts.ASK_NOVA_GUIDANCE_NONE
        raise KeyError(f"{service}.{key}")

    def get_formatted(self, service: str, key: str, **kwargs: Any) -> str:
        if service == "feynman" and key == "evaluator_user_template":
            return (
                f"Themes:\n{kwargs['themes_with_scores']}\n\n"
                f"History:\n{kwargs['history']}\n\n"
                f"Quote:\n{kwargs['selected_quote_block']}\n\n"
                f"AskNova:\n{kwargs['ask_nova_guidance']}\n\n"
                f"Answer:\n{kwargs['user_answer']}"
            )
        if service == "feynman" and key.startswith("ask_nova_guidance_"):
            templates: dict[str, str] = {
                "ask_nova_guidance_repeat": feynman_prompts.ASK_NOVA_GUIDANCE_REPEAT,
                "ask_nova_guidance_spell": feynman_prompts.ASK_NOVA_GUIDANCE_SPELL,
                "ask_nova_guidance_meaning": feynman_prompts.ASK_NOVA_GUIDANCE_MEANING,
                "ask_nova_guidance_default": feynman_prompts.ASK_NOVA_GUIDANCE_DEFAULT,
            }
            template = templates[key]
            if "{quote}" in template:
                return template.format(quote=kwargs.get("quote", ""))
            return template
        raise KeyError(f"{service}.{key}")


def test_standard_feynman_saves_user_citations_and_streams_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session(
        id=uuid.uuid4(),
        status="active",
        type="standard",
        current_iteration=1,
        covered_points=[None],
        feynman_block=_Block(id=uuid.uuid4(), points=["Theme 1"]),
        messages=[_StoredMessage(role="assistant", content="Start")],
    )
    learning = _FakeLearning(session)
    llm = _FakeLLM()

    captured: dict[str, Any] = {}

    def _capture_evaluator_messages(**kwargs: Any) -> list[dict[str, str]]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        feynman_service_module,
        "build_evaluator_messages",
        _capture_evaluator_messages,
    )
    monkeypatch.setattr(
        feynman_service_module,
        "FeedbackNoteService",
        _FakeFeedbackService,
    )

    service = StandardFeynmanService(
        learning_service=learning, llm=llm, prompt_manager=object()
    )

    async def _collect_chunks() -> list[str]:
        chunks: list[str] = []
        async for chunk in service.handle_answer(
            session_id=session.id,
            user_answer="My answer",
            user_id=uuid.uuid4(),
            user_citations=["Quote A", "Quote B"],
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect_chunks())

    assert learning.saved_user_answer == "My answer"
    assert learning.saved_user_citations == ["Quote A", "Quote B"]
    assert learning.last_scores == [1]
    assert any("summary" in c for c in chunks)
    assert captured["user_citations"] == ["Quote A", "Quote B"]


def test_feynman_message_read_defaults_missing_citations_to_empty_list() -> None:
    payload = {
        "id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "role": "user",
        "content": "Answer",
        "citations": None,
        "iteration": 1,
        "created_at": datetime.now(timezone.utc),
    }
    message = FeynmanMessageRead.model_validate(payload)
    assert message.citations == []


def test_build_evaluator_messages_includes_highlighted_quotes_in_prompt() -> None:
    themes = [LessonTheme(number=1, title="Market size", content="")]
    messages = build_evaluator_messages(
        themes=themes,
        scores=[None],
        history=[{"role": "assistant", "content": "Explain market size."}],
        user_answer="It is about demand.",
        user_citations=["  focus  ", "", "market size means total demand"],
        prompt_manager=_FakePromptManager(),
    )

    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    assert "Quote:\n- focus\n- market size means total demand" in messages[1]["content"]
    assert "AskNova:\nAsk Nova request detected." in messages[1]["content"]


def test_build_evaluator_messages_uses_fallback_without_citations() -> None:
    themes = [LessonTheme(number=1, title="Market size", content="")]
    messages = build_evaluator_messages(
        themes=themes,
        scores=[0],
        history=[],
        user_answer="Guessing here.",
        user_citations=None,
        prompt_manager=_FakePromptManager(),
    )
    assert "No highlighted quote provided." in messages[1]["content"]
    assert feynman_prompts.ASK_NOVA_GUIDANCE_NONE.strip() in messages[1]["content"]


def test_build_ask_nova_guidance_repeat_then_back_to_lesson() -> None:
    guidance = _build_ask_nova_guidance(
        _FakePromptManager(),
        user_answer="Repeat this word please",
        citations=["focus"],
    )
    assert "repeat this quote literally" in guidance.lower()
    assert '"focus"' in guidance
    assert "then continue with one short lesson-focused follow-up question" in guidance.lower()
