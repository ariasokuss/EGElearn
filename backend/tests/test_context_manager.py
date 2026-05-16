"""Tests for ContextManager — prompt building, truncation, deduplication."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.chat.context_manager import ContextManager
from src.chat.entities import (
    DocumentInfo,
    Message,
    MessageRole,
    RetrievedChunk,
    UserContext,
)
from src.chat.prompts import (
    GENERAL_SYSTEM_PROMPT_TEMPLATE,
    PRACTICE_SCOPE_BLOCK_TEMPLATE,
    SYSTEM_PROMPT_TEMPLATE,
)
from src.prompts.manager import PromptNotFoundError
from tests.conftest import CHAT_PROMPTS, make_pm


def make_cm(overrides: dict[str, str] | None = None) -> ContextManager:
    """Build a ContextManager with a fully-seeded or overridden PromptManager."""
    if overrides:
        prompts = {**CHAT_PROMPTS, **overrides}
        pm = make_pm(prompts)
    else:
        pm = make_pm()
    return ContextManager(chars_per_token=4, prompt_manager=pm)


def make_doc(
    name: str = "Doc A", doc_id: str = "doc-1", pages: int = 10
) -> DocumentInfo:
    return DocumentInfo(document_id=doc_id, name=name, page_count=pages)


def make_ctx(
    doc_id: str | None = None,
    doc_name: str | None = None,
    page: int | None = None,
    total: int | None = None,
) -> UserContext:
    return UserContext(
        folder_id="folder-1",
        current_document_id=doc_id,
        current_document_name=doc_name,
        current_page=page,
        total_pages=total,
    )


# ── Construction ──────────────────────────────────────────────────────────────


class TestConstruction:
    def test_raises_without_prompt_manager(self):
        with pytest.raises(ValueError, match="PromptManager"):
            ContextManager(prompt_manager=None)

    def test_builds_successfully_with_full_pm(self):
        cm = make_cm()
        assert cm is not None


# ── Document registry block ───────────────────────────────────────────────────


class TestDocumentRegistryBlock:
    def test_no_docs_returns_no_docs_prompt(self):
        cm = make_cm()
        result = cm._build_document_registry_block([])
        assert result == CHAT_PROMPTS["document_registery_block_no_docs"]

    def test_single_doc_formats_correctly(self):
        cm = make_cm()
        doc = make_doc("Physics 101", "doc-abc", 55)
        result = cm._build_document_registry_block([doc])
        assert '"Physics 101"' in result
        assert "doc-abc" in result
        assert "55 pages" in result

    def test_multiple_docs_one_line_each(self):
        cm = make_cm()
        docs = [make_doc("A", "id-1", 5), make_doc("B", "id-2", 10)]
        result = cm._build_document_registry_block(docs)
        lines = result.splitlines()
        assert len(lines) == 2
        assert "id-1" in lines[0]
        assert "id-2" in lines[1]

    def test_raises_when_no_docs_key_missing(self):
        prompts = {
            k: v
            for k, v in CHAT_PROMPTS.items()
            if k != "document_registery_block_no_docs"
        }
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm._build_document_registry_block([])

    def test_raises_when_doc_line_key_missing(self):
        prompts = {
            k: v
            for k, v in CHAT_PROMPTS.items()
            if k != "document_registery_block_doc_line"
        }
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm._build_document_registry_block([make_doc()])


# ── Current page block ────────────────────────────────────────────────────────


class TestCurrentPageBlock:
    def test_no_document_returns_overview_prompt(self):
        cm = make_cm()
        ctx = make_ctx()
        result = cm._build_current_page_block(ctx)
        assert result == CHAT_PROMPTS["no_current_document_page"]

    def test_with_document_formats_name_and_pages(self):
        cm = make_cm()
        ctx = make_ctx(doc_id="doc-1", doc_name="Chemistry", page=3, total=20)
        result = cm._build_current_page_block(ctx)
        assert "Chemistry" in result
        assert "3" in result
        assert "20" in result

    def test_falls_back_to_doc_id_when_name_is_none(self):
        cm = make_cm()
        ctx = make_ctx(doc_id="doc-xyz", doc_name=None, page=1, total=5)
        result = cm._build_current_page_block(ctx)
        assert "doc-xyz" in result

    def test_raises_when_no_current_document_key_missing(self):
        prompts = {
            k: v for k, v in CHAT_PROMPTS.items() if k != "no_current_document_page"
        }
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm._build_current_page_block(make_ctx())

    def test_raises_when_current_document_key_missing(self):
        prompts = {k: v for k, v in CHAT_PROMPTS.items() if k != "current_document"}
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm._build_current_page_block(make_ctx(doc_id="x", page=1, total=5))


# ── Iteration guidance ────────────────────────────────────────────────────────


class TestIterationGuidance:
    # max_iterations = 5, so indices: 1,2=early; 3=early(no chunks); 4=penultimate; 5=final

    def test_early_iteration_with_chunks_is_guidance_2(self):
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=1, max_iterations=5, chunks_in_context=3
        )
        assert result == CHAT_PROMPTS["iteration_guidance_2"]

    def test_early_iteration_no_chunks_after_first_is_guidance_1(self):
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=2, max_iterations=5, chunks_in_context=0
        )
        assert result == CHAT_PROMPTS["iteration_guidance_1"]

    def test_first_iteration_no_chunks_is_guidance_2(self):
        # iteration == 1 → condition `chunks_in_context == 0 and current_iteration > 1` is False
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=1, max_iterations=5, chunks_in_context=0
        )
        assert result == CHAT_PROMPTS["iteration_guidance_2"]

    def test_penultimate_with_chunks_is_guidance_4(self):
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=4, max_iterations=5, chunks_in_context=2
        )
        assert result == CHAT_PROMPTS["iteration_guidance_4"]

    def test_penultimate_no_chunks_is_guidance_3(self):
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=4, max_iterations=5, chunks_in_context=0
        )
        assert result == CHAT_PROMPTS["iteration_guidance_3"]

    def test_final_iteration_is_guidance_5(self):
        cm = make_cm()
        result = cm._build_iteration_guidance(
            current_iteration=5, max_iterations=5, chunks_in_context=0
        )
        assert result == CHAT_PROMPTS["iteration_guidance_5"]

    @pytest.mark.parametrize(
        "key",
        [
            "iteration_guidance_1",
            "iteration_guidance_2",
            "iteration_guidance_3",
            "iteration_guidance_4",
            "iteration_guidance_5",
        ],
    )
    def test_raises_when_guidance_key_missing(self, key: str):
        prompts = {k: v for k, v in CHAT_PROMPTS.items() if k != key}
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            # Drive every branch to ensure the missing key is hit
            cm._build_iteration_guidance(
                2, 5, 0
            )  # may not hit all; individual tests below cover it
            cm._build_iteration_guidance(2, 5, 3)
            cm._build_iteration_guidance(4, 5, 0)
            cm._build_iteration_guidance(4, 5, 3)
            cm._build_iteration_guidance(5, 5, 0)


# ── Tool schemas ──────────────────────────────────────────────────────────────


class TestBuildToolSchemas:
    def test_returns_four_schemas(self):
        cm = make_cm()
        schemas = cm.build_tool_schemas()
        assert len(schemas) == 4

    def test_schema_names_are_correct(self):
        cm = make_cm()
        names = {s["function"]["name"] for s in cm.build_tool_schemas()}
        assert names == {
            "rag_search",
            "get_pages",
            "ask_clarification",
            "to_final_response",
        }

    def test_descriptions_come_from_pm(self):
        cm = make_cm()
        schemas = cm.build_tool_schemas()
        rag = next(s for s in schemas if s["function"]["name"] == "rag_search")
        assert (
            rag["function"]["description"] == CHAT_PROMPTS["tool_call_rag_description"]
        )

    def test_raises_when_tool_description_key_missing(self):
        prompts = {
            k: v for k, v in CHAT_PROMPTS.items() if k != "tool_call_rag_description"
        }
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm.build_tool_schemas()


# ── System prompt ─────────────────────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_contains_all_injected_pieces(self):
        cm = make_cm()
        prompt = cm.build_system_prompt(
            document_registry=[make_doc("Math", "doc-1", 30)],
            user_context=make_ctx(doc_id="doc-1", doc_name="Math", page=5, total=30),
            current_iteration=1,
            max_iterations=5,
            chunks_in_context=0,
        )
        assert "Math" in prompt
        assert "doc-1" in prompt
        assert "1/5" in prompt or ("1" in prompt and "5" in prompt)

    def test_folder_prompt_uses_russian_material_split_guidance(self):
        cm = make_cm({"system_prompt": SYSTEM_PROMPT_TEMPLATE})
        prompt = cm.build_system_prompt(
            document_registry=[make_doc("Русский язык", "doc-1", 30)],
            user_context=make_ctx(
                doc_id="doc-1", doc_name="Русский язык", page=5, total=30
            ),
            current_iteration=1,
            max_iterations=5,
            chunks_in_context=0,
        )

        assert "Отвечай на русском языке" in prompt
        assert "В твоих материалах" in prompt
        assert "В общем по ЕГЭ" in prompt
        assert "From your materials" not in prompt
        assert "In general" not in prompt

    def test_raises_when_system_prompt_key_missing(self):
        prompts = {k: v for k, v in CHAT_PROMPTS.items() if k != "system_prompt"}
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm.build_system_prompt([], make_ctx(), 1, 5)

    def test_general_prompt_contains_novalearn_product_guidance(self):
        cm = make_cm({"system_prompt_general": GENERAL_SYSTEM_PROMPT_TEMPLATE})
        prompt = cm.build_system_prompt(
            document_registry=[],
            user_context=make_ctx(),
            current_iteration=2,
            max_iterations=5,
            chunks_in_context=0,
            is_general=True,
        )

        assert "общий ассистент NovaLearn для подготовки к ЕГЭ" in prompt
        assert "только предметы ЕГЭ" in prompt
        assert "Русский язык" in prompt
        assert "Математика профиль" in prompt
        assert "Информатика" in prompt
        assert "Past Papers" not in prompt
        assert "A-Level" not in prompt
        assert "GCSE" not in prompt
        assert "General Chat cannot see" not in prompt
        assert "Общий чат не видит" in prompt
        assert "You are on iteration 2 of 5." in prompt
        assert CHAT_PROMPTS["iteration_guidance_1"] in prompt
        assert "{current_iteration}" not in prompt
        assert "{max_iterations}" not in prompt
        assert "{iteration_guidance}" not in prompt

    def test_lesson_scope_prompt_uses_russian_anti_spoiler_guidance(self):
        cm = make_cm()
        prompt = cm.build_system_prompt(
            document_registry=[],
            user_context=make_ctx(),
            current_iteration=1,
            max_iterations=5,
            lesson_content=":::question\nЧто такое орфограмма?\n:::",
        )

        assert "Отвечай на русском языке" in prompt
        assert "не давай прямой ответ" in prompt
        assert "помогу тебе разобраться" in prompt
        assert "That's one of the exercises" not in prompt
        assert "I won't give you the answer directly" not in prompt

    def test_practice_scope_block_uses_russian_anti_spoiler_guidance(self):
        block = PRACTICE_SCOPE_BLOCK_TEMPLATE.format(
            question_text="Реши задание по русскому языку."
        )

        assert "Текущий тренировочный вопрос" in block
        assert "Отвечай на русском языке" in block
        assert "не давай ученику прямой ответ" in block
        assert "I won't give you the answer directly" not in block
        assert "Current Practice Question" not in block


# ── LLM messages ─────────────────────────────────────────────────────────────


class TestBuildLlmMessages:
    def _make_history(self) -> list[Message]:
        return [
            Message("m1", "conv-1", MessageRole.USER, "Hello"),
            Message("m2", "conv-1", MessageRole.ASSISTANT, "Hi there"),
        ]

    def test_first_message_is_system(self):
        cm = make_cm()
        messages = cm.build_llm_messages("SYS", [], [], "user query")
        assert messages[0]["role"] == "system"
        assert "SYS" in messages[0]["content"]

    def test_overflow_note_appended_to_system(self):
        cm = make_cm()
        messages = cm.build_llm_messages(
            "SYS", [], [], "user query", retrieval_overflowed=True
        )
        sys_content = messages[0]["content"]
        assert CHAT_PROMPTS["retrieval_overflow_note"] in sys_content

    def test_history_messages_included(self):
        cm = make_cm()
        history = self._make_history()
        messages = cm.build_llm_messages("SYS", history, [], "user query")
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    def test_last_message_is_user_query(self):
        cm = make_cm()
        messages = cm.build_llm_messages("SYS", [], [], "what is entropy?")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "what is entropy?"

    def test_raises_when_overflow_note_key_missing(self):
        prompts = {
            k: v for k, v in CHAT_PROMPTS.items() if k != "retrieval_overflow_note"
        }
        cm = ContextManager(chars_per_token=4, prompt_manager=make_pm(prompts))
        with pytest.raises(PromptNotFoundError):
            cm.build_llm_messages("SYS", [], [], "q", retrieval_overflowed=True)


# ── Estimate tokens ───────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string_is_zero(self):
        assert make_cm().estimate_tokens("") == 0

    def test_chars_per_token_ratio(self):
        cm = make_cm()  # chars_per_token=4
        assert cm.estimate_tokens("abcd") == 1
        assert cm.estimate_tokens("abcdefgh") == 2

    def test_minimum_is_one_for_non_empty(self):
        cm = make_cm()
        assert cm.estimate_tokens("x") == 1


# ── Truncate history ──────────────────────────────────────────────────────────


class TestTruncateHistory:
    def _msg(self, mid: str, content: str, ts: float) -> Message:
        return Message(
            id=mid,
            conversation_id="c",
            role=MessageRole.USER,
            content=content,
            created_at=datetime.fromtimestamp(ts, tz=timezone.utc),
        )

    def test_empty_history_returns_empty(self):
        cm = make_cm()
        assert cm.truncate_history([], 100) == []

    def test_within_budget_returns_all_sorted(self):
        cm = make_cm()
        msgs = [self._msg("b", "BB", 2.0), self._msg("a", "AA", 1.0)]
        result = cm.truncate_history(msgs, token_budget=10)
        assert [m.id for m in result] == ["a", "b"]

    def test_over_budget_keeps_first_and_recent(self):
        cm = make_cm()
        # chars_per_token=4, each 4-char message = 1 token → budget=2 keeps first + one tail
        msgs = [
            self._msg("1", "aaaa", 1.0),  # 1 token
            self._msg("2", "bbbb", 2.0),  # 1 token
            self._msg("3", "cccc", 3.0),  # 1 token
        ]
        result = cm.truncate_history(msgs, token_budget=2)
        ids = [m.id for m in result if m.id != "history-trim-note"]
        assert "1" in ids  # first is always kept
        assert "3" in ids  # most recent tail fits

    def test_over_budget_inserts_trim_note(self):
        cm = make_cm()
        msgs = [
            self._msg("1", "aaaa", 1.0),
            self._msg("2", "bbbbbbbbbbbb", 2.0),  # 3 tokens
            self._msg("3", "cccccccccccc", 3.0),  # 3 tokens
        ]
        result = cm.truncate_history(msgs, token_budget=2)
        assert any(m.id == "history-trim-note" for m in result)


# ── Deduplicate chunks ────────────────────────────────────────────────────────


class TestDeduplicateChunks:
    def _chunk(self, chunk_id: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id, text="t", document_id="d", document_name="n", page=1
        )

    def test_no_duplicates_returned_intact(self):
        chunks = [self._chunk("a"), self._chunk("b")]
        seen: set[str] = set()
        unique, dupes = ContextManager.deduplicate_chunks(chunks, seen)
        assert len(unique) == 2
        assert dupes == 0

    def test_seen_chunks_filtered_out(self):
        chunks = [self._chunk("a"), self._chunk("b")]
        seen: set[str] = {"a"}
        unique, dupes = ContextManager.deduplicate_chunks(chunks, seen)
        assert len(unique) == 1
        assert unique[0].chunk_id == "b"
        assert dupes == 1

    def test_seen_set_is_updated(self):
        chunks = [self._chunk("x")]
        seen: set[str] = set()
        ContextManager.deduplicate_chunks(chunks, seen)
        assert "x" in seen

    def test_all_duplicates(self):
        chunks = [self._chunk("a"), self._chunk("b")]
        seen: set[str] = {"a", "b"}
        unique, dupes = ContextManager.deduplicate_chunks(chunks, seen)
        assert unique == []
        assert dupes == 2
