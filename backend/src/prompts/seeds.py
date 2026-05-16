"""Idempotent startup seeder for chat prompts.

Inserts the default chat prompts into the DB if they don't already exist.
Safe to run on every startup.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.chat.prompts import (
    GENERAL_SYSTEM_PROMPT_TEMPLATE,
    LESSON_SCOPE_SYSTEM_PROMPT_TEMPLATE,
    PRACTICE_SCOPE_BLOCK_TEMPLATE,
    RETRIEVAL_OVERFLOW_NOTE,
    SYSTEM_PROMPT_TEMPLATE,
    RAG_SEARCH_TOOL,
    GET_PAGES_TOOL,
    ASK_CLARIFICATION_TOOL,
    TO_FINAL_RESPONSE_TOOL,
)
from src.learning.mini_feynman.prompts import (
    EVALUATE_SYSTEM,
    EVALUATE_USER_TEMPLATE,
    _TERMINAL_INSTRUCTION,
    _CONTINUE_INSTRUCTION,
)
from src.learning.feynman.prompts import (
    OPENING_SYSTEM,
    OPENING_USER_TEMPLATE,
    EVALUATOR_SYSTEM,
    EVALUATOR_USER_TEMPLATE,
    FEEDBACK_SYSTEM,
    FEEDBACK_USER_TEMPLATE,
    ASK_NOVA_GUIDANCE_NONE,
    ASK_NOVA_GUIDANCE_REPEAT,
    ASK_NOVA_GUIDANCE_SPELL,
    ASK_NOVA_GUIDANCE_MEANING,
    ASK_NOVA_GUIDANCE_DEFAULT,
)
from src.learning.tests.prompts import (
    ALLOCATION_SYSTEM,
    ALLOCATION_USER_TEMPLATE,
    GENERATION_SYSTEM,
    GENERATION_USER_TEMPLATE,
    SINGLE_QUESTION_SYSTEM,
    SINGLE_QUESTION_USER_TEMPLATE,
    GRADING_SYSTEM,
    GRADING_USER_TEMPLATE,
    REVIEW_QUESTION_SYSTEM,
    REVIEW_QUESTION_USER_TEMPLATE,
    PRACTICE_HINT_SYSTEM,
    PRACTICE_HINT_USER_CHAT_MESSAGE,
)
from src.learning.past_paper.parser import (
    _SYSTEM_PROMPT_BASE as _PARSER_SYSTEM,
    _MARK_SCHEME_INSTRUCTION_WITHOUT,
    _MARK_SCHEME_INSTRUCTION_WITH,
    _REPARSE_MARK_SCHEME_SYSTEM,
    _RECOVER_JSON_SYSTEM,
    _ASSIGN_MARK_SCHEME_SYSTEM,
)
from src.learning.past_paper.node_matcher import _SYSTEM_PROMPT as _NODE_MATCHER_SYSTEM
from src.processing.chunking import (
    LINE_CLUSTERING_SYSTEM_PROMPT,
    _CARRY_OVER_INSTRUCTION,
    _NO_CARRY_OVER_INSTRUCTION,
    LINE_CLUSTERING_USER_PROMPT,
)
from src.processing.megaclustering import MEGACLUSTER_VERIFICATION_SYSTEM

from src.prompts import repository

logger = logging.getLogger(__name__)

# [service, key, content, description, variables]
_CHAT_SEEDS: list[tuple[str, str, str, str | None, list[str]]] = [
    (
        "chat",
        "system_prompt",
        SYSTEM_PROMPT_TEMPLATE,
        "Main study assistant system prompt. Placeholders: {document_registry_block}, {current_page_block}, {current_iteration}, {max_iterations}, {iteration_guidance}.",
        [
            "document_registry_block",
            "current_page_block",
            "current_iteration",
            "max_iterations",
            "iteration_guidance",
        ],
    ),
    (
        "chat",
        "system_prompt_general",
        GENERAL_SYSTEM_PROMPT_TEMPLATE,
        "General mode system prompt (no folder/documents). Placeholders: {current_iteration}, {max_iterations}, {iteration_guidance}.",
        ["current_iteration", "max_iterations", "iteration_guidance"],
    ),
    (
        "chat",
        "retrieval_overflow_note",
        RETRIEVAL_OVERFLOW_NOTE,
        "Appended to the system message when earlier retrieval results were condensed to fit context limits.",
        [],
    ),
    (
        "chat",
        "tool_call_rag_description",
        RAG_SEARCH_TOOL["function"]["description"],
        "RAG search function call description.",
        [],
    ),
    (
        "chat",
        "tool_call_rag_query_description",
        RAG_SEARCH_TOOL["function"]["parameters"]["properties"]["query"]["description"],
        "RAG search function call query parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_rag_document_ids_description",
        RAG_SEARCH_TOOL["function"]["parameters"]["properties"]["document_ids"][
            "description"
        ],
        "RAG search function call document_ids parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_get_pages_description",
        GET_PAGES_TOOL["function"]["description"],
        "Get pages function call description.",
        [],
    ),
    (
        "chat",
        "tool_call_get_pages_document_id_description",
        GET_PAGES_TOOL["function"]["parameters"]["properties"]["document_id"][
            "description"
        ],
        "Get pages function call document_id parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_get_pages_start_page_description",
        GET_PAGES_TOOL["function"]["parameters"]["properties"]["start_page"][
            "description"
        ],
        "Get pages function call start_page parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_get_pages_end_page_description",
        GET_PAGES_TOOL["function"]["parameters"]["properties"]["end_page"][
            "description"
        ],
        "Get pages function call end_page parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_ask_clarification_description",
        ASK_CLARIFICATION_TOOL["function"]["description"],
        "Ask clarification function call description.",
        [],
    ),
    (
        "chat",
        "tool_call_ask_clarification_reason_description",
        ASK_CLARIFICATION_TOOL["function"]["parameters"]["properties"]["reason"][
            "description"
        ],
        "Follow-ups function call reason parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_ask_clarification_questions_description",
        ASK_CLARIFICATION_TOOL["function"]["parameters"]["properties"]["questions"][
            "description"
        ],
        "Follow-ups function call questions parameter description.",
        [],
    ),
    (
        "chat",
        "tool_call_to_final_response_description",
        TO_FINAL_RESPONSE_TOOL["function"]["description"],
        "",
        [],
    ),
    (
        "chat",
        "document_registery_block_no_docs",
        "- No documents found in this folder.",
        "Prompt piece when no documents are found in a folder.",
        [],
    ),
    (
        "chat",
        "document_registery_block_doc_line",
        """- "{name}" (uuid: {document_id}, {page_count} pages)""",
        "Prompt piece for one found document in a folder (builds a list of documents).",
        ["name", "document_id", "page_count"],
    ),
    (
        "chat",
        "no_current_document_page",
        "The student is browsing the folder overview. No specific document is open.",
        "Prompt piece when no specific document page is open (used in folder overview).",
        [],
    ),
    (
        "chat",
        "current_document",
        'The student is currently viewing: "{document_name}" '
        "- page {current_page} of {total_pages}.\n"
        "Prioritize this document and nearby pages unless the question clearly refers to other material.",
        "Prompt piece when a specific document page is open (used in document view).",
        ["document_name", "current_page", "total_pages"],
    ),
    (
        "chat",
        "iteration_guidance_1",
        "You have searched but found nothing so far. "
        "Try a different, broader, or rephrased query. "
        "Call to_final_response when ready — you may answer with general knowledge if nothing relevant is found.",
        "Guidance prompt when no chunks are found but iteration budget is enough",
        [],
    ),
    (
        "chat",
        "iteration_guidance_2",
        "You have more iterations available. Search multiple times with different queries if needed. "
        "Call to_final_response when you have enough context to answer.",
        "Guidance prompt when iteration budget is enough and some chunks are found",
        [],
    ),
    (
        "chat",
        "iteration_guidance_3",
        "This is your second-to-last iteration and you have found nothing. "
        "Try one more search, then call to_final_response.",
        "Guidance prompt when no chunks are found and iteration budget is low",
        [],
    ),
    (
        "chat",
        "iteration_guidance_4",
        "This is your second-to-last iteration. If you have sufficient context, "
        "call to_final_response now to proceed directly to your answer.",
        "Guidance prompt when iteration budget is low but some chunks are found",
        [],
    ),
    (
        "chat",
        "iteration_guidance_5",
        "This is your FINAL iteration. You MUST produce your answer now using whatever context you have. DO NOT CALL TOOLS.",
        "Guidance prompt for the final iteration",
        [],
    ),
    (
        "chat",
        "lesson_scope_system_prompt",
        LESSON_SCOPE_SYSTEM_PROMPT_TEMPLATE,
        "System prompt for lesson side chat. Has full lesson markdown + feynman history + anti-cheat guard. Placeholders: {current_block_block}, {lesson_content}, {feynman_history_block}.",
        ["current_block_block", "lesson_content", "feynman_history_block"],
    ),
    (
        "chat",
        "practice_scope_block",
        PRACTICE_SCOPE_BLOCK_TEMPLATE,
        "Block appended to the RAG system prompt when a specific practice question is in scope. Adds anti-cheat guard. Placeholder: {question_text}.",
        ["question_text"],
    ),
    (
        "mini_feynman",
        "feynman_system_prompt",
        EVALUATE_SYSTEM,
        "Mini-Feynman main system prompt",
        [],
    ),
    (
        "mini_feynman",
        "feynman_user_template",
        EVALUATE_USER_TEMPLATE,
        "Mini-Feynman template of user's content",
        ["points_list", "iteration", "history", "user_answer", "terminal_instruction"],
    ),
    (
        "mini_feynman",
        "feynman_terminal_instruction",
        _TERMINAL_INSTRUCTION,
        "Mini-Feynman instruction for final iteration",
        [],
    ),
    (
        "mini_feynman",
        "feynman_continue_instruction",
        _CONTINUE_INSTRUCTION,
        "Mini-Feynman instruction for continuing the iteration",
        [],
    ),
    # Standard Feynman (full session, theme-score tracking)
    (
        "feynman",
        "opening_system",
        OPENING_SYSTEM,
        "Standard Feynman opening system prompt — instructs LLM to generate the session opener",
        [],
    ),
    (
        "feynman",
        "opening_user_template",
        OPENING_USER_TEMPLATE,
        "Standard Feynman opening user template. Placeholders: {themes_list}",
        ["themes_list"],
    ),
    (
        "feynman",
        "evaluator_system",
        EVALUATOR_SYSTEM,
        "Standard Feynman evaluator system prompt — JSON function-call contract for theme scoring",
        [],
    ),
    (
        "feynman",
        "evaluator_user_template",
        EVALUATOR_USER_TEMPLATE,
        "Standard Feynman evaluator user template. Placeholders: {themes_with_scores}, {history}, {selected_quote_block}, {ask_nova_guidance}, {user_answer}",
        [
            "themes_with_scores",
            "history",
            "selected_quote_block",
            "ask_nova_guidance",
            "user_answer",
        ],
    ),
    (
        "feynman",
        "ask_nova_guidance_none",
        ASK_NOVA_GUIDANCE_NONE,
        "Ask Nova evaluator guidance when no highlighted quote is present.",
        [],
    ),
    (
        "feynman",
        "ask_nova_guidance_repeat",
        ASK_NOVA_GUIDANCE_REPEAT,
        "Ask Nova evaluator guidance: repeat quote. Placeholder: {quote}",
        ["quote"],
    ),
    (
        "feynman",
        "ask_nova_guidance_spell",
        ASK_NOVA_GUIDANCE_SPELL,
        "Ask Nova evaluator guidance: spell quote. Placeholder: {quote}",
        ["quote"],
    ),
    (
        "feynman",
        "ask_nova_guidance_meaning",
        ASK_NOVA_GUIDANCE_MEANING,
        "Ask Nova evaluator guidance: explain quote meaning. Placeholder: {quote}",
        ["quote"],
    ),
    (
        "feynman",
        "ask_nova_guidance_default",
        ASK_NOVA_GUIDANCE_DEFAULT,
        "Ask Nova evaluator guidance: generic highlighted-quote handling.",
        [],
    ),
    (
        "feynman",
        "feedback_system",
        FEEDBACK_SYSTEM,
        "Standard Feynman feedback system prompt — used on abort to generate narrative feedback",
        [],
    ),
    (
        "feynman",
        "feedback_user_template",
        FEEDBACK_USER_TEMPLATE,
        "Standard Feynman feedback user template. Placeholders: {outcome}, {themes_with_scores}",
        ["outcome", "themes_with_scores"],
    ),
]

_TESTS_SEEDS: list[tuple[str, str, str, str | None, list[str]]] = [
    (
        "tests",
        "allocation_system",
        ALLOCATION_SYSTEM,
        "Question allocation system prompt — distributes questions across topics by mastery.",
        [],
    ),
    (
        "tests",
        "allocation_user_template",
        ALLOCATION_USER_TEMPLATE,
        "Question allocation user template. Placeholders: {total_questions}, {num_topics}, {topics_list}.",
        ["total_questions", "num_topics", "topics_list"],
    ),
    (
        "tests",
        "generation_system",
        GENERATION_SYSTEM,
        "Mixed MCQ + short-answer question generation system prompt.",
        [],
    ),
    (
        "tests",
        "generation_user_template",
        GENERATION_USER_TEMPLATE,
        "Question generation user template. Placeholders: {count}, {topic_name}, {lesson_content}.",
        ["count", "topic_name", "lesson_content"],
    ),
    (
        "tests",
        "single_question_system",
        SINGLE_QUESTION_SYSTEM,
        "Single question generation system prompt (streaming, one at a time).",
        [],
    ),
    (
        "tests",
        "single_question_user_template",
        SINGLE_QUESTION_USER_TEMPLATE,
        "Single question user template. Placeholders: {current}, {total}, {topic_name}, {lesson_content}, {previous_block}.",
        ["current", "total", "topic_name", "lesson_content", "previous_block"],
    ),
    (
        "tests",
        "grading_system",
        GRADING_SYSTEM,
        "Short-answer grading system prompt — awards marks against a mark scheme.",
        [],
    ),
    (
        "tests",
        "grading_user_template",
        GRADING_USER_TEMPLATE,
        "Grading user template. Placeholders: {question}, {points}, {mark_scheme}, {model_answer}, {student_answer}.",
        ["question", "points", "mark_scheme", "model_answer", "student_answer"],
    ),
    (
        "tests",
        "review_question_system",
        REVIEW_QUESTION_SYSTEM,
        "Review question generation system prompt — generates a question targeting a student's past mistake.",
        [],
    ),
    (
        "tests",
        "review_question_user_template",
        REVIEW_QUESTION_USER_TEMPLATE,
        "Review question user template. Placeholders: {topic}, {mistake}, {correction}.",
        ["topic", "mistake", "correction"],
    ),
    (
        "tests",
        "practice_hint_system",
        PRACTICE_HINT_SYSTEM,
        "Practice hint system prompt — guides student with a hint without revealing the answer.",
        [],
    ),
    (
        "tests",
        "practice_hint_user_chat_message",
        PRACTICE_HINT_USER_CHAT_MESSAGE,
        "Static user chat message that triggers the practice hint flow.",
        [],
    ),
]

_PAST_PAPER_SEEDS: list[tuple[str, str, str, str | None, list[str]]] = [
    (
        "past_paper",
        "parser_system",
        _PARSER_SYSTEM,
        "Past paper extraction base system prompt — extracts all questions from markdown.",
        [],
    ),
    (
        "past_paper",
        "mark_scheme_instruction_without",
        _MARK_SCHEME_INSTRUCTION_WITHOUT,
        "Appended to parser_system when no mark scheme is available — sets mark_scheme to null.",
        [],
    ),
    (
        "past_paper",
        "mark_scheme_instruction_with",
        _MARK_SCHEME_INSTRUCTION_WITH,
        "Appended to parser_system when a mark scheme document is provided.",
        [],
    ),
    (
        "past_paper",
        "reparse_mark_scheme_system",
        _REPARSE_MARK_SCHEME_SYSTEM,
        "Reparse system prompt — matches stored questions to a separately uploaded mark scheme.",
        [],
    ),
    (
        "past_paper",
        "recover_json_system",
        _RECOVER_JSON_SYSTEM,
        "JSON recovery system prompt — fixes malformed LLM JSON output.",
        [],
    ),
    (
        "past_paper",
        "assign_mark_scheme_system",
        _ASSIGN_MARK_SCHEME_SYSTEM,
        "Mark scheme assignment system prompt — maps mark scheme entries to existing questions by content.",
        [],
    ),
    (
        "past_paper",
        "node_matcher_system",
        _NODE_MATCHER_SYSTEM,
        "Curriculum mapping system prompt — maps past paper questions to level-3 roadmap nodes.",
        [],
    ),
]

_PROCESSING_SEEDS: list[tuple[str, str, str, str | None, list[str]]] = [
    (
        "processing",
        "line_clustering_system",
        LINE_CLUSTERING_SYSTEM_PROMPT,
        "Document chunking system prompt template. Placeholders: {carry_over_instruction}, {first_line}, {last_line}.",
        ["carry_over_instruction", "first_line", "last_line"],
    ),
    (
        "processing",
        "line_clustering_carry_over_instruction",
        _CARRY_OVER_INSTRUCTION,
        "Carry-over instruction block — injected into line_clustering_system when previous context exists. Placeholders: {carry_over_end}, {first_line}.",
        ["carry_over_end", "first_line"],
    ),
    (
        "processing",
        "line_clustering_no_carry_over_instruction",
        _NO_CARRY_OVER_INSTRUCTION,
        "No carry-over instruction block — injected into line_clustering_system for first chunk. Placeholder: {first_line}.",
        ["first_line"],
    ),
    (
        "processing",
        "line_clustering_user",
        LINE_CLUSTERING_USER_PROMPT,
        "Document chunking user prompt template. Placeholder: {text}.",
        ["text"],
    ),
    (
        "processing",
        "megacluster_verification_system",
        MEGACLUSTER_VERIFICATION_SYSTEM,
        "Megacluster grouping system prompt — groups semantically similar clusters from different documents.",
        [],
    ),
]


# Prompts in these services are always kept in sync with code (upserted, not skipped).
_ALWAYS_SYNC_SERVICES = {"feynman", "chat", "past_paper"}

_ALL_SEEDS = _CHAT_SEEDS + _TESTS_SEEDS + _PAST_PAPER_SEEDS + _PROCESSING_SEEDS


async def seed_chat_prompts(session_factory: async_sessionmaker[AsyncSession]) -> None:
    inserted = updated = 0
    async with session_factory() as session:
        for service, key, content, description, variables in _ALL_SEEDS:
            existing = await repository.get_by_service_key(session, service, key)
            if existing:
                if service in _ALWAYS_SYNC_SERVICES and existing.content != content:
                    await repository.update_prompt(
                        session, existing, content=content, description=description
                    )
                    updated += 1
                continue
            await repository.create_prompt(
                session,
                service=service,
                key=key,
                content=content,
                description=description,
                variables=variables,
            )
            inserted += 1
        if inserted or updated:
            await session.commit()

    if inserted or updated:
        logger.info("Seeded %d / updated %d chat prompt(s)", inserted, updated)
    else:
        logger.debug("Chat prompts already seeded, skipping")
