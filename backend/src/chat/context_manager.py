"""Context manager for chat agent — prompts, history truncation, retrieval overflow."""

from __future__ import annotations

import copy
import json
from typing import Any

from src.chat.attachments import format_text_blocks_for_message, metadata_to_text_blocks
from src.chat.entities import (
    DocumentInfo,
    Message,
    MessageRole,
    RetrievedChunk,
    UserContext,
)
from src.chat.prompts import (
    ASK_CLARIFICATION_TOOL,
    GET_PAGES_TOOL,
    LESSON_SCOPE_SYSTEM_PROMPT_TEMPLATE,
    PRACTICE_SCOPE_BLOCK_TEMPLATE,
    RAG_SEARCH_TOOL,
    TO_FINAL_RESPONSE_TOOL,
)
from src.chat.schemas import InlineQuizAnswerContext
from src.config import get_settings
from src.prompts.manager import PromptManager


class ContextManager:
    def __init__(
        self,
        chars_per_token: int | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._chars_per_token = (
            chars_per_token
            if chars_per_token is not None
            else get_settings().chat.chars_per_token
        )
        if prompt_manager is None:
            raise ValueError("ContextManager requires a PromptManager")
        self._pm = prompt_manager

    def build_system_prompt(
        self,
        document_registry: list[DocumentInfo],
        user_context: UserContext,
        current_iteration: int,
        max_iterations: int,
        chunks_in_context: int = 0,
        is_general: bool = False,
        lesson_content: str | None = None,
        feynman_history_text: str | None = None,
        practice_question_text: str | None = None,
        answer_context_text: str | None = None,
        current_block_info: str | None = None,
        inline_quiz_answers: list[InlineQuizAnswerContext] | None = None,
    ) -> str:
        # Lesson scope: full lesson content + feynman history, no RAG.
        if lesson_content is not None:
            feynman_block = feynman_history_text or ""
            if current_block_info:
                current_block_block = f"## Что сейчас открыто\n\nУченик сейчас смотрит **{current_block_info}**.\n\n"
            else:
                current_block_block = ""
            prompt = LESSON_SCOPE_SYSTEM_PROMPT_TEMPLATE.format(
                lesson_content=lesson_content,
                feynman_history_block=feynman_block,
                current_block_block=current_block_block,
            )
            quiz_block = self._format_inline_quiz_answers(inline_quiz_answers)
            if quiz_block:
                prompt += "\n\n" + quiz_block
            return prompt

        iteration_guidance = self._build_iteration_guidance(
            current_iteration, max_iterations, chunks_in_context
        )
        if is_general:
            template = self._pm.get("chat", "system_prompt_general")
            return template.format(
                current_iteration=current_iteration,
                max_iterations=max_iterations,
                iteration_guidance=iteration_guidance,
            )
        template = self._pm.get("chat", "system_prompt")
        base_prompt = template.format(
            current_page_block=self._build_current_page_block(user_context),
            document_registry_block=self._build_document_registry_block(
                document_registry
            ),
            current_iteration=current_iteration,
            max_iterations=max_iterations,
            iteration_guidance=iteration_guidance,
        )
        # Practice scope: append the question + anti-cheat block to the RAG prompt.
        if practice_question_text:
            practice_block = PRACTICE_SCOPE_BLOCK_TEMPLATE.format(
                question_text=practice_question_text,
            )
            base_prompt = base_prompt + practice_block
        # Answer context: append student's answer, grading, and feedback note info.
        if answer_context_text:
            base_prompt = base_prompt + "\n\n" + answer_context_text
        return base_prompt

    # ── Private prompt-piece builders (all keys required — PromptNotFoundError = missing seed) ──

    def _build_document_registry_block(
        self, document_registry: list[DocumentInfo]
    ) -> str:
        if not document_registry:
            return self._pm.get("chat", "document_registery_block_no_docs")
        doc_line_tpl = self._pm.get("chat", "document_registery_block_doc_line")
        lines = [
            doc_line_tpl.format(
                name=doc.name,
                document_id=doc.document_id,
                page_count=doc.page_count,
            )
            for doc in document_registry
        ]
        return "\n".join(lines)

    def _build_current_page_block(self, user_context: UserContext) -> str:
        if not user_context.current_document_id:
            return self._pm.get("chat", "no_current_document_page")
        return self._pm.get("chat", "current_document").format(
            document_name=user_context.current_document_name
            or user_context.current_document_id,
            current_page=user_context.current_page,
            total_pages=user_context.total_pages,
        )

    def _build_iteration_guidance(
        self, current_iteration: int, max_iterations: int, chunks_in_context: int = 0
    ) -> str:
        if current_iteration <= max_iterations - 2:
            key = (
                "iteration_guidance_1"
                if chunks_in_context == 0 and current_iteration > 1
                else "iteration_guidance_2"
            )
        elif current_iteration == max_iterations - 1:
            key = (
                "iteration_guidance_3"
                if chunks_in_context == 0
                else "iteration_guidance_4"
            )
        else:
            key = "iteration_guidance_5"
        return self._pm.get("chat", key)

    @staticmethod
    def _format_inline_quiz_answers(
        answers: list[InlineQuizAnswerContext] | None,
    ) -> str:
        """Format inline quiz answers into a system prompt section."""
        if not answers:
            return ""

        lines = [
            "=== STUDENT'S INLINE QUIZ ANSWERS ===",
            "The student has answered the following questions embedded in this lesson.",
            "Use this context when they ask about their performance, scores, or specific answers.",
            "",
        ]

        sorted_answers = sorted(answers, key=lambda a: (a.block_id, a.question_index))
        for a in sorted_answers:
            q_type = "MCQ" if a.question_type == "mcq" else "Short answer"
            header = f"Block {a.block_id}, Q{a.question_index + 1} ({q_type}, {a.total_marks} mark{'s' if a.total_marks != 1 else ''}):"

            if a.grading:
                lines.append(f"{header}")
                lines.append(f"  Answer: \"{a.answer}\"")
                lines.append("  [Currently being graded]")
            elif a.earned_marks is not None:
                correct_label = ""
                if a.is_correct is True:
                    correct_label = " — Correct"
                elif a.is_correct is False:
                    correct_label = " — Incorrect"
                lines.append(f"{header}")
                lines.append(f"  Answer: \"{a.answer[:200]}\"{'…' if len(a.answer) > 200 else ''}{correct_label} ({a.earned_marks}/{a.total_marks} marks)")
                if a.feedback:
                    lines.append(f"  Feedback: {a.feedback}")
                if a.recommendations:
                    lines.append(f"  Recommendations: {a.recommendations}")
            else:
                lines.append(f"{header}")
                lines.append(f"  Answer: \"{a.answer[:200]}\"{'…' if len(a.answer) > 200 else ''}")
                lines.append("  [Pending grading]")
            lines.append("")

        lines.append("===")
        return "\n".join(lines)

    def build_tool_schemas(self) -> list[dict[str, Any]]:
        """Build tool schemas with descriptions loaded from PromptManager.

        Raises PromptNotFoundError if any required prompt key is missing from the DB.
        """
        rag = copy.deepcopy(RAG_SEARCH_TOOL)
        rag["function"]["description"] = self._pm.get(
            "chat", "tool_call_rag_description"
        )
        rag["function"]["parameters"]["properties"]["query"]["description"] = (
            self._pm.get("chat", "tool_call_rag_query_description")
        )
        rag["function"]["parameters"]["properties"]["document_ids"]["description"] = (
            self._pm.get("chat", "tool_call_rag_document_ids_description")
        )

        pages = copy.deepcopy(GET_PAGES_TOOL)
        pages["function"]["description"] = self._pm.get(
            "chat", "tool_call_get_pages_description"
        )
        pages["function"]["parameters"]["properties"]["document_id"]["description"] = (
            self._pm.get("chat", "tool_call_get_pages_document_id_description")
        )
        pages["function"]["parameters"]["properties"]["start_page"]["description"] = (
            self._pm.get("chat", "tool_call_get_pages_start_page_description")
        )
        pages["function"]["parameters"]["properties"]["end_page"]["description"] = (
            self._pm.get("chat", "tool_call_get_pages_end_page_description")
        )

        clarify = copy.deepcopy(ASK_CLARIFICATION_TOOL)
        clarify["function"]["description"] = self._pm.get(
            "chat", "tool_call_ask_clarification_description"
        )
        clarify["function"]["parameters"]["properties"]["reason"]["description"] = (
            self._pm.get("chat", "tool_call_ask_clarification_reason_description")
        )
        clarify["function"]["parameters"]["properties"]["questions"]["description"] = (
            self._pm.get("chat", "tool_call_ask_clarification_questions_description")
        )

        final = copy.deepcopy(TO_FINAL_RESPONSE_TOOL)
        final["function"]["description"] = self._pm.get(
            "chat", "tool_call_to_final_response_description"
        )

        return [rag, pages, clarify, final]

    def build_llm_messages(
        self,
        system_prompt: str,
        history: list[Message],
        loop_tool_pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]],
        user_message: str,
        retrieval_overflowed: bool = False,
        force_answer_note: str = "",
        user_message_images: list[str] | None = None,
        user_citations: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        overflow_note = self._pm.get("chat", "retrieval_overflow_note")
        system_parts = [system_prompt]
        if retrieval_overflowed:
            system_parts.append(overflow_note)
        if force_answer_note:
            system_parts.append(force_answer_note)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(system_parts)}
        ]

        for msg in history:
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
                # Re-attach stored images for user history messages.
                stored_images: list[str] = (msg.metadata or {}).get("images", [])
                # Re-attach stored attachment text for user history messages.
                msg_text = msg.content
                if msg.role == MessageRole.USER:
                    attachment_texts_raw = (msg.metadata or {}).get(
                        "attachment_texts", []
                    )
                    if attachment_texts_raw:
                        text_blocks = metadata_to_text_blocks(attachment_texts_raw)
                        msg_text = msg_text + format_text_blocks_for_message(
                            text_blocks
                        )
                if msg.role == MessageRole.USER and stored_images:
                    content: Any = [{"type": "text", "text": msg_text}]
                    for img_url in stored_images:
                        content.append(
                            {"type": "image_url", "image_url": {"url": img_url}}
                        )
                    messages.append({"role": "user", "content": content})
                else:
                    messages.append({"role": msg.role.value, "content": msg_text})

        for tool_call_message, tool_result_messages in loop_tool_pairs:
            messages.append(tool_call_message)
            for result_message in tool_result_messages:
                messages.append(result_message)

        # Append user-provided citations as labelled references.
        if user_citations:
            citations_block = "\n\n[User-provided references:]\n" + "\n".join(
                f"{i + 1}. {ref}" for i, ref in enumerate(user_citations)
            )
            user_message = user_message + citations_block

        # Build the current user turn — multimodal if images are attached.
        if user_message_images:
            current_content: Any = [{"type": "text", "text": user_message}]
            for img_url in user_message_images:
                current_content.append(
                    {"type": "image_url", "image_url": {"url": img_url}}
                )
            messages.append({"role": "user", "content": current_content})
        else:
            messages.append({"role": "user", "content": user_message})

        return messages

    def truncate_history(
        self, messages: list[Message], token_budget: int
    ) -> list[Message]:
        if not messages:
            return []

        def _sort_key(msg: Message) -> float:
            if msg.created_at is None:
                return 0.0
            try:
                return msg.created_at.timestamp()
            except Exception:
                return 0.0

        messages_sorted = sorted(messages, key=_sort_key)
        total_tokens = sum(self.estimate_tokens(m.content) for m in messages_sorted)
        if total_tokens <= token_budget:
            return messages_sorted

        first_message = messages_sorted[0]
        first_tokens = self.estimate_tokens(first_message.content)
        remaining_budget = max(0, token_budget - first_tokens)

        tail_selected: list[Message] = []
        for msg in reversed(messages_sorted[1:]):
            msg_tokens = self.estimate_tokens(msg.content)
            if msg_tokens <= remaining_budget:
                tail_selected.append(msg)
                remaining_budget -= msg_tokens

        trimmed = [first_message, *reversed(tail_selected)]
        trim_note = Message(
            id="history-trim-note",
            conversation_id=first_message.conversation_id,
            role=MessageRole.ASSISTANT,
            content="[Earlier conversation history was trimmed. The most recent messages are shown.]",
            metadata={},
        )
        return [trim_note, *trimmed]

    def handle_retrieval_overflow(
        self,
        loop_tool_pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]],
        budget: int,
    ) -> tuple[list[tuple[dict[str, Any], list[dict[str, Any]]]], bool]:
        if not loop_tool_pairs:
            return [], False

        total_tokens = 0
        for _, tool_results in loop_tool_pairs:
            for tool_result in tool_results:
                total_tokens += self.estimate_tokens(tool_result.get("content", ""))

        if total_tokens <= budget:
            return loop_tool_pairs, False

        condensed_pairs = copy.deepcopy(loop_tool_pairs)
        older_pairs = condensed_pairs[:-1]

        for idx, (_, tool_result_msgs) in enumerate(older_pairs):
            new_result_msgs = []
            for tool_result_msg in tool_result_msgs:
                payload = self._parse_json(tool_result_msg.get("content", "{}"))
                tool_name = payload.get("tool") or tool_result_msg.get("name")

                if tool_name == "rag_search":
                    results = payload.get("results", [])
                    sorted_results = sorted(
                        results,
                        key=lambda item: float(item.get("similarity_score") or 0.0),
                        reverse=True,
                    )
                    if len(sorted_results) > 5:
                        payload["results"] = sorted_results[:5]
                        payload["result_count"] = len(payload["results"])
                        payload["note"] = self._append_note(
                            payload.get("note"),
                            "Older rag_search results condensed to top 5 chunks by similarity.",
                        )

                if tool_name == "get_pages":
                    chunks = payload.get("chunks", [])
                    requested = payload.get("requested_range") or []
                    start_page = requested[0] if len(requested) > 0 else None
                    end_page = requested[1] if len(requested) > 1 else None

                    if start_page is None or end_page is None:
                        pages = [
                            int(c.get("page"))
                            for c in chunks
                            if c.get("page") is not None
                        ]
                        if pages:
                            start_page = min(pages)
                            end_page = max(pages)

                    if start_page is not None and end_page is not None and chunks:
                        kept = [
                            chunk
                            for chunk in chunks
                            if int(chunk.get("page", -1))
                            in {int(start_page), int(end_page)}
                        ]
                        if not kept:
                            kept = chunks[: min(5, len(chunks))]

                        if len(kept) < len(chunks):
                            payload["chunks"] = kept
                            payload["chunk_count"] = len(kept)
                            payload["note"] = self._append_note(
                                payload.get("note"),
                                "Older get_pages results condensed to first/last pages.",
                            )

                new_result_msgs.append(
                    {
                        **tool_result_msg,
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                )

            condensed_pairs[idx] = (condensed_pairs[idx][0], new_result_msgs)

        return condensed_pairs, True

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // self._chars_per_token)

    @staticmethod
    def deduplicate_chunks(
        new_chunks: list[RetrievedChunk],
        seen_chunk_ids: set[str],
    ) -> tuple[list[RetrievedChunk], int]:
        unique: list[RetrievedChunk] = []
        duplicates = 0

        for chunk in new_chunks:
            if chunk.chunk_id in seen_chunk_ids:
                duplicates += 1
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            unique.append(chunk)

        return unique, duplicates

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, json.JSONDecodeError):
            pass
        return {}

    @staticmethod
    def _append_note(existing: str | None, extra: str) -> str:
        if not existing:
            return extra
        return f"{existing} {extra}".strip()
