"""Unit tests for practice hint delimiter splitting."""

from __future__ import annotations

from src.learning.tests.hint_service import PracticeHintDelimiterSplitter
from src.learning.tests.prompts import PRACTICE_HINT_CHAT_MARKER, PRACTICE_HINT_PANEL_MARKER


def _collect(chunks: list[str]) -> tuple[str, str]:
    s = PracticeHintDelimiterSplitter()
    chat_parts: list[str] = []
    panel_parts: list[str] = []
    for c in chunks:
        for lane, text in s.feed(c):
            if lane == "chat":
                chat_parts.append(text)
            else:
                panel_parts.append(text)
    for lane, text in s.finalize():
        if lane == "chat":
            chat_parts.append(text)
        else:
            panel_parts.append(text)
    return "".join(chat_parts), "".join(panel_parts)


def test_splitter_happy_path() -> None:
    raw = (
        f"{PRACTICE_HINT_CHAT_MARKER}\n"
        "Short chat line.\n"
        f"{PRACTICE_HINT_PANEL_MARKER}\n"
        "Panel hint text."
    )
    chat, panel = _collect([raw])
    assert "Short chat line" in chat
    assert "Panel hint" in panel
    assert PRACTICE_HINT_CHAT_MARKER not in chat
    assert PRACTICE_HINT_PANEL_MARKER not in panel


def test_splitter_chunked() -> None:
    parts = [
        PRACTICE_HINT_CHAT_MARKER[:4],
        PRACTICE_HINT_CHAT_MARKER[4:],
        "\nChat ",
        "more. ",
        PRACTICE_HINT_PANEL_MARKER[:3],
        PRACTICE_HINT_PANEL_MARKER[3:],
        "\nPanel",
        " end",
    ]
    chat, panel = _collect(parts)
    assert "Chat more" in chat
    assert "Panel end" in panel


def test_splitter_no_markers_fallback_chat() -> None:
    chat, panel = _collect(["Only chat without tags."])
    assert "without tags" in chat
    assert panel == ""
