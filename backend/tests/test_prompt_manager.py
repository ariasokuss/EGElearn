"""Tests for PromptManager — get, get_formatted, get_or_none."""

import pytest

from tests.conftest import make_pm
from src.prompts.manager import PromptNotFoundError


class TestGet:
    def test_returns_value_when_key_exists(self):
        pm = make_pm()
        assert (
            pm.get("chat", "retrieval_overflow_note")
            == "Some earlier results were condensed."
        )

    def test_raises_prompt_not_found_on_missing_service(self):
        pm = make_pm()
        with pytest.raises(PromptNotFoundError, match="unknown_service.some_key"):
            pm.get("unknown_service", "some_key")

    def test_raises_prompt_not_found_on_missing_key(self):
        pm = make_pm()
        with pytest.raises(PromptNotFoundError, match="chat.nonexistent"):
            pm.get("chat", "nonexistent")


class TestGetFormatted:
    def test_substitutes_placeholders(self):
        pm = make_pm()
        result = pm.get_formatted(
            "chat",
            "document_registery_block_doc_line",
            name="Physics 101",
            document_id="abc-123",
            page_count=42,
        )
        assert result == '- "Physics 101" (uuid: abc-123, 42 pages)'

    def test_raises_prompt_not_found_on_missing_prompt(self):
        pm = make_pm()
        with pytest.raises(PromptNotFoundError):
            pm.get_formatted("chat", "does_not_exist", foo="bar")

    def test_raises_key_error_on_missing_placeholder(self):
        pm = make_pm()
        # document_registery_block_doc_line needs {name}, {document_id}, {page_count}
        with pytest.raises(KeyError):
            pm.get_formatted("chat", "document_registery_block_doc_line", name="X")


class TestGetOrNone:
    def test_returns_value_when_exists(self):
        pm = make_pm()
        result = pm.get_or_none("chat", "no_current_document_page")
        assert result == "The student is browsing the folder overview."

    def test_returns_none_on_missing_service(self):
        pm = make_pm()
        assert pm.get_or_none("ghost", "key") is None

    def test_returns_none_on_missing_key(self):
        pm = make_pm()
        assert pm.get_or_none("chat", "ghost_key") is None


class TestGetAll:
    def test_returns_all_keys_for_service(self):
        pm = make_pm()
        all_prompts = pm.get_all("chat")
        assert "system_prompt" in all_prompts
        assert "retrieval_overflow_note" in all_prompts

    def test_returns_empty_dict_for_unknown_service(self):
        pm = make_pm()
        assert pm.get_all("unknown") == {}
