"""Document chat agent — RAG, tools, streaming."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from src.chat.attachments import (
    ProcessedAttachments,
    format_text_blocks_for_message,
    process_attachments,
    text_blocks_to_metadata,
)
from src.chat.citation_extractor import CitationExtractor
from src.chat.context_manager import ContextManager
from src.chat.entities import (
    AgentLoopState,
    Citation,
    DocumentInfo,
    Message,
    MessageRole,
    RetrievedChunk,
    ToolCallResult,
    ToolName,
    UserContext,
)
from src.chat.interfaces import (
    ChatRepository,
    EmbeddingService,
    LLMGateway,
    RetrievalService,
)
from src.config import get_settings
from src.core.llm_usage import UsageInfo, estimate_usage
from src.core.s3 import S3Client
from src.processing.markdown import MistralOCR
from src.prompts.manager import PromptNotFoundError

_settings = get_settings()
logger = logging.getLogger(__name__)

_DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)
_MIME_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}


class DocumentChatAgent:
    def __init__(
        self,
        chat_repo: ChatRepository,
        retrieval: RetrievalService,
        embedding: EmbeddingService,
        llm: LLMGateway,
        context_manager: ContextManager,
        citation_extractor: CitationExtractor,
        s3: S3Client,
        max_iterations: int | None = None,
        usage_service: Any | None = None,
        mistral_ocr: MistralOCR | None = None,
    ) -> None:
        self.chat_repo = chat_repo
        self.retrieval = retrieval
        self.embedding = embedding
        self.llm = llm
        self.context_manager = context_manager
        self.citation_extractor = citation_extractor
        self.s3 = s3
        self.mistral_ocr = mistral_ocr
        self.max_iterations = (
            max_iterations
            if max_iterations is not None
            else _settings.chat.max_agent_iterations
        )
        self._tool_call_semaphore = asyncio.Semaphore(
            _settings.chat.max_concurrent_tool_calls
        )
        self._usage_service = usage_service

    def _resolve_usage_model(self, model: str | None) -> str:
        resolver = getattr(self.llm, "_resolve_model", None)
        if callable(resolver):
            try:
                return str(resolver(model))
            except Exception:
                logger.exception("failed to resolve model for usage estimate")
        if model:
            return model
        return str(getattr(self.llm, "_model", None) or get_settings().llm.resolve_model_uri())

    def _stream_usage_or_estimate(
        self,
        usage: UsageInfo | None,
        *,
        messages: list[dict[str, Any]],
        output_text: str,
        model: str | None,
        source: str,
    ) -> UsageInfo:
        if usage is not None:
            return usage
        resolved_model = self._resolve_usage_model(model)
        logger.warning(
            "LLM stream usage missing, estimating chat usage (source=%s model=%s)",
            source,
            resolved_model,
        )
        return estimate_usage(
            messages=messages,
            output_text=output_text,
            model=resolved_model,
        )

    async def handle_message(
        self,
        user_id: str,
        conversation_id: str | None,
        folder_id: str | None,
        message: str,
        current_document_id: str | None,
        current_page: int | None,
        total_pages: int | None,
        model: str | None = None,
        reasoning: str | None = None,
        images: list[str] | None = None,
        user_citations: list[str] | None = None,
        test_session_id: str | None = None,
        question_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
        attachments: list | None = None,
        lesson_id: str | None = None,
        # Scope context — pre-fetched by the router.
        lesson_content: str | None = None,
        feynman_history_text: str | None = None,
        practice_question_text: str | None = None,
        answer_context_text: str | None = None,
        current_block_info: str | None = None,
        inline_quiz_answers: list | None = None,
        parent_id: str | None = None,
        skip_user_save: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        t_request_start = time.monotonic()
        logger.info(
            "handle_message start user=%s conv=%s folder=%s model=%s reasoning=%s has_current_doc=%s attachments=%d",
            user_id[:8],
            conversation_id or "new",
            folder_id[:8] if folder_id else "-",
            model or "default",
            reasoning or "default",
            bool(current_document_id),
            len(attachments or []),
        )

        if not message or not message.strip():
            logger.warning(
                "empty message rejected user=%s conv=%s",
                user_id[:8],
                conversation_id or "new",
            )
            yield self._error_event("Message cannot be empty.", recoverable=True)
            return
        if len(message) > _settings.chat.message_max_length:
            logger.warning(
                "message too long user=%s length=%s limit=%s",
                user_id[:8],
                len(message),
                _settings.chat.message_max_length,
            )
            yield self._error_event(
                f"Message exceeds {_settings.chat.message_max_length} characters.",
                recoverable=True,
            )
            return

        is_new_conversation = conversation_id is None
        existing_conversation_title: str | None = None
        is_general = folder_id is None

        # Process file attachments (PDF OCR, HEIC conversion, text extraction).
        # Keep original message for DB storage; build llm_message with attachment text.
        original_message = message
        processed_attachments: ProcessedAttachments | None = None
        if attachments:
            yield {
                "event": "status",
                "data": {"step": "processing_attachments", "count": len(attachments)},
            }
            try:
                # Need a temp conversation_id for S3 keys if new conversation.
                att_conv_id = conversation_id or str(uuid.uuid4())
                processed_attachments = await process_attachments(
                    attachments=attachments,
                    conversation_id=att_conv_id,
                    s3=self.s3,
                    mistral_ocr=self.mistral_ocr,
                )
                # Merge attachment images into the images list.
                images = list(images or []) + processed_attachments.image_data_uris
                # Append extracted text to LLM message only (not stored in DB).
                text_suffix = format_text_blocks_for_message(
                    processed_attachments.text_blocks
                )
                if text_suffix:
                    message = original_message + text_suffix
                logger.info(
                    "attachments processed user=%s images=%d text_blocks=%d s3_keys=%d",
                    user_id[:8],
                    len(processed_attachments.image_data_uris),
                    len(processed_attachments.text_blocks),
                    len(processed_attachments.s3_keys),
                )
            except ValueError as e:
                yield self._error_event(str(e), recoverable=True)
                return
            except Exception:
                logger.exception("Attachment processing failed user=%s", user_id[:8])
                yield self._error_event(
                    "Failed to process attachments.", recoverable=True
                )
                return

        # All scoped chats skip the RAG loop: lesson, practice, review,
        # and feedback_review.  Their context is pre-fetched by the router
        # (lesson content, question text, answer context, feedback notes)
        # so the agent tool-calling iteration is wasteful — the model never
        # calls tools and we burn an extra LLM round-trip.
        # Only document-scoped chat (folder_id set, no special scope) uses RAG.
        is_lesson_scope = lesson_id is not None
        is_scoped_chat = scope_type in ("practice", "review", "feedback_review")
        if is_general or is_lesson_scope or is_scoped_chat:
            async for event in self._handle_direct_chat(
                user_id=user_id,
                conversation_id=conversation_id,
                folder_id=folder_id,
                message=message,  # LLM message (with attachment text)
                original_message=original_message,  # clean message for DB
                model=model,
                reasoning=reasoning,
                images=images or [],
                user_citations=user_citations or [],
                is_new_conversation=is_new_conversation,
                test_session_id=test_session_id,
                question_id=question_id,
                scope_type=scope_type,
                feedback_note_id=feedback_note_id,
                lesson_id=lesson_id,
                lesson_content=lesson_content,
                feynman_history_text=feynman_history_text,
                practice_question_text=practice_question_text,
                answer_context_text=answer_context_text,
                current_block_info=current_block_info,
                inline_quiz_answers=inline_quiz_answers,
                t_request_start=t_request_start,
                processed_attachments=processed_attachments,
                parent_id=parent_id,
                skip_user_save=skip_user_save,
            ):
                yield event
            return

        _rag_persisted = False
        _rag_final_answer = ""
        _rag_loop_tool_pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        user_context = UserContext(folder_id=folder_id)
        title_task: asyncio.Task[str | None] | None = None

        try:
            if is_new_conversation:
                logger.info(
                    "creating new conversation user=%s folder=%s",
                    user_id[:8],
                    folder_id[:8] if folder_id else "-",
                )
                conversation_id = await self.chat_repo.create_conversation(
                    user_id=user_id,
                    folder_id=folder_id,
                    title=None,
                    test_session_id=test_session_id,
                    question_id=question_id,
                    lesson_id=lesson_id,
                    scope_type=scope_type,
                    feedback_note_id=feedback_note_id,
                )
                logger.info(
                    "new conversation created user=%s conv=%s",
                    user_id[:8],
                    conversation_id,
                )
                # Run title generation in parallel with the RAG loop.
                title_task = asyncio.create_task(
                    self._finalize_title(
                        conversation_id=conversation_id,
                        user_message=original_message,
                        user_id=user_id,
                    )
                )
                yield {
                    "event": "metadata",
                    "data": {"conversation_id": conversation_id},
                }
            else:
                logger.info(
                    "loading existing conversation user=%s conv=%s",
                    user_id[:8],
                    conversation_id,
                )
                conversation = await self.chat_repo.get_conversation(conversation_id)
                if (
                    not conversation
                    or conversation.user_id != user_id
                    or conversation.folder_id != folder_id
                    or conversation.test_session_id != test_session_id
                    or conversation.question_id != question_id
                    or conversation.lesson_id != lesson_id
                    or conversation.scope_type != scope_type
                    or str(conversation.feedback_note_id or "") != (feedback_note_id or "")
                ):
                    logger.error(
                        "conversation not found or mismatched user/folder user=%s conv=%s folder=%s",
                        user_id[:8],
                        conversation_id,
                        folder_id[:8] if folder_id else "-",
                    )
                    yield self._error_event(
                        "Conversation not found.", recoverable=False
                    )
                    return
                existing_conversation_title = conversation.title

            docs_task = self.chat_repo.get_folder_documents(
                user_id=user_id, folder_id=folder_id
            )
            history_task = self.chat_repo.get_active_path_history(
                conversation_id=conversation_id,
                roles=[MessageRole.USER, MessageRole.ASSISTANT],
            )
            document_registry, history = await asyncio.gather(docs_task, history_task)
            logger.info(
                "loaded context conv=%s docs=%d history_messages=%d",
                conversation_id,
                len(document_registry),
                len(history),
            )

            document_map = {doc.document_id: doc for doc in document_registry}

            resolved_document_name = None
            resolved_total_pages = total_pages

            if current_document_id:
                doc = document_map.get(current_document_id)
                if doc:
                    resolved_document_name = doc.name
                    resolved_total_pages = doc.page_count
                    logger.info(
                        "current_document resolved id=%s name=%s page=%s/%s",
                        current_document_id,
                        resolved_document_name,
                        current_page,
                        resolved_total_pages,
                    )
                else:
                    logger.warning(
                        "current_document_id not found in registry id=%s",
                        current_document_id,
                    )

            user_context = UserContext(
                folder_id=folder_id,
                current_document_id=current_document_id,
                current_document_name=resolved_document_name,
                current_page=current_page,
                total_pages=resolved_total_pages,
            )

            history = self.context_manager.truncate_history(
                messages=history,
                token_budget=_settings.chat.history_token_budget,
            )
            logger.info(
                "history truncated conv=%s resulting_messages=%d",
                conversation_id,
                len(history),
            )

            tool_schemas = self.context_manager.build_tool_schemas()

            loop_state = AgentLoopState()
            loop_tool_pairs_full: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
            retrieved_chunks: list[RetrievedChunk] = []
            should_answer_now = False

            for iteration in range(1, self.max_iterations + 1):
                loop_state.iteration = iteration
                logger.info(
                    "iteration start conv=%s iter=%d/%d chunks_in_context=%d",
                    conversation_id,
                    iteration,
                    self.max_iterations,
                    len(retrieved_chunks),
                )
                yield {
                    "event": "status",
                    "data": {
                        "step": "thinking",
                        "iteration": iteration,
                        "max_iterations": self.max_iterations,
                        "chunks_in_context": len(retrieved_chunks),
                    },
                }

                system_prompt = self.context_manager.build_system_prompt(
                    document_registry=document_registry,
                    user_context=user_context,
                    current_iteration=iteration,
                    max_iterations=self.max_iterations,
                    chunks_in_context=len(retrieved_chunks),
                    is_general=is_general,
                    practice_question_text=practice_question_text,
                    answer_context_text=answer_context_text,
                )
                logger.info(
                    "system_prompt built conv=%s iter=%d prompt_chars=%d",
                    conversation_id,
                    iteration,
                    len(system_prompt),
                )
                loop_tool_pairs_context, retrieval_overflowed = (
                    self.context_manager.handle_retrieval_overflow(
                        loop_tool_pairs=loop_tool_pairs_full,
                        budget=_settings.chat.retrieval_token_budget,
                    )
                )
                if retrieval_overflowed:
                    logger.info(
                        "retrieval overflow detected conv=%s iter=%d condensed_pairs=%d",
                        conversation_id,
                        iteration,
                        len(loop_tool_pairs_context),
                    )
                llm_messages = self.context_manager.build_llm_messages(
                    system_prompt=system_prompt,
                    history=history,
                    loop_tool_pairs=loop_tool_pairs_context,
                    user_message=message,
                    retrieval_overflowed=retrieval_overflowed,
                    user_message_images=images or [],
                    user_citations=user_citations,
                )
                logger.info(
                    "llm_messages built conv=%s iter=%d messages=%d",
                    conversation_id,
                    iteration,
                    len(llm_messages),
                )

                if iteration == self.max_iterations or should_answer_now:
                    logger.info(
                        "final answer iteration conv=%s iter=%d reason=%s",
                        conversation_id,
                        iteration,
                        "to_final_response" if should_answer_now else "max_iterations",
                    )
                    force_messages = self.context_manager.build_llm_messages(
                        system_prompt=system_prompt,
                        history=history,
                        loop_tool_pairs=loop_tool_pairs_context,
                        user_message=message,
                        retrieval_overflowed=retrieval_overflowed,
                        force_answer_note=(
                            "You MUST answer now with whatever context you have. "
                            "Note any gaps. *Do not call tools.*"
                        ),
                        user_message_images=images or [],
                        user_citations=user_citations,
                    )
                    _rag_final_answer = ""
                    _rag_loop_tool_pairs = loop_tool_pairs_full
                    _stream_usage: UsageInfo | None = None
                    t_stream_start = time.monotonic()
                    ttft_logged = False
                    async for token in self.llm.chat_stream(
                        force_messages, model_override=model, reasoning_level=reasoning
                    ):
                        if isinstance(token, UsageInfo):
                            _stream_usage = token
                            continue
                        if not ttft_logged:
                            t_now = time.monotonic()
                            ttft_llm_ms = (t_now - t_stream_start) * 1000
                            ttft_e2e_ms = (t_now - t_request_start) * 1000
                            logger.info(
                                "[ttft] agent_chat conv=%s model=%s reasoning=%s iter=%d llm_ms=%.1f e2e_ms=%.1f",
                                conversation_id,
                                model or "default",
                                reasoning or "default",
                                iteration,
                                ttft_llm_ms,
                                ttft_e2e_ms,
                            )
                            ttft_logged = True
                        _rag_final_answer += token
                        yield {"event": "token", "data": {"content": token}}
                    # Signal the frontend immediately that token streaming is
                    # done so it can flip stop→send without waiting for DB
                    # writes and title generation that follow.
                    yield {"event": "stream_end", "data": {}}
                    if self._usage_service:
                        self._usage_service.log_usage_fire_and_forget(
                            user_id=user_id,
                            feature="chat",
                            usage=self._stream_usage_or_estimate(
                                _stream_usage,
                                messages=force_messages,
                                output_text=_rag_final_answer,
                                model=model,
                                source="rag_chat",
                            ),
                        )
                    _rag_final_answer = self._strip_response_prefix(_rag_final_answer)
                    final_answer = _rag_final_answer
                    logger.info(
                        "final answer produced conv=%s iter=%d answer_chars=%d final_answer=%s",
                        conversation_id,
                        iteration,
                        len(final_answer),
                        final_answer,
                    )

                    citations = self.citation_extractor.extract(
                        response_text=final_answer,
                        retrieved_chunks=retrieved_chunks,
                        document_registry=document_registry,
                    )
                    logger.info(
                        "citations extracted conv=%s iter=%d count=%d",
                        conversation_id,
                        iteration,
                        len(citations),
                    )
                    (
                        message_id,
                        _user_msg_id,
                        conversation_title,
                    ) = await self._persist_loop_and_emit_completion(
                        conversation_id=conversation_id,
                        folder_id=folder_id,
                        user_message=original_message,  # store clean message in DB
                        user_context=user_context,
                        loop_tool_pairs=loop_tool_pairs_full,
                        assistant_message=final_answer,
                        citations=citations,
                        is_new_conversation=is_new_conversation,
                        existing_conversation_title=existing_conversation_title,
                        images=images,
                        user_citations=user_citations,
                        user_id=user_id,
                        processed_attachments=processed_attachments,
                        parent_id=parent_id,
                        skip_user_save=skip_user_save,
                    )
                    _rag_persisted = True

                    # Prefer a finished title over the fallback so the sidebar
                    # doesn't flash. Otherwise the `title_update` event below
                    # will catch up the UI.
                    if title_task is not None and title_task.done():
                        try:
                            fast_title = title_task.result()
                        except Exception:
                            fast_title = None
                        if fast_title:
                            conversation_title = fast_title

                    logger.info(
                        "completion persisted conv=%s message_id=%s title=%s",
                        conversation_id,
                        message_id,
                        conversation_title,
                    )

                    yield {
                        "event": "message_complete",
                        "data": {
                            "message_id": message_id,
                            "user_message_id": _user_msg_id,
                            "conversation_id": conversation_id,
                            "conversation_title": conversation_title,
                            "content": final_answer,
                            "citations": [asdict(citation) for citation in citations],
                            "text_modified": False,
                        },
                    }

                    followup_questions = self._extract_followups_from_tool_pairs(
                        loop_tool_pairs_full
                    )
                    if followup_questions:
                        logger.info(
                            "followup suggestions conv=%s count=%d",
                            conversation_id,
                            len(followup_questions),
                        )
                        yield {
                            "event": "followup_suggestions",
                            "data": {"questions": followup_questions},
                        }

                    if title_task is not None and not title_task.done():
                        async for ev in self._emit_title_update(
                            title_task, conversation_id
                        ):
                            yield ev
                    return

                # Non-final iteration: use tools-only call — content is always
                # dropped server-side so no flash-and-discard can occur.
                all_tool_calls, _tools_usage = await self.llm.chat_tools_only(
                    llm_messages,
                    tool_schemas,
                    model_override=model,
                    reasoning_level=reasoning,
                )
                if self._usage_service:
                    self._usage_service.log_usage_fire_and_forget(
                        user_id=user_id, feature="chat", usage=_tools_usage,
                    )

                # Separate the to_final_response signal from real tool calls.
                to_final_response_called = any(
                    tc.get("name") == ToolName.TO_FINAL_RESPONSE.value
                    for tc in all_tool_calls
                )
                real_tool_calls = [
                    tc
                    for tc in all_tool_calls
                    if tc.get("name") != ToolName.TO_FINAL_RESPONSE.value
                ]

                if to_final_response_called:
                    should_answer_now = True
                    logger.info(
                        "to_final_response called conv=%s iter=%d",
                        conversation_id,
                        iteration,
                    )
                elif not all_tool_calls:
                    # Model returned no tools at all — treat as to_final_response.
                    should_answer_now = True
                    logger.info(
                        "no tool calls in non-final iter, treating as to_final_response conv=%s iter=%d",
                        conversation_id,
                        iteration,
                    )

                logger.info(
                    "tool calls detected conv=%s iter=%d tools=%s to_final_response=%s",
                    conversation_id,
                    iteration,
                    [tc.get("name") for tc in real_tool_calls],
                    to_final_response_called,
                )

                if real_tool_calls:
                    for tool_call in real_tool_calls:
                        status_payload = self._build_tool_status_event(
                            tool_call, iteration, document_map
                        )
                        if status_payload:
                            yield {"event": "status", "data": status_payload}

                    execution_results = await self._execute_tool_calls_parallel(
                        user_id=user_id,
                        tool_calls=real_tool_calls,
                        document_registry=document_registry,
                    )
                    logger.info(
                        "tool calls executed conv=%s iter=%d count=%d",
                        conversation_id,
                        iteration,
                        len(execution_results),
                    )

                    for execution in execution_results:
                        raw_chunks: list[RetrievedChunk] = execution.get(
                            "raw_chunks", []
                        )
                        unique_chunks, duplicate_count = (
                            self.context_manager.deduplicate_chunks(
                                raw_chunks,
                                loop_state.seen_chunk_ids,
                            )
                        )
                        execution["unique_chunks"] = unique_chunks
                        execution["result_payload"] = self._apply_dedup_to_payload(
                            tool_name=execution["tool_name"],
                            result_payload=execution["result_payload"],
                            unique_chunks=unique_chunks,
                            duplicate_count=duplicate_count,
                        )
                        execution["token_count"] = self.context_manager.estimate_tokens(
                            json.dumps(execution["result_payload"], ensure_ascii=False)
                        )
                        execution["result_message"]["content"] = json.dumps(
                            execution["result_payload"],
                            ensure_ascii=False,
                        )

                        try:
                            loop_state.tool_calls.append(
                                ToolCallResult(
                                    tool=ToolName(execution["tool_name"]),
                                    arguments=execution["arguments"],
                                    result=execution["result_payload"],
                                    token_count=execution["token_count"],
                                )
                            )
                        except ValueError:
                            logger.warning(
                                "unknown tool name from execution tool=%s",
                                execution["tool_name"],
                            )
                        loop_state.total_retrieval_tokens += execution["token_count"]
                        retrieved_chunks.extend(execution["unique_chunks"])

                        if execution["result_payload"].get("error"):
                            logger.warning(
                                "tool error conv=%s iter=%d tool=%s error=%s",
                                conversation_id,
                                iteration,
                                execution["tool_name"],
                                execution["result_payload"].get("error"),
                            )
                            yield {
                                "event": "status",
                                "data": {
                                    "step": "tool_error",
                                    "tool": execution["tool_name"],
                                    "message": execution["result_payload"]["error"],
                                    "iteration": iteration,
                                },
                            }

                    shared_call_message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": str(tc.get("id") or ""),
                                "type": "function",
                                "function": {
                                    "name": str(tc.get("name") or ""),
                                    "arguments": tc.get("arguments") or "{}",
                                },
                            }
                            for tc in real_tool_calls
                        ],
                    }
                    loop_tool_pairs_full.append(
                        (
                            shared_call_message,
                            [ex["result_message"] for ex in execution_results],
                        )
                    )

                    logger.info(
                        "iteration tool phase complete conv=%s iter=%d total_chunks=%d total_tool_calls=%d",
                        conversation_id,
                        iteration,
                        len(retrieved_chunks),
                        len(loop_state.tool_calls),
                    )
                    yield {
                        "event": "status",
                        "data": {
                            "step": "evaluating",
                            "iteration": iteration,
                            "chunks_retrieved": len(retrieved_chunks),
                            "tool_calls_so_far": len(loop_state.tool_calls),
                        },
                    }

                continue

            logger.error(
                "agent loop finished without producing a response conv=%s",
                conversation_id,
            )
            yield self._error_event(
                "Agent loop finished without producing a response.",
                recoverable=False,
            )
        except ValueError:
            logger.exception(
                "ValueError in handle_message user=%s conv=%s folder=%s",
                user_id[:8],
                conversation_id,
                folder_id[:8] if folder_id else "-",
            )
        finally:
            # Persist messages even if client disconnected mid-stream.
            # Skip if there is no content — persisting an empty assistant
            # message pollutes the conversation history with blank bubbles.
            if not _rag_persisted and conversation_id:
                stripped = self._strip_response_prefix(_rag_final_answer) if _rag_final_answer else ""
                if not stripped:
                    logger.info(
                        "skipping persist of empty answer after disconnect (RAG) conv=%s",
                        conversation_id,
                    )
                else:
                    try:
                        await self._persist_loop_and_emit_completion(
                            conversation_id=conversation_id,
                            folder_id=folder_id,
                            user_message=original_message,
                            user_context=user_context,
                            loop_tool_pairs=_rag_loop_tool_pairs,
                            assistant_message=stripped,
                            citations=[],
                            is_new_conversation=is_new_conversation,
                            existing_conversation_title=existing_conversation_title,
                            images=images,
                            user_citations=user_citations,
                            user_id=user_id,
                            processed_attachments=processed_attachments,
                            parent_id=parent_id,
                            skip_user_save=skip_user_save,
                        )
                        logger.info(
                            "persisted messages after client disconnect (RAG) conv=%s answer_len=%d",
                            conversation_id,
                            len(stripped),
                        )
                    except Exception:
                        logger.exception(
                            "failed to persist after disconnect (RAG) conv=%s",
                            conversation_id,
                        )

    async def _handle_direct_chat(
        self,
        user_id: str,
        conversation_id: str | None,
        folder_id: str | None = None,
        message: str = "",
        original_message: str | None = None,
        model: str | None = None,
        reasoning: str | None = None,
        images: list[str] | None = None,
        user_citations: list[str] | None = None,
        is_new_conversation: bool = True,
        test_session_id: str | None = None,
        question_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
        lesson_id: str | None = None,
        lesson_content: str | None = None,
        feynman_history_text: str | None = None,
        practice_question_text: str | None = None,
        answer_context_text: str | None = None,
        current_block_info: str | None = None,
        inline_quiz_answers: list | None = None,
        t_request_start: float | None = None,
        processed_attachments: ProcessedAttachments | None = None,
        parent_id: str | None = None,
        skip_user_save: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Simple direct chat — no RAG tools, no agent loop.

        Used for general chat, lesson scope, and review/feedback scopes
        where all context is pre-fetched by the router.
        """
        images = images or []
        user_citations = user_citations or []
        store_message = original_message if original_message is not None else message
        existing_conversation_title: str | None = None
        history: list[Message] = []
        final_answer = ""
        _persisted = False
        title_task: asyncio.Task[str | None] | None = None

        try:
            if is_new_conversation:
                conversation_id = await self.chat_repo.create_conversation(
                    user_id=user_id,
                    folder_id=folder_id,
                    title=None,
                    test_session_id=test_session_id,
                    question_id=question_id,
                    lesson_id=lesson_id,
                    scope_type=scope_type,
                    feedback_note_id=feedback_note_id,
                )
                logger.info(
                    "direct_chat new conv created conv=%s",
                    conversation_id,
                )
                # Run title generation in parallel with model streaming so the
                # answer isn't blocked. The task persists the title to DB on
                # its own; we surface the result via a `title_update` SSE
                # event after `message_complete`.
                title_task = asyncio.create_task(
                    self._finalize_title(
                        conversation_id=conversation_id,
                        user_message=store_message,
                        user_id=user_id,
                    )
                )
                yield {
                    "event": "metadata",
                    "data": {"conversation_id": conversation_id},
                }
                # No history for a brand-new conversation.
            else:
                conv_task = self.chat_repo.get_conversation(conversation_id)
                history_task = self.chat_repo.get_active_path_history(
                    conversation_id=conversation_id,
                    roles=[MessageRole.USER, MessageRole.ASSISTANT],
                )
                conversation, history = await asyncio.gather(conv_task, history_task)
                logger.info(
                    "direct_chat context loaded conv=%s history_msgs=%d",
                    conversation_id,
                    len(history),
                )
                if (
                    not conversation
                    or conversation.user_id != user_id
                    or conversation.test_session_id != test_session_id
                    or conversation.question_id != question_id
                    or conversation.lesson_id != lesson_id
                    or conversation.scope_type != scope_type
                    or str(conversation.feedback_note_id or "") != (feedback_note_id or "")
                ):
                    yield self._error_event("Conversation not found.", recoverable=False)
                    return
                existing_conversation_title = conversation.title

            history = self.context_manager.truncate_history(
                messages=history,
                token_budget=_settings.chat.history_token_budget,
            )

            system_prompt = self.context_manager.build_system_prompt(
                document_registry=[],
                user_context=UserContext(folder_id=folder_id),
                current_iteration=1,
                max_iterations=1,
                is_general=lesson_content is None and not practice_question_text,
                lesson_content=lesson_content,
                feynman_history_text=feynman_history_text,
                practice_question_text=practice_question_text,
                answer_context_text=answer_context_text,
                current_block_info=current_block_info,
                inline_quiz_answers=inline_quiz_answers,
            )
            logger.info(
                "direct_chat prompt built conv=%s prompt_chars=%d",
                conversation_id,
                len(system_prompt),
            )

            llm_messages = self.context_manager.build_llm_messages(
                system_prompt=system_prompt,
                history=history,
                loop_tool_pairs=[],
                user_message=message,
                user_message_images=images,
                user_citations=user_citations,
            )

            yield {"event": "status", "data": {"step": "thinking"}}

            _stream_usage: UsageInfo | None = None
            t_stream_start = time.monotonic()
            ttft_logged = False
            logger.info(
                "direct_chat llm_stream starting conv=%s model=%s msgs=%d",
                conversation_id,
                model or "default",
                len(llm_messages),
            )
            async for token in self.llm.chat_stream(
                llm_messages, model_override=model, reasoning_level=reasoning
            ):
                if isinstance(token, UsageInfo):
                    _stream_usage = token
                    continue
                if not ttft_logged:
                    t_now = time.monotonic()
                    ttft_llm_ms = (t_now - t_stream_start) * 1000
                    ttft_e2e_ms = (
                        (t_now - t_request_start) * 1000
                        if t_request_start
                        else ttft_llm_ms
                    )
                    logger.info(
                        "[ttft] direct_chat conv=%s model=%s reasoning=%s llm_ms=%.1f e2e_ms=%.1f",
                        conversation_id or "pending",
                        model or "default",
                        reasoning or "default",
                        ttft_llm_ms,
                        ttft_e2e_ms,
                    )
                    ttft_logged = True
                final_answer += token
                yield {"event": "token", "data": {"content": token}}

            yield {"event": "stream_end", "data": {}}

            if self._usage_service:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id,
                    feature="chat",
                    usage=self._stream_usage_or_estimate(
                        _stream_usage,
                        messages=llm_messages,
                        output_text=final_answer,
                        model=model,
                        source="direct_chat",
                    ),
                )

            final_answer = self._strip_response_prefix(final_answer)

            # Persist user + assistant messages.
            _assistant_msg_id, _user_msg_id = await self._persist_direct_chat(
                conversation_id=conversation_id,
                store_message=store_message,
                final_answer=final_answer,
                images=images,
                user_citations=user_citations,
                processed_attachments=processed_attachments,
                parent_id=parent_id,
                skip_user_save=skip_user_save,
            )
            _persisted = True

            # If the title task already finished while we were streaming /
            # persisting, prefer its result so the sidebar doesn't flash the
            # fallback. Otherwise yield the fallback now and let the
            # `title_update` event below catch up the UI.
            conversation_title = existing_conversation_title or self._fallback_title(
                store_message
            )
            if title_task is not None and title_task.done():
                try:
                    fast_title = title_task.result()
                except Exception:
                    fast_title = None
                if fast_title:
                    conversation_title = fast_title

            yield {
                "event": "message_complete",
                "data": {
                    "message_id": _assistant_msg_id,
                    "user_message_id": _user_msg_id,
                    "conversation_id": conversation_id,
                    "conversation_title": conversation_title,
                    "content": final_answer,
                    "citations": [],
                    "text_modified": False,
                },
            }

            # Slow path: title task still running. Wait for it (with a hard
            # cap) and emit a separate `title_update` event so the sidebar
            # updates without a page reload.
            if title_task is not None and not title_task.done():
                async for ev in self._emit_title_update(
                    title_task, conversation_id
                ):
                    yield ev
        except PromptNotFoundError as e:
            logger.error(
                "prompt not configured user=%s conv=%s prompt=%s",
                user_id[:8],
                conversation_id or "new",
                str(e),
            )
            yield self._error_event("Chat service is not configured correctly.", recoverable=False)
        except Exception:
            logger.exception(
                "direct chat error user=%s conv=%s",
                user_id[:8],
                conversation_id or "new",
            )
            yield self._error_event("An unexpected error occurred.", recoverable=False)
        finally:
            # Persist messages even if client disconnected mid-stream.
            # GeneratorExit from client abort triggers this block.
            # Skip if there is no content — persisting an empty assistant
            # message pollutes the conversation history with blank bubbles.
            if not _persisted and conversation_id:
                stripped = self._strip_response_prefix(final_answer) if final_answer else ""
                if not stripped:
                    logger.info(
                        "skipping persist of empty answer after disconnect conv=%s",
                        conversation_id,
                    )
                else:
                    try:
                        await self._persist_direct_chat(
                            conversation_id=conversation_id,
                            store_message=store_message,
                            final_answer=stripped,
                            images=images,
                            user_citations=user_citations,
                            processed_attachments=processed_attachments,
                            parent_id=parent_id,
                            skip_user_save=skip_user_save,
                        )
                        # `title_task` (if any) was spawned before streaming
                        # and continues running independently of this
                        # generator's lifecycle, so it will persist the title
                        # even after a client disconnect.
                        logger.info(
                            "persisted messages after client disconnect conv=%s answer_len=%d",
                            conversation_id,
                            len(stripped),
                        )
                    except Exception:
                        logger.exception(
                            "failed to persist after disconnect conv=%s",
                            conversation_id,
                        )

    async def _execute_tool_calls_parallel(
        self,
        user_id: str,
        tool_calls: list[dict[str, Any]],
        document_registry: list[DocumentInfo],
    ) -> list[dict[str, Any]]:
        document_map = {doc.document_id: doc for doc in document_registry}

        async def _run(tool_call: dict[str, Any]) -> dict[str, Any]:
            async with self._tool_call_semaphore:
                return await self._execute_single_tool_call(
                    user_id=user_id,
                    tool_call=tool_call,
                    document_map=document_map,
                )

        return await asyncio.gather(*[_run(tc) for tc in tool_calls])

    async def _execute_single_tool_call(
        self,
        user_id: str,
        tool_call: dict[str, Any],
        document_map: dict[str, DocumentInfo],
    ) -> dict[str, Any]:
        tool_name = str(tool_call.get("name") or "")
        call_id = str(tool_call.get("id") or uuid.uuid4())
        raw_arguments = tool_call.get("arguments") or {}

        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}

        result_payload: dict[str, Any]
        raw_chunks: list[RetrievedChunk] = []

        try:
            if tool_name == ToolName.RAG_SEARCH.value:
                result_payload, raw_chunks = await self._execute_rag_search(
                    user_id=user_id,
                    arguments=arguments,
                    document_map=document_map,
                )
            elif tool_name == ToolName.GET_PAGES.value:
                result_payload, raw_chunks = await self._execute_get_pages(
                    user_id=user_id,
                    arguments=arguments,
                    document_map=document_map,
                )
            elif tool_name == ToolName.ASK_CLARIFICATION.value:
                result_payload, raw_chunks = self._execute_ask_clarification(arguments)
            elif tool_name == ToolName.TO_FINAL_RESPONSE.value:
                result_payload = {
                    "tool": ToolName.TO_FINAL_RESPONSE.value,
                    "message": "Proceeding to final answer.",
                }
            else:
                result_payload = {
                    "tool": tool_name,
                    "error": f"Unsupported tool '{tool_name}'.",
                }
        except Exception as exc:
            result_payload = {
                "tool": tool_name,
                "error": f"{tool_name} failed: {exc}. Try a different query or answer with available context.",
            }

        result_message = {
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": json.dumps(result_payload, ensure_ascii=False),
        }

        return {
            "tool_name": tool_name,
            "call_id": call_id,
            "arguments": arguments,
            "result_payload": result_payload,
            "result_message": result_message,
            "token_count": self.context_manager.estimate_tokens(
                result_message["content"]
            ),
            "raw_chunks": raw_chunks,
            "unique_chunks": [],
        }

    @staticmethod
    def _extract_followups_from_tool_pairs(
        loop_tool_pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    ) -> list[str]:
        for _call, result_msgs in loop_tool_pairs:
            for msg in result_msgs:
                try:
                    payload = json.loads(msg.get("content") or "{}")
                    if payload.get("tool") == ToolName.ASK_CLARIFICATION.value:
                        qs = payload.get("questions") or []
                        if isinstance(qs, list):
                            return [str(q).strip() for q in qs if str(q).strip()]
                except (json.JSONDecodeError, TypeError):
                    pass
        return []

    @staticmethod
    def _execute_ask_clarification(
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], list[RetrievedChunk]]:
        reason = str(arguments.get("reason") or "")
        questions = arguments.get("questions")
        if not isinstance(questions, list):
            return (
                {
                    "tool": ToolName.ASK_CLARIFICATION.value,
                    "error": "Missing or invalid 'questions' array.",
                },
                [],
            )
        qs = [str(q).strip() for q in questions if str(q).strip()][
            : _settings.chat.followup_max_questions
        ]
        if not qs:
            return (
                {
                    "tool": ToolName.ASK_CLARIFICATION.value,
                    "error": "At least one non-empty question required.",
                },
                [],
            )
        return (
            {
                "tool": ToolName.ASK_CLARIFICATION.value,
                "reason": reason,
                "questions": qs,
            },
            [],
        )

    async def _execute_rag_search(
        self,
        user_id: str,
        arguments: dict[str, Any],
        document_map: dict[str, DocumentInfo],
    ) -> tuple[dict[str, Any], list[RetrievedChunk]]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return (
                {
                    "tool": ToolName.RAG_SEARCH.value,
                    "error": "Missing required argument 'query'.",
                },
                [],
            )

        document_ids = arguments.get("document_ids")
        if document_ids is not None and not isinstance(document_ids, list):
            return (
                {
                    "tool": ToolName.RAG_SEARCH.value,
                    "error": "Invalid 'document_ids'. Expected an array of UUID strings.",
                },
                [],
            )

        requested_ids = [str(doc_id) for doc_id in (document_ids or [])]
        invalid_ids = [doc_id for doc_id in requested_ids if doc_id not in document_map]
        if invalid_ids:
            return (
                {
                    "tool": ToolName.RAG_SEARCH.value,
                    "error": (
                        f"Invalid document_ids {invalid_ids}. "
                        f"Available documents: {list(document_map.keys())}."
                    ),
                },
                [],
            )

        embedding = await self.embedding.embed_query(query)
        chunks = await self.retrieval.semantic_search(
            user_id=user_id,
            query_embedding=embedding,
            document_ids=requested_ids or None,
            top_k=_settings.rag.top_k,
            threshold=_settings.rag.similarity_threshold,
        )

        for chunk in chunks:
            if chunk.document_id in document_map:
                chunk.document_name = document_map[chunk.document_id].name

        result_rows = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "page": chunk.page,
                "similarity_score": chunk.similarity_score,
            }
            for chunk in chunks
        ]

        payload = {
            "tool": ToolName.RAG_SEARCH.value,
            "query_used": query,
            "results": result_rows,
            "result_count": len(result_rows),
        }

        return payload, chunks

    async def _execute_get_pages(
        self,
        user_id: str,
        arguments: dict[str, Any],
        document_map: dict[str, DocumentInfo],
    ) -> tuple[dict[str, Any], list[RetrievedChunk]]:
        document_id = str(arguments.get("document_id") or "").strip()
        if document_id not in document_map:
            return (
                {
                    "tool": ToolName.GET_PAGES.value,
                    "error": (
                        f"Invalid document_id '{document_id}'. "
                        f"Available documents: {list(document_map.keys())}."
                    ),
                },
                [],
            )

        try:
            requested_start = int(arguments.get("start_page"))
            requested_end = int(arguments.get("end_page"))
        except (TypeError, ValueError):
            return (
                {
                    "tool": ToolName.GET_PAGES.value,
                    "error": "start_page and end_page must be integers.",
                },
                [],
            )

        if requested_start > requested_end:
            return (
                {
                    "tool": ToolName.GET_PAGES.value,
                    "error": "Invalid range: start_page cannot be greater than end_page.",
                },
                [],
            )

        document = document_map[document_id]
        start_page = max(1, requested_start)
        end_page = min(document.page_count, requested_end)

        if start_page > end_page:
            return (
                {
                    "tool": ToolName.GET_PAGES.value,
                    "error": (
                        f"Requested pages [{requested_start}, {requested_end}] are out of bounds for "
                        f"document with {document.page_count} pages."
                    ),
                },
                [],
            )

        chunks = await self.retrieval.get_chunks_by_pages(
            user_id=user_id,
            document_id=document_id,
            start_page=start_page,
            end_page=end_page,
            buffer=_settings.chat.page_buffer,
        )

        for chunk in chunks:
            chunk.document_name = document.name

        actual_start = max(1, start_page - _settings.chat.page_buffer)
        actual_end = min(document.page_count, end_page + _settings.chat.page_buffer)
        serialized_chunks = [
            {"chunk_id": chunk.chunk_id, "text": chunk.text, "page": chunk.page}
            for chunk in chunks
        ]

        payload = {
            "tool": ToolName.GET_PAGES.value,
            "document_id": document_id,
            "document_name": document.name,
            "requested_range": [requested_start, requested_end],
            "actual_range_with_buffer": [actual_start, actual_end],
            "chunks": serialized_chunks,
            "chunk_count": len(serialized_chunks),
        }

        notes: list[str] = []
        if requested_start != start_page or requested_end != end_page:
            notes.append(
                f"Requested range was clamped to [{start_page}, {end_page}] based on document page limits."
            )
        if notes:
            payload["note"] = " ".join(notes)

        return payload, chunks

    @staticmethod
    def _apply_dedup_to_payload(
        tool_name: str,
        result_payload: dict[str, Any],
        unique_chunks: list[RetrievedChunk],
        duplicate_count: int,
    ) -> dict[str, Any]:
        if result_payload.get("error"):
            return result_payload

        if tool_name == ToolName.RAG_SEARCH.value:
            allowed_ids = {chunk.chunk_id for chunk in unique_chunks}
            filtered = [
                item
                for item in (result_payload.get("results") or [])
                if str(item.get("chunk_id")) in allowed_ids
            ]
            result_payload["results"] = filtered
            result_payload["result_count"] = len(filtered)
            if duplicate_count:
                result_payload["note"] = (
                    f"{duplicate_count} duplicate chunks from previous searches were excluded."
                )
            return result_payload

        if tool_name == ToolName.GET_PAGES.value:
            allowed_ids = {chunk.chunk_id for chunk in unique_chunks}
            filtered = [
                item
                for item in (result_payload.get("chunks") or [])
                if str(item.get("chunk_id")) in allowed_ids
            ]
            result_payload["chunks"] = filtered
            result_payload["chunk_count"] = len(filtered)
            if duplicate_count:
                existing_note = result_payload.get("note")
                duplicate_note = f"{duplicate_count} duplicate chunks from previous retrievals were excluded."
                result_payload["note"] = (
                    f"{existing_note} {duplicate_note}".strip()
                    if existing_note
                    else duplicate_note
                )
            return result_payload

        return result_payload

    async def _persist_loop_and_emit_completion(
        self,
        conversation_id: str,
        folder_id: str,
        user_message: str,
        user_context: UserContext,
        loop_tool_pairs: list[tuple[dict[str, Any], list[dict[str, Any]]]],
        assistant_message: str,
        citations: list[Citation],
        is_new_conversation: bool,
        existing_conversation_title: str | None,
        images: list[str] | None = None,
        user_citations: list[str] | None = None,
        user_id: str | None = None,
        processed_attachments: ProcessedAttachments | None = None,
        parent_id: str | None = None,
        skip_user_save: bool = False,
    ) -> tuple[str, str]:
        if skip_user_save:
            # User message already saved by caller (regenerate endpoint).
            user_msg_id = parent_id
        else:
            user_metadata: dict[str, Any] = {
                "folder_id": folder_id,
                "current_document_id": user_context.current_document_id,
                "current_page": user_context.current_page,
                "total_pages": user_context.total_pages,
            }
            if images:
                s3_keys = await self._upload_images_to_s3(conversation_id, images)
                if s3_keys:
                    user_metadata["image_s3_keys"] = s3_keys
            if user_citations:
                user_metadata["citations"] = user_citations
            if processed_attachments:
                if processed_attachments.s3_keys:
                    user_metadata["attachment_s3_keys"] = processed_attachments.s3_keys
                if processed_attachments.text_blocks:
                    user_metadata["attachment_texts"] = text_blocks_to_metadata(
                        processed_attachments.text_blocks
                    )
                if processed_attachments.attachment_meta:
                    user_metadata["attachments"] = processed_attachments.attachment_meta

            user_msg_id = str(uuid.uuid4())
            next_vi = await self.chat_repo.get_next_version_index(
                parent_id, conversation_id, role=MessageRole.USER.value
            )
            await self.chat_repo.save_message(
                Message(
                    id=user_msg_id,
                    conversation_id=conversation_id,
                    role=MessageRole.USER,
                    content=user_message,
                    metadata={k: v for k, v in user_metadata.items() if v is not None},
                ),
                parent_id=parent_id,
                version_index=next_vi,
            )
            await self.chat_repo.append_to_active_path(conversation_id, user_msg_id)

        # Save tool call/result pairs as children of the user message.
        for call_message, result_messages in loop_tool_pairs:
            tool_calls = call_message.get("tool_calls") or []
            for tc, result_message in zip(tool_calls, result_messages):
                tool_call_payload = self._serialize_single_tool_call_for_storage(tc)
                await self.chat_repo.save_message(
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role=MessageRole.TOOL_CALL,
                        content=json.dumps(tool_call_payload, ensure_ascii=False),
                        metadata={},
                    ),
                    parent_id=user_msg_id,
                    version_index=1,
                )
                tool_result_payload = self._serialize_tool_result_for_storage(
                    result_message
                )
                await self.chat_repo.save_message(
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role=MessageRole.TOOL_RESULT,
                        content=json.dumps(tool_result_payload, ensure_ascii=False),
                        metadata={},
                    ),
                    parent_id=user_msg_id,
                    version_index=1,
                )

        # Save assistant message as child of the user message.
        citations_payload = [asdict(citation) for citation in citations]
        assistant_msg_id = str(uuid.uuid4())
        asst_vi = await self.chat_repo.get_next_version_index(
            user_msg_id, conversation_id, role=MessageRole.ASSISTANT.value
        )
        assistant_message_id = await self.chat_repo.save_message(
            Message(
                id=assistant_msg_id,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=assistant_message,
                metadata={"citations": citations_payload} if citations_payload else {},
            ),
            parent_id=user_msg_id,
            version_index=asst_vi,
        )
        await self.chat_repo.append_to_active_path(conversation_id, assistant_message_id)

        await self.chat_repo.touch_conversation(conversation_id)

        # Title generation is owned by the caller (handle_message), which
        # spawns it in parallel with the RAG loop and emits a `title_update`
        # SSE event when the real title is ready.
        conversation_title = existing_conversation_title or self._fallback_title(
            user_message
        )

        return assistant_message_id, user_msg_id, conversation_title

    async def _persist_direct_chat(
        self,
        conversation_id: str,
        store_message: str,
        final_answer: str,
        images: list[str],
        user_citations: list[str],
        processed_attachments: ProcessedAttachments | None,
        parent_id: str | None = None,
        skip_user_save: bool = False,
    ) -> str:
        """Save user + assistant messages and touch the conversation timestamp.

        Returns the assistant message UUID string.
        """
        if skip_user_save:
            # The user message was already saved by the caller (e.g. regenerate
            # endpoint).  Determine the user_msg_id so the assistant message can
            # reference it as its parent.
            # For user-edit: parent_id is the branch parent; the new user message
            #   is the last item already on active_path.
            # For assistant-regen: parent_id is the original user message id.
            user_msg_id = parent_id
        else:
            # For normal messages: parent should be the last message in active_path
            # (i.e. the previous assistant response), not None.
            if parent_id is None:
                active_path = await self.chat_repo.get_active_path(conversation_id)
                if active_path:
                    parent_id = active_path[-1]
            user_metadata: dict[str, Any] = {}
            if images:
                s3_keys = await self._upload_images_to_s3(conversation_id, images)
                if s3_keys:
                    user_metadata["image_s3_keys"] = s3_keys
            if user_citations:
                user_metadata["citations"] = user_citations
            if processed_attachments:
                if processed_attachments.s3_keys:
                    user_metadata["attachment_s3_keys"] = processed_attachments.s3_keys
                if processed_attachments.text_blocks:
                    user_metadata["attachment_texts"] = text_blocks_to_metadata(
                        processed_attachments.text_blocks
                    )
                if processed_attachments.attachment_meta:
                    user_metadata["attachments"] = processed_attachments.attachment_meta

            user_msg_id = str(uuid.uuid4())
            next_vi = await self.chat_repo.get_next_version_index(
                parent_id, conversation_id, role=MessageRole.USER.value
            )
            await self.chat_repo.save_message(
                Message(
                    id=user_msg_id,
                    conversation_id=conversation_id,
                    role=MessageRole.USER,
                    content=store_message,
                    metadata={k: v for k, v in user_metadata.items() if v is not None},
                ),
                parent_id=parent_id,
                version_index=next_vi,
            )
            await self.chat_repo.append_to_active_path(conversation_id, user_msg_id)

        # Save assistant message as child of the user message.
        assistant_msg_id = str(uuid.uuid4())
        asst_vi = await self.chat_repo.get_next_version_index(
            user_msg_id, conversation_id, role=MessageRole.ASSISTANT.value
        )
        await self.chat_repo.save_message(
            Message(
                id=assistant_msg_id,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=final_answer,
                metadata={},
            ),
            parent_id=user_msg_id,
            version_index=asst_vi,
        )
        await self.chat_repo.append_to_active_path(conversation_id, assistant_msg_id)
        await self.chat_repo.touch_conversation(conversation_id)
        return assistant_msg_id, user_msg_id

    async def _upload_images_to_s3(
        self,
        conversation_id: str,
        images: list[str],
    ) -> list[str]:
        """Upload base64 data-URI images to S3. Returns list of S3 object keys."""
        s3_keys: list[str] = []
        for img in images:
            match = _DATA_URI_RE.match(img)
            if not match:
                logger.warning("Skipping non-data-URI image (len=%d)", len(img))
                continue
            mime = match.group("mime")
            raw_b64 = match.group("data")
            ext = _MIME_TO_EXT.get(mime, "bin")
            try:
                raw_bytes = base64.b64decode(raw_b64)
            except Exception:
                logger.warning("Failed to decode base64 image, skipping")
                continue
            key = f"chat-images/{conversation_id}/{uuid.uuid4()}.{ext}"
            try:
                await self.s3.upload_bytes(key, raw_bytes, content_type=mime)
                s3_keys.append(key)
            except Exception:
                logger.exception("Failed to upload image to S3 key=%s", key)
        return s3_keys

    async def _finalize_title(
        self,
        conversation_id: str,
        user_message: str,
        user_id: str | None = None,
    ) -> str | None:
        """Generate title via LLM, persist to DB, return final title (or None)."""
        try:
            title, usage = await self.llm.generate_title(user_message)
            if self._usage_service and user_id:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=user_id, feature="chat_title", usage=usage,
                )
            title = title.strip()[: _settings.chat.conversation_title_max_length]
            if not title:
                return None
            await self.chat_repo.update_conversation_title(conversation_id, title)
            return title
        except Exception:
            logger.exception("title generation failed conv=%s", conversation_id)
            return None

    async def _emit_title_update(
        self,
        title_task: asyncio.Task[str | None] | None,
        conversation_id: str,
        timeout: float = 15.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Wait for the background title task and yield a `title_update` SSE event.

        Uses asyncio.shield so the task keeps running (and persists the title)
        even if this generator is cancelled or the await times out.
        """
        if title_task is None:
            return
        try:
            title = await asyncio.wait_for(
                asyncio.shield(title_task), timeout=timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return
        if title:
            yield {
                "event": "title_update",
                "data": {
                    "conversation_id": conversation_id,
                    "title": title,
                },
            }

    @staticmethod
    def _fallback_title(user_message: str) -> str:
        fallback = user_message.strip().replace("\n", " ")
        if len(fallback) <= _settings.chat.conversation_title_max_length:
            return fallback
        return (
            fallback[: _settings.chat.conversation_title_max_length - 3].rstrip()
            + "..."
        )

    @staticmethod
    def _build_tool_status_event(
        tool_call: dict[str, Any],
        iteration: int,
        document_map: dict[str, DocumentInfo],
    ) -> dict[str, Any] | None:
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if tool_name == ToolName.RAG_SEARCH.value:
            query = str(arguments.get("query") or "")
            document_ids = arguments.get("document_ids") or []
            filtered_doc_names = [
                document_map[d].name for d in document_ids if d in document_map
            ]
            status: dict[str, Any] = {
                "step": "searching",
                "tool": ToolName.RAG_SEARCH.value,
                "query": query,
                "iteration": iteration,
            }
            if filtered_doc_names:
                status["filtered_documents"] = filtered_doc_names
            return status

        if tool_name == ToolName.GET_PAGES.value:
            document_id = str(arguments.get("document_id") or "")
            doc = document_map.get(document_id)
            document_name = doc.name if doc else document_id
            return {
                "step": "reading_pages",
                "tool": ToolName.GET_PAGES.value,
                "document_id": document_id,
                "document_name": document_name,
                "pages": [arguments.get("start_page"), arguments.get("end_page")],
                "iteration": iteration,
            }

        if tool_name == ToolName.ASK_CLARIFICATION.value:
            return {"step": "asking_clarification", "iteration": iteration}

        return None

    @staticmethod
    def _error_event(message: str, recoverable: bool) -> dict[str, Any]:
        return {
            "event": "error",
            "data": {
                "message": message,
                "recoverable": recoverable,
            },
        }

    @staticmethod
    def _chunk_for_stream(text: str, chunk_size: int = 4):
        words = text.split(" ")
        for i in range(0, len(words), chunk_size):
            yield " ".join(words[i : i + chunk_size]) + (
                " " if i + chunk_size < len(words) else ""
            )

    @staticmethod
    def _strip_response_prefix(text: str) -> str:
        stripped = text.lstrip()
        lines = stripped.splitlines(keepends=True)
        result_lines = []
        skipping = True
        for line in lines:
            if skipping:
                clean = line.strip()
                if clean and not re.search(r"[a-zA-Z0-9а-яА-ЯёЁ]", clean):
                    continue
                skipping = False
            result_lines.append(line)
        result = "".join(result_lines).lstrip()
        result = re.sub(r'^[\s.,!?;\'"\-—()\[\]\{\}\*#@…]+', "", result)
        return result

    @staticmethod
    def _serialize_single_tool_call_for_storage(
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        function_data = tool_call.get("function") or {}
        arguments = function_data.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        return {
            "tool": function_data.get("name"),
            "arguments": arguments,
            "tool_call_id": tool_call.get("id"),
        }

    @staticmethod
    def _serialize_tool_result_for_storage(
        result_message: dict[str, Any],
    ) -> dict[str, Any]:
        content = result_message.get("content") or {}
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = {"raw": content}
        elif isinstance(content, dict):
            payload = content
        else:
            payload = {"raw": str(content)}

        payload["tool_call_id"] = result_message.get("tool_call_id")
        return payload
