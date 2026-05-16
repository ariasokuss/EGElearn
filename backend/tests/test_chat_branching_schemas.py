"""Tests for chat branching schemas."""

import uuid
from datetime import datetime

import pytest

from src.chat.schemas import (
    MessageSchema,
    SwitchBranchRequest,
    SwitchBranchResponse,
)


def test_message_schema_includes_branching_fields():
    msg = MessageSchema(
        id=str(uuid.uuid4()),
        role="assistant",
        content="Hello",
        metadata={},
        created_at=datetime.now(),
        parent_id=str(uuid.uuid4()),
        sibling_count=3,
        version_index=2,
    )
    assert msg.sibling_count == 3
    assert msg.version_index == 2
    assert msg.parent_id is not None


def test_message_schema_defaults():
    msg = MessageSchema(
        id=str(uuid.uuid4()),
        role="user",
        content="Hi",
        metadata={},
        created_at=datetime.now(),
    )
    assert msg.sibling_count == 1
    assert msg.version_index == 1
    assert msg.parent_id is None


def test_switch_branch_request_valid():
    req = SwitchBranchRequest(
        message_id=str(uuid.uuid4()),
        direction="next",
    )
    assert req.direction == "next"


def test_switch_branch_request_prev():
    req = SwitchBranchRequest(
        message_id=str(uuid.uuid4()),
        direction="prev",
    )
    assert req.direction == "prev"


def test_switch_branch_request_invalid_direction():
    with pytest.raises(Exception):
        SwitchBranchRequest(
            message_id=str(uuid.uuid4()),
            direction="up",
        )


def test_switch_branch_request_invalid_message_id():
    with pytest.raises(Exception):
        SwitchBranchRequest(
            message_id="not-a-uuid",
            direction="next",
        )


def test_switch_branch_response():
    msg_id = str(uuid.uuid4())
    resp = SwitchBranchResponse(
        active_path=[msg_id],
        messages=[
            MessageSchema(
                id=msg_id,
                role="assistant",
                content="Response",
                metadata={},
                created_at=datetime.now(),
                sibling_count=2,
                version_index=1,
            )
        ],
    )
    assert len(resp.active_path) == 1
    assert len(resp.messages) == 1
