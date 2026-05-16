"""Tests: LLM grading bypass and vision grading for unsupported questions."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.learning.tests.session_service import SessionServiceError, TestSessionService


def _service(s3=None):
    kwargs = {}
    if s3 is not None:
        kwargs["s3"] = s3
    return TestSessionService(session_factory=MagicMock(), **kwargs)


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_exc):
        return None


# --- _requires_llm_grading ---

def test_requires_llm_grading_false_for_unsupported_short():
    assert _service()._requires_llm_grading("short", is_unsupported=True) is False


def test_requires_llm_grading_true_for_supported_short():
    assert _service()._requires_llm_grading("short", is_unsupported=False) is True


def test_requires_llm_grading_false_for_mcq():
    assert _service()._requires_llm_grading("mcq", is_unsupported=False) is False


def test_requires_llm_grading_false_for_none_type():
    assert _service()._requires_llm_grading(None, is_unsupported=False) is False


# --- vision grading ---

def _make_question(points: int = 4, is_unsupported: bool = True, mark_scheme: str | None = "Award 1 mark per correct ray."):
    return SimpleNamespace(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        type="short",
        question="Draw the ray diagram.",
        model_answer="Two rays converging at focal point.",
        points=points,
        is_unsupported=is_unsupported,
        mark_scheme=mark_scheme,
    )


def _make_answer(
    image_key: str | None = "session-answers/s/q/abc.jpg",
    answer_text: str = "",
):
    ans = MagicMock()
    ans.id = uuid.uuid4()
    ans.answer = answer_text
    ans.image_key = image_key
    ans.image_keys = [image_key] if image_key else []
    ans.session_id = uuid.uuid4()
    return ans


@pytest.mark.asyncio
async def test_grade_one_vision_message_built_when_image_key_set():
    """_grade_one must prepend base64 image_url block when answer.image_key is set."""
    import base64
    captured_messages = []

    async def fake_chat_complete(messages, **kwargs):
        captured_messages.extend(messages)
        return '{"earned_marks": 3, "feedback": "Good", "recommendations": ""}', None

    fake_bytes = b"\xff\xd8\xff"  # minimal JPEG magic bytes
    mock_s3 = AsyncMock()
    mock_s3.download_bytes = AsyncMock(return_value=fake_bytes)

    svc = _service(s3=mock_s3)
    svc._llm = MagicMock()
    svc._llm.chat_complete = fake_chat_complete

    question = _make_question()
    answer = _make_answer(image_key="session-answers/s/q/abc.jpg")

    await svc._grade_one(question, answer)

    # The user message content must be a list with image_url as the first block
    user_msg = next(m for m in captured_messages if m["role"] == "user")
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0]["type"] == "image_url"
    expected_data_url = f"data:image/jpeg;base64,{base64.b64encode(fake_bytes).decode()}"
    assert user_msg["content"][0]["image_url"]["url"] == expected_data_url
    assert user_msg["content"][1]["type"] == "text"
    mock_s3.download_bytes.assert_awaited_once_with("session-answers/s/q/abc.jpg")


@pytest.mark.asyncio
async def test_grade_one_vision_message_includes_typed_answer_when_image_is_attached(caplog):
    """Mixed text + image answers must send both parts to the grader."""

    captured_messages = []

    async def fake_chat_complete(messages, **kwargs):
        captured_messages.extend(messages)
        return '{"earned_marks": 4, "feedback": "Good", "recommendations": ""}', None

    mock_s3 = AsyncMock()
    mock_s3.download_bytes = AsyncMock(return_value=b"\xff\xd8\xff")

    svc = _service(s3=mock_s3)
    svc._llm = MagicMock()
    svc._llm.chat_complete = fake_chat_complete

    question = _make_question(points=4)
    answer = _make_answer(
        image_key="session-answers/s/q/lorenz.jpg",
        answer_text="Gini coefficient = A/(A+B), using Extract A.",
    )

    caplog.set_level(logging.INFO, logger="src.learning.tests.session_service")
    await svc._grade_one(question, answer)

    user_msg = next(m for m in captured_messages if m["role"] == "user")
    assert isinstance(user_msg["content"], list)
    text_blocks = [
        block["text"]
        for block in user_msg["content"]
        if block.get("type") == "text"
    ]
    assert any("Gini coefficient = A/(A+B)" in text for text in text_blocks)
    assert any("attached image" in text.lower() for text in text_blocks)
    assert "answer_length=" in caplog.text
    assert "image_count=1" in caplog.text
    assert "typed_answer_present=True" in caplog.text
    assert "Gini coefficient = A/(A+B)" not in caplog.text


@pytest.mark.asyncio
async def test_grade_one_text_only_message_when_no_image_key():
    """_grade_one must NOT modify message content when image_key is None."""
    captured_messages = []

    async def fake_chat_complete(messages, **kwargs):
        captured_messages.extend(messages)
        return '{"earned_marks": 2, "feedback": "OK", "recommendations": ""}', None

    mock_s3 = AsyncMock()
    svc = _service(s3=mock_s3)
    svc._llm = MagicMock()
    svc._llm.chat_complete = fake_chat_complete

    question = _make_question(is_unsupported=True)
    answer = _make_answer(image_key=None)
    answer.answer = "The rays converge."

    await svc._grade_one(question, answer)

    user_msg = next(m for m in captured_messages if m["role"] == "user")
    # content must be a plain string, not a list
    assert isinstance(user_msg["content"], str)
    mock_s3.presigned_get_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_diagram_answer_rejects_mcq_question():
    """save_diagram_answer must raise SessionServiceError for MCQ questions."""
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="mcq",
        points=1,
    )
    session_obj = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        template_id=q_template_id,
        status="active",
    )

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=session_obj)
    db.get = AsyncMock(return_value=question)

    with pytest.raises(SessionServiceError, match="not supported for MCQ"):
        await svc.save_diagram_answer(
            session_id=session_obj.id,
            user_id=user_id,
            question_id=question.id,
            image_key="session-answers/x/y/z.jpg",
            session=db,
        )


@pytest.mark.asyncio
async def test_save_diagram_answer_accepts_short_question():
    """save_diagram_answer accepts non-MCQ short-answer questions (not just is_unsupported)."""
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    sa_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="short",
        points=4,
    )
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = user_id
    session_obj.template_id = q_template_id
    session_obj.status = "active"
    session_obj.started_at = None

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[session_obj, None])
    db.get = AsyncMock(return_value=question)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", sa_id))

    out = await svc.save_diagram_answer(
        session_id=session_obj.id,
        user_id=user_id,
        question_id=question.id,
        image_key="session-answers/x/y/z.jpg",
        session=db,
    )
    assert out.image_key == "session-answers/x/y/z.jpg"
    assert out.answer == ""


@pytest.mark.asyncio
async def test_save_answer_accepts_text_and_image_keys_atomically():
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="short",
        points=4,
    )
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = user_id
    session_obj.template_id = q_template_id
    session_obj.status = "active"
    session_obj.started_at = None

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[session_obj, None])
    db.get = AsyncMock(return_value=question)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    out = await svc.save_answer(
        session_id=session_obj.id,
        user_id=user_id,
        question_id=question.id,
        answer_text="Gini coefficient = A/(A+B), using Extract A.",
        image_keys=[
            "session-answers/x/y/diagram.jpg",
            "session-answers/x/y/extract.png",
        ],
        session=db,
    )

    assert out.answer == "Gini coefficient = A/(A+B), using Extract A."
    assert out.image_key == "session-answers/x/y/diagram.jpg"
    assert out.image_keys == [
        "session-answers/x/y/diagram.jpg",
        "session-answers/x/y/extract.png",
    ]


@pytest.mark.asyncio
async def test_submit_session_regrades_short_answer_when_final_text_changes_after_image_grade():
    """Final typed text must invalidate any earlier image-only background grade."""

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    template_id = uuid.uuid4()
    question_id = uuid.uuid4()
    old_graded_at = datetime.now(timezone.utc)
    question = SimpleNamespace(
        id=question_id,
        template_id=template_id,
        type="short",
        is_unsupported=False,
        points=4,
    )
    existing_answer = SimpleNamespace(
        question_id=question_id,
        answer="",
        image_key="session-answers/s/q/diagram.jpg",
        image_keys=["session-answers/s/q/diagram.jpg"],
        is_skipped=False,
        graded_at=old_graded_at,
        earned_marks=1,
        score=0.25,
        is_correct=False,
        feedback="Image-only feedback",
        recommendations="Old recommendation",
    )
    test_session = SimpleNamespace(
        id=session_id,
        user_id=user_id,
        template_id=template_id,
        template=SimpleNamespace(questions=[question]),
        answers=[existing_answer],
        status="active",
        total_marks=4,
        earned_marks=1,
        score=0.25,
        submitted_at=None,
        started_at=None,
        graded_at=None,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=test_session)
    db.scalars = AsyncMock(side_effect=[
        [question],
        [existing_answer],
        [question],
    ])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    svc = TestSessionService(session_factory=lambda: _AsyncContext(db))

    returned_session, ungraded_ids = await svc.submit_session(
        session_id=session_id,
        user_id=user_id,
        final_answers=[
            {
                "question_id": question_id,
                "answer": "Gini coefficient = A/(A+B), using Extract A.",
            }
        ],
    )

    assert returned_session is test_session
    assert existing_answer.answer == "Gini coefficient = A/(A+B), using Extract A."
    assert existing_answer.graded_at is None
    assert existing_answer.earned_marks is None
    assert existing_answer.score is None
    assert existing_answer.is_correct is None
    assert existing_answer.feedback is None
    assert existing_answer.recommendations is None
    assert ungraded_ids == [question_id]
    assert test_session.status == "grading"


# --- set_question_skipped ---


@pytest.mark.asyncio
async def test_set_question_skipped_creates_skipped_answer_when_none_exists():
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="short",
        points=4,
    )
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = user_id
    session_obj.template_id = q_template_id
    session_obj.status = "active"
    session_obj.started_at = None

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[session_obj, None])
    db.get = AsyncMock(return_value=question)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    out = await svc.set_question_skipped(
        session_id=session_obj.id,
        user_id=user_id,
        question_id=question.id,
        skipped=True,
        session=db,
    )
    assert out.is_skipped is True
    assert out.answer == ""
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_set_question_skipped_updates_existing_answer():
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="short",
        points=4,
    )
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = user_id
    session_obj.template_id = q_template_id
    session_obj.status = "active"

    existing = MagicMock()
    existing.is_skipped = False

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[session_obj, existing])
    db.get = AsyncMock(return_value=question)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    out = await svc.set_question_skipped(
        session_id=session_obj.id,
        user_id=user_id,
        question_id=question.id,
        skipped=True,
        session=db,
    )
    assert out is existing
    assert existing.is_skipped is True


@pytest.mark.asyncio
async def test_set_question_skipped_can_unskip():
    svc = _service()
    user_id = uuid.uuid4()
    q_template_id = uuid.uuid4()
    question = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=q_template_id,
        is_unsupported=False,
        type="short",
        points=4,
    )
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = user_id
    session_obj.template_id = q_template_id
    session_obj.status = "active"

    existing = MagicMock()
    existing.is_skipped = True

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[session_obj, existing])
    db.get = AsyncMock(return_value=question)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    await svc.set_question_skipped(
        session_id=session_obj.id,
        user_id=user_id,
        question_id=question.id,
        skipped=False,
        session=db,
    )
    assert existing.is_skipped is False


@pytest.mark.asyncio
async def test_set_question_skipped_rejects_other_user_session():
    svc = _service()
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    session_obj = MagicMock()
    session_obj.id = uuid.uuid4()
    session_obj.user_id = other_user_id
    session_obj.status = "active"

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=session_obj)

    with pytest.raises(SessionServiceError, match="Session not found"):
        await svc.set_question_skipped(
            session_id=session_obj.id,
            user_id=user_id,
            question_id=uuid.uuid4(),
            skipped=True,
            session=db,
        )
