"""Unit tests for HighlightService — schemas and computed type only (no DB)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.learning.highlights.schemas import HighlightRead


def _make_read(**kwargs) -> HighlightRead:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        lesson_id=uuid.uuid4(),
        text="some text",
        comment=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return HighlightRead(**defaults)


def test_type_is_highlight_when_comment_is_none():
    h = _make_read(comment=None)
    assert h.type == "highlight"


def test_type_is_highlight_when_comment_is_empty():
    h = _make_read(comment="")
    assert h.type == "highlight"


def test_type_is_note_when_comment_is_set():
    h = _make_read(comment="my note")
    assert h.type == "note"


def test_type_reverts_to_highlight_when_comment_cleared():
    h = _make_read(comment="had a comment")
    h2 = h.model_copy(update={"comment": None})
    assert h2.type == "highlight"
