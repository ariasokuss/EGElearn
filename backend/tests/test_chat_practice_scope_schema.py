from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.chat.schemas import ChatMessageRequest


def test_practice_scope_both_or_neither() -> None:
    with pytest.raises(ValidationError, match="test_session_id and question_id"):
        ChatMessageRequest(
            message="hi",
            folder_id=str(uuid.uuid4()),
            test_session_id=str(uuid.uuid4()),
            question_id=None,
        )


def test_practice_scope_valid_pair() -> None:
    fid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    qid = str(uuid.uuid4())
    req = ChatMessageRequest(
        message="hi",
        folder_id=fid,
        test_session_id=sid,
        question_id=qid,
    )
    assert req.test_session_id == sid
    assert req.question_id == qid


def test_practice_scope_invalid_uuid() -> None:
    with pytest.raises(ValidationError, match="test_session_id must be a valid UUID"):
        ChatMessageRequest(
            message="hi",
            folder_id=str(uuid.uuid4()),
            test_session_id="not-a-uuid",
            question_id=str(uuid.uuid4()),
        )


def test_lesson_id_cannot_combine_with_practice() -> None:
    with pytest.raises(ValidationError, match="lesson_id cannot be combined"):
        ChatMessageRequest(
            message="hi",
            folder_id=str(uuid.uuid4()),
            lesson_id=str(uuid.uuid4()),
            test_session_id=str(uuid.uuid4()),
            question_id=str(uuid.uuid4()),
        )


def test_lesson_id_must_be_uuid() -> None:
    with pytest.raises(ValidationError, match="lesson_id must be a valid UUID"):
        ChatMessageRequest(
            message="hi",
            folder_id=str(uuid.uuid4()),
            lesson_id="not-a-uuid",
        )
