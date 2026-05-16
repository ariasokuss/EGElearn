"""Tests for chat branching entity fields."""

from src.chat.entities import Conversation, Message, MessageRole


def test_message_has_branching_fields():
    msg = Message(
        id="msg-1",
        conversation_id="conv-1",
        role=MessageRole.USER,
        content="Hello",
        parent_id="msg-0",
        version_index=2,
    )
    assert msg.parent_id == "msg-0"
    assert msg.version_index == 2


def test_message_branching_defaults():
    msg = Message(
        id="msg-1",
        conversation_id="conv-1",
        role=MessageRole.USER,
        content="Hello",
    )
    assert msg.parent_id is None
    assert msg.version_index == 1


def test_conversation_has_active_path():
    conv = Conversation(
        id="conv-1",
        user_id="user-1",
        folder_id=None,
        active_path=["msg-1", "msg-2", "msg-3"],
    )
    assert conv.active_path == ["msg-1", "msg-2", "msg-3"]


def test_conversation_active_path_default():
    conv = Conversation(
        id="conv-1",
        user_id="user-1",
        folder_id=None,
    )
    assert conv.active_path is None
