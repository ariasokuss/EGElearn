"""Shared test helpers and fixtures."""

from __future__ import annotations

from src.prompts.manager import PromptManager

# ── All prompt keys used by ContextManager ─────────────────────────────────

CHAT_PROMPTS: dict[str, str] = {
    "system_prompt": (
        "System: {current_page_block}\n"
        "Docs: {document_registry_block}\n"
        "Iteration {current_iteration}/{max_iterations}\n"
        "{iteration_guidance}"
    ),
    "retrieval_overflow_note": "Some earlier results were condensed.",
    "document_registery_block_no_docs": "- No documents found in this folder.",
    "document_registery_block_doc_line": '- "{name}" (uuid: {document_id}, {page_count} pages)',
    "no_current_document_page": "The student is browsing the folder overview.",
    "current_document": (
        'The student is viewing: "{document_name}" '
        "- page {current_page} of {total_pages}."
    ),
    "iteration_guidance_1": "Nothing found yet. Try a broader query.",
    "iteration_guidance_2": "More iterations available. Keep searching.",
    "iteration_guidance_3": "Second-to-last iteration, nothing found. Try once more.",
    "iteration_guidance_4": "Second-to-last iteration. Call to_final_response if ready.",
    "iteration_guidance_5": "FINAL iteration. Answer now.",
    "tool_call_rag_description": "Search document chunks.",
    "tool_call_rag_query_description": "Natural language search query.",
    "tool_call_rag_document_ids_description": "Filter by document UUIDs.",
    "tool_call_get_pages_description": "Retrieve full page text.",
    "tool_call_get_pages_document_id_description": "Document UUID.",
    "tool_call_get_pages_start_page_description": "First page to fetch.",
    "tool_call_get_pages_end_page_description": "Last page to fetch.",
    "tool_call_ask_clarification_description": "Ask the student a clarifying question.",
    "tool_call_ask_clarification_reason_description": "Why clarification is needed.",
    "tool_call_ask_clarification_questions_description": "Questions to ask.",
    "tool_call_to_final_response_description": "Signal that the final answer is ready.",
}


def make_pm(prompts: dict[str, str] | None = None) -> PromptManager:
    """Build a PromptManager with a pre-loaded in-memory cache — no DB needed."""
    pm: PromptManager = object.__new__(PromptManager)
    pm._cache = {"chat": dict(CHAT_PROMPTS if prompts is None else prompts)}
    return pm
