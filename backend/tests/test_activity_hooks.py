from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks

from src.chat import router as chat_router
from src.chat.entities import Conversation
from src.chat.schemas import ChatMessageRequest
from src.learning import router as learning_router
from src.learning.feynman import router as standard_feynman_router
from src.learning.mini_feynman import router as mini_feynman_router
from src.learning.tests import router as tests_router
from src.learning.tests.schemas import (
    PracticeHintRequest,
    SaveAnswerRequest,
    SkipQuestionRequest,
    StartSessionRequest,
    SubmitAnswerItem,
    SubmitSessionRequest,
)
from src.learning.tests.session_service import TestSessionService as _TestSessionService


UNSAFE_EVENT_KEYS = {
    "answer",
    "answers",
    "assistant_chat",
    "body",
    "chat",
    "content",
    "feedback",
    "hint_panel",
    "message",
    "messages",
    "prompt",
    "question",
    "raw",
    "response",
    "summary",
    "text",
    "transcript",
    "user_answer",
}


def _activity_service() -> SimpleNamespace:
    return SimpleNamespace(log_event_fire_and_forget=Mock())


def _request(activity_service: object | None = None) -> SimpleNamespace:
    state = SimpleNamespace()
    if activity_service is not None:
        state.activity_service = activity_service
    return SimpleNamespace(app=SimpleNamespace(state=state), url=SimpleNamespace(path="/test"), method="POST")


def _user(user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id or uuid.uuid4(), is_active=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _events(activity_service: SimpleNamespace) -> list:
    return [call.args[0] for call in activity_service.log_event_fire_and_forget.call_args_list]


def _event(activity_service: SimpleNamespace, event_type: str):
    return next(event for event in _events(activity_service) if event.event_type == event_type)


def _assert_no_raw_payload(event, *raw_values: str) -> None:
    metadata = event.metadata or {}
    assert UNSAFE_EVENT_KEYS.isdisjoint(metadata)
    dumped = json.dumps(metadata, default=str)
    for raw_value in raw_values:
        assert raw_value not in dumped


def _assert_replay_contains(event, *raw_values: str) -> None:
    replay = event.replay_payload or {}
    dumped = json.dumps(replay, default=str)
    for raw_value in raw_values:
        assert raw_value in dumped


def _assert_replay_items_contain(event, *raw_values: str) -> None:
    replay = event.replay_payload or {}
    assert "items" in replay
    assert "messages" not in replay
    dumped = json.dumps(replay["items"], default=str)
    for raw_value in raw_values:
        assert raw_value in dumped


async def _collect_stream(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_learning_routes_log_lesson_events_after_success() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    lesson_id = uuid.uuid4()
    lesson = SimpleNamespace(
        id=lesson_id,
        user_id=user.id,
        name="Private lesson title",
        description=None,
        content="Private lesson content",
        num_blocks=2,
        created_at=_now(),
    )
    stars = SimpleNamespace(stars=2, study=True, feynman=False, test=True)
    service = SimpleNamespace(
        get_lesson_detail=AsyncMock(return_value=(lesson, [], [], None, None)),
        complete_step=AsyncMock(
            return_value=(stars, {"progress": 66, "mastery": 0.7, "confidence": 0.8})
        ),
        reset_lesson=AsyncMock(),
    )

    await learning_router.get_lesson(
        lesson_id=lesson_id,
        current_user=user,
        request=request,
        db=AsyncMock(),
        service=service,
    )
    await learning_router.complete_step(
        lesson_id=lesson_id,
        body=learning_router.CompleteStepRequest(step=2),
        current_user=user,
        request=request,
        service=service,
    )
    await learning_router.reset_lesson(
        lesson_id=lesson_id,
        current_user=user,
        request=request,
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == [
        "lesson_opened",
        "lesson_step_completed",
        "lesson_reset",
    ]
    opened = _event(activity, "lesson_opened")
    assert opened.user_id == user.id
    assert opened.lesson_id == lesson_id
    assert opened.metadata == {
        "block_count": 0,
        "feynman_block_count": 0,
        "has_progress": False,
        "has_roadmap_context": False,
        "lesson_id": str(lesson_id),
        "lesson_name": "Private lesson title",
    }
    assert opened.replay_payload["refs"] == {"lesson_id": str(lesson_id)}
    _assert_replay_items_contain(opened, "Private lesson title")
    _assert_no_raw_payload(opened, "Private lesson content")
    assert "Private lesson content" not in json.dumps(
        opened.replay_payload, default=str
    )


@pytest.mark.asyncio
async def test_learning_route_success_does_not_require_activity_service() -> None:
    user = _user()
    service = SimpleNamespace(reset_lesson=AsyncMock())

    result = await learning_router.reset_lesson(
        lesson_id=uuid.uuid4(),
        current_user=user,
        request=_request(),
        service=service,
    )

    assert result == {"ok": True}
    service.reset_lesson.assert_awaited_once()


@pytest.mark.asyncio
async def test_test_routes_log_start_and_abort() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    template_id = uuid.uuid4()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    lesson_id = uuid.uuid4()
    now = _now()
    question = SimpleNamespace(
        id=question_id,
        index=0,
        type="mcq",
        question="private question",
        options=["private option"],
        hint="private hint",
        points=1,
        context=None,
        node_ids=None,
        question_number=None,
        is_unsupported=False,
        model_answer=None,
        mark_scheme=None,
        correct_option_index=0,
    )
    template = SimpleNamespace(
        id=template_id,
        user_id=user.id,
        folder_id=folder_id,
        lesson_id=lesson_id,
        name="Private template",
        type="lesson_test",
        status="ready",
        node_ids=None,
        total_questions=1,
        total_marks=1,
        mark_scheme=None,
        original_filename=None,
        created_at=now,
        generation_progress=None,
        question_type_counts=None,
        questions=[question],
    )
    test_session = SimpleNamespace(
        id=session_id,
        template_id=template_id,
        template_name=None,
        session_mode="practice",
        status="not_started",
        earned_marks=None,
        total_marks=1,
        score=None,
        started_at=None,
        submitted_at=None,
        graded_at=None,
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        start_session=AsyncMock(return_value=(test_session, template)),
        abort_session=AsyncMock(return_value=True),
    )

    await tests_router.start_session(
        body=StartSessionRequest(template_id=template_id, mode="practice"),
        current_user=user,
        request=request,
        service=service,
        container=SimpleNamespace(s3=None),
    )
    await tests_router.abort_session(
        session_id=session_id,
        current_user=user,
        request=request,
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == [
        "test_started",
        "test_aborted",
    ]
    assert _event(activity, "test_started").lesson_id == lesson_id
    assert _event(activity, "test_started").metadata["total_questions"] == 1
    _assert_replay_contains(
        _event(activity, "test_started"),
        "private question",
        "private option",
        "Private template",
    )
    assert _event(activity, "test_aborted").test_session_id == session_id
    for event in _events(activity):
        _assert_no_raw_payload(event, "private question", "private option", "Private template")


@pytest.mark.asyncio
async def test_test_routes_log_answer_skip_submit_and_hint_without_raw_text(monkeypatch) -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    raw_answer = "raw private answer text"
    answer = SimpleNamespace(
        question_id=question_id,
        answer=raw_answer,
        is_correct=None,
        score=None,
        earned_marks=None,
        feedback=None,
        recommendations=None,
        answered_at=_now(),
        graded_at=None,
        is_skipped=False,
    )
    test_session = SimpleNamespace(
        id=session_id,
        template_id=uuid.uuid4(),
        session_mode="practice",
        status="graded",
        earned_marks=3,
        total_marks=5,
        score=0.6,
        started_at=_now(),
        submitted_at=_now(),
        graded_at=_now(),
        created_at=_now(),
        updated_at=_now(),
        template=SimpleNamespace(
            questions=[SimpleNamespace(id=question_id, index=1, hint="private hint text")]
        ),
        answers=[answer],
    )
    service = SimpleNamespace(
        save_answer=AsyncMock(return_value=answer),
        grade_single_answer=AsyncMock(),
        set_question_skipped=AsyncMock(return_value=SimpleNamespace(**{**answer.__dict__, "is_skipped": True})),
        submit_session=AsyncMock(return_value=(test_session, [])),
        get_session=AsyncMock(return_value=test_session),
        is_ai_hint_consumed=AsyncMock(return_value=False),
        try_acquire_hint_inflight_lock=AsyncMock(return_value=True),
        record_ai_hint_consumed=AsyncMock(),
        _pm=None,
    )

    async def fake_hint_events(**kwargs):
        yield {
            "event": "hint_complete",
            "data": {
                "assistant_chat": "raw assistant hint line",
                "hint_panel": "raw hint panel text",
            },
        }

    monkeypatch.setattr(tests_router, "stream_practice_hint_events", fake_hint_events)

    await tests_router.save_answer(
        session_id=session_id,
        question_id=question_id,
        body=SaveAnswerRequest(answer=raw_answer),
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        db=AsyncMock(),
        service=service,
    )
    await tests_router.set_question_skipped(
        session_id=session_id,
        question_id=question_id,
        body=SkipQuestionRequest(skipped=True),
        current_user=user,
        request=request,
        db=AsyncMock(),
        service=service,
    )
    await tests_router.submit_session(
        session_id=session_id,
        body=SubmitSessionRequest(
            answers=[SubmitAnswerItem(question_id=question_id, answer=raw_answer)]
        ),
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        service=service,
    )
    test_session.status = "active"
    hint_response = await tests_router.stream_practice_hint(
        session_id=session_id,
        question_id=question_id,
        current_user=user,
        request=request,
        db=AsyncMock(),
        service=service,
        body=PracticeHintRequest(),
    )
    await _collect_stream(hint_response)

    event_types = [event.event_type for event in _events(activity)]
    assert event_types == [
        "answer_saved",
        "question_skipped",
        "test_submitted",
        "hint_used",
    ]
    assert _event(activity, "answer_saved").metadata["answer_length"] == len(raw_answer)
    assert _event(activity, "question_skipped").metadata["skipped"] is True
    assert _event(activity, "test_submitted").metadata["score_percent"] == 60.0
    assert _event(activity, "hint_used").metadata["question_id"] == str(question_id)
    _assert_replay_contains(_event(activity, "answer_saved"), raw_answer)
    _assert_replay_contains(_event(activity, "test_submitted"), raw_answer)
    _assert_replay_contains(
        _event(activity, "hint_used"),
        "raw assistant hint line",
        "raw hint panel text",
    )
    for event in _events(activity):
        assert event.test_session_id == session_id
        _assert_no_raw_payload(event, raw_answer, "raw assistant hint line", "raw hint panel text")


@pytest.mark.asyncio
async def test_submit_session_metadata_counts_final_payload_answers_without_raw_text() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    raw_answer = "raw final submit answer"
    test_session = SimpleNamespace(
        id=session_id,
        template_id=uuid.uuid4(),
        session_mode="practice",
        status="grading",
        earned_marks=None,
        total_marks=5,
        score=None,
        started_at=_now(),
        submitted_at=_now(),
        graded_at=None,
        created_at=_now(),
        updated_at=_now(),
        template=SimpleNamespace(
            questions=[
                SimpleNamespace(
                    id=question_id,
                    index=0,
                    type="short",
                    question="private final submit question",
                    options=None,
                    correct_option_index=None,
                    points=5,
                    question_number="1",
                )
            ]
        ),
        answers=[],
    )
    service = SimpleNamespace(
        submit_session=AsyncMock(return_value=(test_session, [question_id])),
        grade_session=AsyncMock(),
    )

    await tests_router.submit_session(
        session_id=session_id,
        body=SubmitSessionRequest(
            answers=[SubmitAnswerItem(question_id=question_id, answer=raw_answer)]
        ),
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        service=service,
    )

    submitted = _event(activity, "test_submitted")
    assert submitted.metadata["answered_count"] == 1
    assert submitted.metadata["total_questions"] == 1
    assert [item["kind"] for item in submitted.replay_payload["items"]] == [
        "test",
        "question",
        "user_answer",
    ]
    _assert_replay_contains(submitted, raw_answer)
    _assert_no_raw_payload(submitted, raw_answer)


@pytest.mark.asyncio
async def test_check_answer_logs_non_inline_test_answer() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    raw_answer = "3"
    question = SimpleNamespace(
        id=question_id,
        index=0,
        type="mcq",
        question="private checked question",
        options=["private A", "private B", "private C", "private D"],
        correct_option_index=2,
        points=1,
        question_number=None,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(first=Mock(return_value=None)))
    db.get = AsyncMock(return_value=question)
    service = SimpleNamespace(
        check_answer=AsyncMock(
            return_value={
                "question_id": question_id,
                "type": "mcq",
                "answer": raw_answer,
                "answered_at": _now(),
                "graded_at": _now(),
                "is_correct": False,
                "earned_marks": 0,
                "total_marks": 1,
                "score": 0.0,
                "model_answer": "private model answer",
                "correct_option_index": 2,
                "feedback": "private feedback",
                "recommendations": None,
            }
        )
    )

    await tests_router.check_answer(
        session_id=session_id,
        question_id=question_id,
        body=SaveAnswerRequest(answer=raw_answer),
        current_user=user,
        request=request,
        db=db,
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == ["answer_checked"]
    event = _event(activity, "answer_checked")
    assert event.event_group == "test"
    assert event.test_session_id == session_id
    assert event.metadata["question_id"] == str(question_id)
    assert event.metadata["is_correct"] is False
    _assert_replay_items_contain(
        event,
        "private checked question",
        "D. private D",
        "C. private C",
        "private model answer",
        "private feedback",
    )
    _assert_no_raw_payload(
        event,
        "private checked question",
        "private model answer",
        "private feedback",
    )


@pytest.mark.asyncio
async def test_diagram_submit_and_regrade_log_activity() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    image_key = "session-answers/private-key.png"
    question = SimpleNamespace(
        id=question_id,
        index=0,
        type="diagram",
        question="private diagram question",
        options=None,
        correct_option_index=None,
        points=4,
        question_number="1",
    )
    answer = SimpleNamespace(
        question_id=question_id,
        answer="",
        image_key=image_key,
        image_keys=[image_key],
        is_correct=None,
        score=None,
        earned_marks=None,
        feedback=None,
        recommendations=None,
        answered_at=_now(),
        graded_at=None,
        is_skipped=False,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=question)
    service = SimpleNamespace(
        save_diagram_answer=AsyncMock(return_value=answer),
        regrade_answer=AsyncMock(),
        grade_single_answer=AsyncMock(),
    )

    await tests_router.submit_diagram_answer(
        session_id=session_id,
        question_id=question_id,
        body=tests_router.DiagramAnswerRequest(image_key=image_key),
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        service=service,
    )
    await tests_router.regrade_answer(
        session_id=session_id,
        question_id=question_id,
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == [
        "diagram_answer_submitted",
        "answer_regrade_requested",
    ]
    diagram_event = _event(activity, "diagram_answer_submitted")
    assert diagram_event.metadata["used_image"] is True
    _assert_replay_items_contain(
        diagram_event,
        "private diagram question",
        "Image answer uploaded",
    )
    regrade_event = _event(activity, "answer_regrade_requested")
    assert regrade_event.metadata["question_id"] == str(question_id)
    _assert_no_raw_payload(
        diagram_event,
        "private diagram question",
        image_key,
    )


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionFactory:
    def __init__(self, *sessions) -> None:
        self.sessions = list(sessions)

    def __call__(self):
        if self.sessions:
            return _AsyncContext(self.sessions.pop(0))
        return _AsyncContext(AsyncMock())


class _ExecuteResult:
    def __init__(self, row) -> None:
        self.row = row

    def first(self):
        return self.row


class _SqlAlchemyRowLike:
    def __init__(self, *values) -> None:
        self.values = values

    def _tuple(self):
        return self.values


@pytest.mark.asyncio
async def test_inline_lesson_question_save_logs_lesson_answer_without_test_duplicate() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    lesson_id = uuid.uuid4()
    raw_answer = "private inline choice"
    answer = SimpleNamespace(
        question_id=question_id,
        answer=raw_answer,
        is_correct=True,
        score=1.0,
        earned_marks=1,
        feedback=None,
        recommendations=None,
        answered_at=_now(),
        graded_at=_now(),
        is_skipped=False,
    )
    inline_session = SimpleNamespace(id=session_id)
    template = SimpleNamespace(id=uuid.uuid4(), type="inline_quiz", lesson_id=lesson_id)
    question = SimpleNamespace(
        id=question_id,
        index=0,
        type="mcq",
        points=1,
        question="private inline question",
        options=["private option"],
        correct_option_index=0,
        model_answer=None,
        mark_scheme=None,
        question_number=None,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_ExecuteResult(
                _SqlAlchemyRowLike(inline_session, template, question)
            )
        )
    )
    service = SimpleNamespace(save_answer=AsyncMock(return_value=answer))

    await tests_router.save_answer(
        session_id=session_id,
        question_id=question_id,
        body=SaveAnswerRequest(answer=raw_answer),
        current_user=user,
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == ["lesson_question_answered"]
    event = _event(activity, "lesson_question_answered")
    assert event.event_group == "lesson"
    assert event.lesson_id == lesson_id
    assert event.test_session_id == session_id
    assert event.metadata == {
        "question_id": str(question_id),
        "question_type": "mcq",
        "answer_length": len(raw_answer),
        "is_correct": True,
        "earned_marks": 1,
        "total_marks": 1,
        "score_percent": 100.0,
    }
    _assert_replay_contains(event, "private inline question", "private option", raw_answer)
    _assert_no_raw_payload(event, raw_answer)


@pytest.mark.asyncio
async def test_inline_lesson_question_check_logs_wrong_open_answer_without_raw_text() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()
    question_id = uuid.uuid4()
    lesson_id = uuid.uuid4()
    raw_answer = "raw private open answer"
    now = _now()
    result = {
        "question_id": question_id,
        "type": "short",
        "answer": raw_answer,
        "answered_at": now,
        "graded_at": now,
        "is_correct": False,
        "earned_marks": 0,
        "total_marks": 2,
        "score": 0.0,
        "model_answer": "private model answer",
        "correct_option_index": None,
        "feedback": "private feedback",
        "recommendations": "private recommendations",
    }
    inline_session = SimpleNamespace(id=session_id)
    template = SimpleNamespace(id=uuid.uuid4(), type="inline_quiz", lesson_id=lesson_id)
    question = SimpleNamespace(
        id=question_id,
        index=1,
        type="short",
        points=2,
        question="private open question",
        options=None,
        correct_option_index=None,
        model_answer="private model answer",
        mark_scheme="private mark scheme",
        question_number="2",
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ExecuteResult((inline_session, template, question)))
    )
    service = SimpleNamespace(check_answer=AsyncMock(return_value=result))

    await tests_router.check_answer(
        session_id=session_id,
        question_id=question_id,
        body=SaveAnswerRequest(answer=raw_answer),
        current_user=user,
        request=request,
        db=db,
        service=service,
    )

    event = _event(activity, "lesson_question_answered")
    assert event.event_group == "lesson"
    assert event.lesson_id == lesson_id
    assert event.metadata["is_correct"] is False
    assert event.metadata["earned_marks"] == 0
    assert event.metadata["total_marks"] == 2
    _assert_replay_contains(
        event,
        "private open question",
        raw_answer,
        "private model answer",
        "private feedback",
        "private recommendations",
    )
    _assert_no_raw_payload(
        event,
        raw_answer,
        "private model answer",
        "private feedback",
        "private recommendations",
    )


@pytest.mark.asyncio
async def test_grade_session_logs_test_graded_from_injected_activity_service(monkeypatch) -> None:
    activity = _activity_service()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    template_id = uuid.uuid4()
    lesson_id = uuid.uuid4()
    question_id = uuid.uuid4()
    answer = SimpleNamespace(
        question_id=question_id,
        earned_marks=3,
        is_skipped=False,
        graded_at=_now(),
        answer="raw graded answer",
        image_key=None,
        image_keys=[],
        score=0.6,
        feedback="private graded feedback",
        recommendations="private graded recommendation",
        question=SimpleNamespace(
            id=question_id,
            type="short",
            is_unsupported=False,
            points=5,
            question="private graded question",
            model_answer="private graded model answer",
            mark_scheme="private graded mark scheme",
            question_number="1",
        ),
    )
    test_session = SimpleNamespace(
        id=session_id,
        user_id=user_id,
        template_id=template_id,
        answers=[answer],
        total_marks=5,
        earned_marks=None,
        score=None,
        graded_at=None,
        status="grading",
    )
    template = SimpleNamespace(id=template_id, lesson_id=lesson_id)
    db = AsyncMock()

    async def fake_get(model, key, **kwargs):
        if model.__name__ == "TestSession":
            return test_session
        if model.__name__ == "TestTemplate":
            return template
        return None

    db.get = fake_get
    db.scalars = AsyncMock(return_value=[SimpleNamespace(id=question_id, points=5)])
    db.commit = AsyncMock()

    import src.mastery.emitters as mastery_emitters

    monkeypatch.setattr(mastery_emitters, "emit_test_session_events", AsyncMock())
    _TestSessionService._active_grade_sessions.clear()
    service = _TestSessionService(
        session_factory=_SessionFactory(db, AsyncMock()),
        activity_service=activity,
    )
    service._wait_for_individual_grading = AsyncMock(return_value=0)

    await service.grade_session(session_id)

    graded = _event(activity, "test_graded")
    assert graded.user_id == user_id
    assert graded.lesson_id == lesson_id
    assert graded.test_session_id == session_id
    assert graded.metadata == {
        "answered_count": 1,
        "skipped_count": 0,
        "total_questions": 1,
        "earned_marks": 3,
        "total_marks": 5,
        "score_percent": 60.0,
    }
    _assert_replay_contains(
        graded,
        "private graded question",
        "raw graded answer",
        "private graded feedback",
        "private graded recommendation",
    )
    _assert_no_raw_payload(graded, "raw graded answer")


@pytest.mark.asyncio
async def test_chat_message_logs_message_sent_with_replay_payload() -> None:
    activity = _activity_service()
    raw_message = "private chat message"
    assistant_reply = "private assistant reply"

    class Agent:
        async def handle_message(self, **kwargs):
            yield {"event": "message_complete", "data": {"content": assistant_reply}}

    response = await chat_router.post_chat_message(
        payload=ChatMessageRequest(message=raw_message),
        current_user=_user(),
        request=_request(activity),
        container=SimpleNamespace(session_factory=object(), s3=None),
        agent=Agent(),
        repo=SimpleNamespace(),
        tests_service=SimpleNamespace(),
        pm=SimpleNamespace(get_or_none=lambda namespace, key: "prompt"),
    )
    await _collect_stream(response)

    event = _event(activity, "chat_message_sent")
    assert event.event_group == "chat"
    assert event.metadata["message_length"] == len(raw_message)
    assert event.metadata["has_test_scope"] is False
    assert event.metadata["has_lesson_scope"] is False
    _assert_replay_items_contain(event, raw_message, assistant_reply)
    _assert_no_raw_payload(event, raw_message, assistant_reply)


@pytest.mark.asyncio
async def test_chat_message_logs_when_client_does_not_consume_stream() -> None:
    activity = _activity_service()
    raw_message = "private chat message not consumed"
    assistant_reply = "private assistant reply after disconnect"

    class Agent:
        async def handle_message(self, **kwargs):
            yield {"event": "message_complete", "data": {"content": assistant_reply}}

    await chat_router.post_chat_message(
        payload=ChatMessageRequest(message=raw_message),
        current_user=_user(),
        request=_request(activity),
        container=SimpleNamespace(session_factory=object(), s3=None),
        agent=Agent(),
        repo=SimpleNamespace(),
        tests_service=SimpleNamespace(),
        pm=SimpleNamespace(get_or_none=lambda namespace, key: "prompt"),
    )
    await asyncio.sleep(0.01)

    event = _event(activity, "chat_message_sent")
    assert event.metadata["message_length"] == len(raw_message)
    _assert_replay_items_contain(event, raw_message, assistant_reply)
    _assert_no_raw_payload(event, raw_message, assistant_reply)


@pytest.mark.asyncio
async def test_chat_regenerate_logs_branch_reply_with_replay_payload() -> None:
    activity = _activity_service()
    user = _user()
    conversation_id = str(uuid.uuid4())
    assistant_message_id = str(uuid.uuid4())
    user_message_id = str(uuid.uuid4())
    regenerated_message_id = str(uuid.uuid4())
    raw_user_message = "private regenerate prompt"
    assistant_reply = "private regenerated assistant reply"

    class Repo:
        async def get_conversation(self, _conversation_id):
            return Conversation(
                id=conversation_id,
                user_id=str(user.id),
                folder_id=None,
                active_path=[user_message_id, assistant_message_id],
            )

        async def get_message(self, message_id, _conversation_id):
            if message_id == assistant_message_id:
                return chat_router.Message(
                    id=assistant_message_id,
                    conversation_id=conversation_id,
                    role=chat_router.MessageRole.ASSISTANT,
                    content="private old assistant",
                    parent_id=user_message_id,
                )
            if message_id == user_message_id:
                return chat_router.Message(
                    id=user_message_id,
                    conversation_id=conversation_id,
                    role=chat_router.MessageRole.USER,
                    content=raw_user_message,
                )
            return None

        async def update_active_path(self, *_args):
            return None

    class Agent:
        async def handle_message(self, **kwargs):
            yield {
                "event": "message_complete",
                "data": {
                    "content": assistant_reply,
                    "message_id": regenerated_message_id,
                    "citations": [],
                },
            }

    response = await chat_router.regenerate_message(
        conversation_id=conversation_id,
        message_id=assistant_message_id,
        body=chat_router.RegenerateRequest(),
        current_user=user,
        request=_request(activity),
        agent=Agent(),
        repo=Repo(),
        container=SimpleNamespace(session_factory=object(), s3=None),
    )
    await _collect_stream(response)

    assert [event.event_type for event in _events(activity)] == [
        "chat_message_regenerated"
    ]
    event = _event(activity, "chat_message_regenerated")
    assert event.event_group == "chat"
    assert event.metadata["target_role"] == "assistant"
    _assert_replay_items_contain(event, raw_user_message, assistant_reply)
    _assert_no_raw_payload(event, raw_user_message, assistant_reply)


@pytest.mark.asyncio
async def test_chat_switch_branch_logs_activity() -> None:
    activity = _activity_service()
    user = _user()
    conversation_id = str(uuid.uuid4())
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    class Repo:
        async def get_conversation(self, _conversation_id):
            return Conversation(
                id=conversation_id,
                user_id=str(user.id),
                folder_id=None,
                active_path=[first_id],
            )

        async def get_siblings(self, _message_id, _conversation_id):
            return [
                chat_router.Message(
                    id=first_id,
                    conversation_id=conversation_id,
                    role=chat_router.MessageRole.ASSISTANT,
                    content="first",
                    parent_id=None,
                    created_at=_now(),
                ),
                chat_router.Message(
                    id=second_id,
                    conversation_id=conversation_id,
                    role=chat_router.MessageRole.ASSISTANT,
                    content="second",
                    parent_id=None,
                    created_at=_now(),
                ),
            ]

        async def get_subtree_path(self, *_args):
            return [second_id]

        async def update_active_path(self, *_args):
            return None

        async def get_messages_batch(self, *_args):
            return {
                second_id: chat_router.Message(
                    id=second_id,
                    conversation_id=conversation_id,
                    role=chat_router.MessageRole.ASSISTANT,
                    content="second",
                    parent_id=None,
                    created_at=_now(),
                )
            }

        async def get_sibling_info_batch(self, *_args):
            return {second_id: (2, 2)}

    response = await chat_router.switch_branch(
        conversation_id=conversation_id,
        body=chat_router.SwitchBranchRequest(message_id=first_id, direction="next"),
        current_user=user,
        request=_request(activity),
        repo=Repo(),
        container=SimpleNamespace(s3=SimpleNamespace()),
    )

    assert response.active_path == [second_id]
    event = _event(activity, "chat_branch_switched")
    assert event.metadata["direction"] == "next"
    assert event.metadata["from_message_id"] == first_id
    assert event.metadata["to_message_id"] == second_id


@pytest.mark.asyncio
async def test_mini_feynman_logs_start_answer_and_abort_with_replay_payload() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    lesson_id = uuid.uuid4()
    block_id = uuid.uuid4()
    session_id = uuid.uuid4()
    block = SimpleNamespace(
        id=block_id,
        lesson_id=lesson_id,
        user_id=user.id,
        scope=[1],
        question="private feynman question",
        points=["private point"],
        created_at=_now(),
    )
    feynman_session = SimpleNamespace(
        id=session_id,
        feynman_block_id=block_id,
        user_id=user.id,
        status="active",
        type="mini",
        current_iteration=1,
        covered_points=None,
        feedback=None,
        created_at=_now(),
        updated_at=_now(),
    )
    first_message = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content="private first message",
        citations=[],
        iteration=1,
        created_at=_now(),
    )
    service = SimpleNamespace(
        get_feynman_block=AsyncMock(return_value=block),
        create_session=AsyncMock(return_value=feynman_session),
        add_message=AsyncMock(return_value=first_message),
        abort_session=AsyncMock(return_value=SimpleNamespace(**{**feynman_session.__dict__, "status": "aborted"})),
    )

    class Pipeline:
        async def handle_answer(self, **kwargs):
            yield 'event: summary\ndata: {"text": "private feynman summary", "covered": [true], "points": ["private point"], "all_covered": true}\n\n'

    await mini_feynman_router.start_session(
        body=mini_feynman_router.StartSessionRequest(feynman_block_id=block_id),
        current_user=user,
        request=request,
        service=service,
    )
    complete_response = await mini_feynman_router.submit_answer(
        session_id=session_id,
        body=mini_feynman_router.AnswerRequest(answer="private feynman answer"),
        current_user=user,
        request=request,
        pipeline=Pipeline(),
    )
    await _collect_stream(complete_response)
    await mini_feynman_router.abort_session(
        session_id=session_id,
        current_user=user,
        request=request,
        service=service,
    )

    assert [event.event_type for event in _events(activity)] == [
        "feynman_started",
        "feynman_completed",
        "feynman_aborted",
    ]
    assert _event(activity, "feynman_started").lesson_id == lesson_id
    assert _event(activity, "feynman_started").entity_id == session_id
    _assert_replay_items_contain(_event(activity, "feynman_started"), "private first message")
    assert _event(activity, "feynman_completed").metadata["answer_length"] == len(
        "private feynman answer"
    )
    _assert_replay_items_contain(
        _event(activity, "feynman_completed"),
        "private feynman answer",
        "private feynman summary",
    )
    assert _event(activity, "feynman_aborted").entity_id == session_id
    for event in _events(activity):
        _assert_no_raw_payload(
            event,
            "private feynman question",
            "private first message",
            "private feynman answer",
            "private feynman summary",
            "private point",
        )


@pytest.mark.asyncio
async def test_standard_feynman_logs_start_complete_and_abort_with_replay_payload() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    lesson_id = uuid.uuid4()
    session_id = uuid.uuid4()
    block_id = uuid.uuid4()

    class Pipeline:
        async def start_session(self, **kwargs):
            yield "event: token\ndata: {\"content\": \"private opening\"}\n\n"
            yield (
                "event: session_started\n"
                f"data: {{\"session_id\": \"{session_id}\", \"feynman_block_id\": \"{block_id}\", \"theme_titles\": [\"private theme\"], \"theme_scores\": [null]}}\n\n"
            )

        async def handle_answer(self, **kwargs):
            yield (
                "event: summary\n"
                "data: {\"theme_scores\": [2], \"theme_titles\": [\"private theme\"], \"all_covered\": true, \"feedback\": [{\"theme\": \"private theme\", \"feedback\": \"private feedback\"}]}\n\n"
            )

        async def abort_session(self, *args, **kwargs):
            return SimpleNamespace(
                id=session_id,
                feynman_block_id=block_id,
                user_id=user.id,
                status="aborted",
                type="standard",
                current_iteration=2,
                covered_points=[2],
                feedback=None,
                created_at=_now(),
                updated_at=_now(),
            )

    pipeline = Pipeline()
    started_response = await standard_feynman_router.start_session(
        body=standard_feynman_router.StartStandardSessionRequest(lesson_id=lesson_id),
        current_user=user,
        request=request,
        pipeline=pipeline,
    )
    await _collect_stream(started_response)
    completed_response = await standard_feynman_router.submit_answer(
        session_id=session_id,
        body=standard_feynman_router.AnswerRequest(answer="private standard answer"),
        current_user=user,
        request=request,
        pipeline=pipeline,
    )
    await _collect_stream(completed_response)
    await standard_feynman_router.abort_session(
        session_id=session_id,
        current_user=user,
        request=request,
        body=standard_feynman_router.AbortSessionRequest(exhausted=True),
        pipeline=pipeline,
    )

    assert [event.event_type for event in _events(activity)] == [
        "feynman_started",
        "feynman_completed",
        "feynman_aborted",
    ]
    assert _event(activity, "feynman_started").lesson_id == lesson_id
    assert _event(activity, "feynman_started").entity_id == session_id
    _assert_replay_items_contain(_event(activity, "feynman_started"), "private opening")
    assert _event(activity, "feynman_completed").metadata["answer_length"] == len(
        "private standard answer"
    )
    _assert_replay_items_contain(
        _event(activity, "feynman_completed"),
        "private standard answer",
        "private feedback",
    )
    assert _event(activity, "feynman_aborted").metadata["exhausted"] is True
    for event in _events(activity):
        _assert_no_raw_payload(
            event,
            "private opening",
            "private theme",
            "private feedback",
            "private standard answer",
        )


@pytest.mark.asyncio
async def test_standard_feynman_follow_up_answer_logs_replay_payload() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()

    class Pipeline:
        async def handle_answer(self, **kwargs):
            yield "event: token\ndata: {\"content\": \"private follow-up\"}\n\n"
            yield (
                "event: message_complete\n"
                "data: {\"role\": \"assistant\", \"content\": \"private follow-up\", \"iteration\": 2, \"theme_scores\": [null], \"citations\": []}\n\n"
            )

    response = await standard_feynman_router.submit_answer(
        session_id=session_id,
        body=standard_feynman_router.AnswerRequest(
            answer="private standard follow-up answer"
        ),
        current_user=user,
        request=request,
        pipeline=Pipeline(),
    )
    await _collect_stream(response)

    assert [event.event_type for event in _events(activity)] == ["feynman_answered"]
    event = _event(activity, "feynman_answered")
    assert event.event_group == "feynman"
    assert event.entity_id == session_id
    assert event.metadata["answer_length"] == len("private standard follow-up answer")
    assert event.metadata["reply_length"] == len("private follow-up")
    _assert_replay_items_contain(
        event,
        "private standard follow-up answer",
        "private follow-up",
    )
    _assert_no_raw_payload(
        event,
        "private standard follow-up answer",
        "private follow-up",
    )


@pytest.mark.asyncio
async def test_feynman_abort_does_not_log_when_session_was_already_completed() -> None:
    activity = _activity_service()
    request = _request(activity)
    user = _user()
    session_id = uuid.uuid4()

    service = SimpleNamespace(
        abort_session=AsyncMock(
            return_value=SimpleNamespace(
                id=session_id,
                feynman_block_id=uuid.uuid4(),
                user_id=user.id,
                status="completed",
                type="mini",
                current_iteration=1,
                covered_points=None,
                feedback=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
    )

    await mini_feynman_router.abort_session(
        session_id=session_id,
        current_user=user,
        request=request,
        service=service,
    )

    assert _events(activity) == []
