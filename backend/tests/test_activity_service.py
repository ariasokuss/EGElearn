from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.activity.service import (
    ActivityEventInput,
    ActivityService,
    build_activity_sessions,
    sanitize_metadata,
)
from src.learning.tests.activity_replay import (
    answer_replay_payload,
    submit_session_replay_payload,
)


def _event(
    event_type: str,
    created_at: datetime,
    metadata: dict | None = None,
    **overrides,
):
    base = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_type=event_type,
        event_group=event_type.split("_", 1)[0],
        created_at=created_at,
        request_path=None,
        http_method=None,
        route_label=None,
        entity_type=None,
        entity_id=None,
        folder_id=None,
        lesson_id=None,
        test_session_id=None,
        metadata=metadata or {},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _AsyncSessionCM:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_sanitize_metadata_removes_raw_content_recursively():
    sanitized = sanitize_metadata(
        {
            "answer": "raw answer",
            "email": "student@example.com",
            "message": "raw chat",
            "password": "secret-password",
            "prompt": "raw prompt",
            "response": "raw response",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "answer_length": 17,
            "score_percent": 78,
            "nested": {
                "safe": "kept",
                "body": "hidden",
                "question": "hidden",
                "summary": "hidden",
                "feedback": "hidden",
                "google_credential": "hidden",
                "id_token": "hidden",
                "assistant_chat": "hidden",
                "hint_panel": "hidden",
                "items": [{"content": "hidden"}, {"question_index": 2}],
            },
        }
    )

    assert sanitized == {
        "answer_length": 17,
        "score_percent": 78,
        "nested": {"safe": "kept", "items": [{}, {"question_index": 2}]},
    }


def test_build_activity_sessions_splits_after_one_hour_gap():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("lesson_opened", start),
            _event("answer_saved", start + timedelta(minutes=30)),
            _event("test_submitted", start + timedelta(hours=1, minutes=31)),
        ]
    )

    assert len(sessions) == 2
    assert [session.event_count for session in sessions] == [1, 2]


def test_build_activity_sessions_orders_sessions_newest_first_and_events_chronologically():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("chat_message_sent", start + timedelta(hours=2, minutes=5)),
            _event("lesson_opened", start),
            _event("answer_saved", start + timedelta(minutes=5)),
            _event("test_submitted", start + timedelta(hours=2)),
        ]
    )

    assert [session.start_at for session in sessions] == [
        start + timedelta(hours=2),
        start,
    ]
    assert [event.created_at for event in sessions[0].events] == [
        start + timedelta(hours=2),
        start + timedelta(hours=2, minutes=5),
    ]
    assert [event.created_at for event in sessions[1].events] == [
        start,
        start + timedelta(minutes=5),
    ]


def test_build_activity_sessions_derives_low_score_and_chat_signal():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("test_submitted", start, {"score_percent": 42}),
            _event("chat_message_sent", start + timedelta(minutes=3), {"message_length": 120}),
        ]
    )

    assert "low_score" in sessions[0].signals
    assert "chat_after_low_score" in sessions[0].signals
    assert "inactive_after_bad_result" not in sessions[0].signals


def test_build_activity_sessions_derives_chat_opened_after_low_score_signal():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("test_submitted", start, {"score_percent": 42}),
            _event("chat_opened", start + timedelta(minutes=3), {"surface": "lesson_panel"}),
        ]
    )

    assert "low_score" in sessions[0].signals
    assert "chat_after_low_score" in sessions[0].signals
    assert "inactive_after_bad_result" not in sessions[0].signals
    assert (
        build_activity_sessions(
            [_event("chat_opened", start, {"surface": "lesson_panel"})]
        )[0].summary
        == "Used chat"
    )


def test_build_activity_sessions_adds_short_action_labels_for_timeline_chips():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("lesson_opened", start, event_group="lesson"),
            _event("lesson_question_answered", start + timedelta(seconds=1), event_group="lesson"),
            _event("chat_opened", start + timedelta(seconds=2), event_group="chat"),
            _event("test_started", start + timedelta(seconds=3), event_group="test"),
        ]
    )

    assert [event.action_label for event in sessions[0].events] == [
        "Opened",
        "Question Answered",
        "Opened",
        "Started",
    ]


def test_build_activity_sessions_labels_unskip_action_distinctly():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event(
                "question_skipped",
                start,
                {"skipped": False},
                event_group="test",
            )
        ]
    )

    assert sessions[0].events[0].action_label == "Question Unskipped"


def test_build_activity_sessions_exposes_replay_payload_for_admin_timeline():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    replay_payload = {
        "schema_version": 1,
        "items": [
            {"kind": "user_answer", "title": "Answer", "text": "raw user answer"},
            {"kind": "feedback", "title": "Feedback", "text": "raw feedback"},
        ],
    }

    sessions = build_activity_sessions(
        [
            _event(
                "lesson_question_answered",
                start,
                {"is_correct": False},
                event_group="lesson",
                replay_payload=replay_payload,
            ),
        ]
    )

    assert sessions[0].events[0].replay_payload == replay_payload


def test_build_activity_sessions_formats_numeric_mcq_replay_as_letters():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    replay_payload = {
        "schema_version": 1,
        "items": [
            {
                "kind": "question",
                "title": "Question 1",
                "text": "Pick the rational decision.",
                "options": ["Cheapest", "Hindsight", "Objective", "Moral"],
            },
            {"kind": "user_answer", "title": "User answer", "text": "3"},
            {"kind": "answer_key", "title": "Correct option", "value": 3},
        ],
    }

    sessions = build_activity_sessions(
        [
            _event(
                "lesson_question_answered",
                start,
                {"is_correct": False},
                event_group="lesson",
                replay_payload=replay_payload,
            ),
        ]
    )

    items = sessions[0].events[0].replay_payload["items"]
    assert items[0]["options"] == [
        {
            "label": "A",
            "text": "Cheapest",
            "value": "A. Cheapest",
            "is_selected": False,
            "is_correct": False,
        },
        {
            "label": "B",
            "text": "Hindsight",
            "value": "B. Hindsight",
            "is_selected": False,
            "is_correct": False,
        },
        {
            "label": "C",
            "text": "Objective",
            "value": "C. Objective",
            "is_selected": False,
            "is_correct": True,
        },
        {
            "label": "D",
            "text": "Moral",
            "value": "D. Moral",
            "is_selected": True,
            "is_correct": False,
        },
    ]
    assert items[1]["text"] == "D. Moral"
    assert items[1]["absorbed_into_options"] is True
    assert items[2]["value"] == "C. Objective"
    assert items[2]["absorbed_into_options"] is True


def test_build_activity_sessions_keeps_mcq_selection_scoped_to_question():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    replay_payload = {
        "schema_version": 1,
        "items": [
            {
                "kind": "question",
                "title": "Question 1",
                "text": "Pick one.",
                "options": ["Alpha", "Beta"],
            },
            {"kind": "user_answer", "title": "User answer", "text": "1"},
            {"kind": "answer_key", "title": "Correct option", "value": 1},
            {
                "kind": "question",
                "title": "Question 2",
                "text": "Pick another.",
                "options": ["Gamma", "Delta"],
            },
            {"kind": "user_answer", "title": "User answer", "text": "0"},
            {"kind": "answer_key", "title": "Correct option", "value": 2},
        ],
    }

    sessions = build_activity_sessions(
        [
            _event(
                "lesson_question_answered",
                start,
                {"is_correct": False},
                event_group="lesson",
                replay_payload=replay_payload,
            ),
        ]
    )

    items = sessions[0].events[0].replay_payload["items"]
    assert items[0]["options"][1]["is_selected"] is True
    assert items[0]["options"][0]["is_correct"] is True
    assert items[3]["options"][0]["is_selected"] is True
    assert items[3]["options"][1]["is_correct"] is True


def test_answer_replay_payload_formats_mcq_indices_as_letters():
    question_id = uuid.uuid4()
    question = SimpleNamespace(
        id=question_id,
        index=0,
        type="mcq",
        question="Pick the rational decision.",
        options=["Cheapest", "Hindsight", "Objective", "Moral"],
        correct_option_index=2,
        points=1,
        question_number=None,
    )
    result = SimpleNamespace(
        question=question,
        answer="3",
        is_correct=False,
        score=0.0,
        earned_marks=0,
        graded_at=None,
    )

    payload = answer_replay_payload(
        question=question,
        question_id=question_id,
        answer_text="3",
        result=result,
    )

    items = payload["items"]
    assert items[0]["options"] == [
        "A. Cheapest",
        "B. Hindsight",
        "C. Objective",
        "D. Moral",
    ]
    assert items[1]["text"] == "D. Moral"
    assert items[-1]["value"] == "C. Objective"


def test_submit_session_replay_payload_does_not_lazy_load_answer_question():
    """Regression: submit_session passes detached SessionAnswer instances; the
    payload builder must resolve the question via the template, never via
    lazy-load on the answer (which would raise DetachedInstanceError)."""

    class _DetachedAnswer:
        def __init__(self, question_id: uuid.UUID, answer: str) -> None:
            self.question_id = question_id
            self.answer = answer
            self.is_correct = False
            self.score = 0.0
            self.earned_marks = 0
            self.graded_at = None

        def __getattr__(self, name: str):
            if name == "question":
                raise AssertionError(
                    "must not lazy-load 'question' on a detached answer"
                )
            raise AttributeError(name)

    question_id = uuid.uuid4()
    template = SimpleNamespace(
        id=uuid.uuid4(),
        questions=[
            SimpleNamespace(
                id=question_id,
                index=0,
                type="short",
                question="Define entropy.",
                options=None,
                correct_option_index=None,
                points=2,
                question_number="1",
            )
        ],
    )
    test_session = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=template.id,
        template=template,
        answers=[_DetachedAnswer(question_id, "lalalal")],
        earned_marks=0,
        total_marks=2,
        score=0.0,
        status="grading",
    )

    payload = submit_session_replay_payload(
        test_session=test_session,
        submitted_answers=[
            SimpleNamespace(question_id=question_id, answer="lalalal"),
        ],
    )

    assert [item["kind"] for item in payload["items"]] == [
        "test",
        "question",
        "user_answer",
    ]
    dumped = json.dumps(payload, default=str)
    assert "lalalal" in dumped
    assert "Define entropy." in dumped


def test_submit_session_replay_payload_skips_unanswered_questions():
    question_id = uuid.uuid4()
    empty_question_id = uuid.uuid4()
    template = SimpleNamespace(
        id=uuid.uuid4(),
        questions=[
            SimpleNamespace(
                id=question_id,
                index=0,
                type="short",
                question="Answered question.",
                options=None,
                correct_option_index=None,
                points=2,
                question_number="1",
            ),
            SimpleNamespace(
                id=empty_question_id,
                index=1,
                type="short",
                question="Empty question.",
                options=None,
                correct_option_index=None,
                points=2,
                question_number="2",
            ),
        ],
    )
    test_session = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=template.id,
        template=template,
        answers=[],
        earned_marks=None,
        total_marks=4,
        score=None,
        status="grading",
    )

    payload = submit_session_replay_payload(
        test_session=test_session,
        submitted_answers=[
            SimpleNamespace(question_id=question_id, answer="final answer"),
            SimpleNamespace(question_id=empty_question_id, answer=""),
        ],
    )

    dumped = json.dumps(payload, default=str)
    assert "Answered question." in dumped
    assert "final answer" in dumped
    assert "Empty question." not in dumped


def test_build_activity_sessions_does_not_mark_aborted_test_as_abandoned():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    test_session_id = uuid.uuid4()
    sessions = build_activity_sessions(
        [
            _event(
                "test_started",
                start,
                test_session_id=test_session_id,
            ),
            _event(
                "test_aborted",
                start + timedelta(minutes=3),
                test_session_id=test_session_id,
            ),
        ]
    )

    assert "abandoned_test" not in sessions[0].signals


def test_build_activity_sessions_does_not_mark_prior_chat_as_after_low_score():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    sessions = build_activity_sessions(
        [
            _event("chat_message_sent", start, {"message_length": 120}),
            _event("test_submitted", start + timedelta(minutes=3), {"score_percent": 42}),
        ]
    )

    assert "low_score" in sessions[0].signals
    assert "chat_after_low_score" not in sessions[0].signals
    assert "inactive_after_bad_result" in sessions[0].signals


def test_build_activity_sessions_derives_abandoned_test_signal():
    start = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    test_session_id = uuid.uuid4()
    sessions = build_activity_sessions(
        [
            _event("test_started", start, test_session_id=test_session_id),
            _event("answer_saved", start + timedelta(minutes=2), test_session_id=test_session_id),
        ]
    )

    assert "abandoned_test" in sessions[0].signals


@pytest.mark.asyncio
async def test_log_event_inserts_sanitized_record():
    session = AsyncMock()
    session.add = MagicMock()
    session_factory = MagicMock(return_value=_AsyncSessionCM(session))
    service = ActivityService(session_factory)
    user_id = uuid.uuid4()

    await service.log_event(
        ActivityEventInput(
            user_id=user_id,
            event_type="answer_saved",
            event_group="test",
            metadata={"answer": "raw text", "answer_length": 8},
        )
    )

    session.add.assert_called_once()
    added = session.add.call_args.args[0]
    assert added.user_id == user_id
    assert added.event_type == "answer_saved"
    assert added.event_metadata == {"answer_length": 8}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_event_keeps_raw_content_only_in_replay_payload():
    session = AsyncMock()
    session.add = MagicMock()
    session_factory = MagicMock(return_value=_AsyncSessionCM(session))
    service = ActivityService(session_factory)
    user_id = uuid.uuid4()

    await service.log_event(
        ActivityEventInput(
            user_id=user_id,
            event_type="answer_saved",
            event_group="test",
            metadata={"answer": "raw answer", "answer_length": 10},
            replay_payload={
                "schema_version": 1,
                "items": [
                    {"kind": "user_answer", "title": "Answer", "text": "raw answer"},
                    {"kind": "score", "title": "Score", "value": "1/2"},
                ],
                "refs": {"question_id": uuid.uuid4()},
            },
        )
    )

    added = session.add.call_args.args[0]
    assert added.event_metadata == {"answer_length": 10}
    assert added.replay_payload["schema_version"] == 1
    assert added.replay_payload["items"][0]["text"] == "raw answer"
    assert isinstance(added.replay_payload["refs"]["question_id"], str)
