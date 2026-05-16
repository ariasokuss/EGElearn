"""Chat API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Annotated, Any, AsyncIterator

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse, FileResponse

from src.api.deps import CurrentUser, get_container, get_prompt_manager
from src.activity.service import ActivityEventInput, log_activity_from_request
from src.chat.agent import DocumentChatAgent
from src.chat.entities import Message, MessageRole
from src.chat.interfaces import ChatRepository
from src.chat.lesson_scope import resolve_lesson_scope_param
from src.chat.practice_scope import resolve_practice_scope_params
from src.chat.schemas import (
    AttachmentSchema,
    AvailableModelsResponse,
    ChatMessageRequest,
    ConversationSummary,
    FolderDocumentRead,
    GetMessagesResponse,
    GetSiblingsResponse,
    ListConversationsResponse,
    ListFolderDocumentsResponse,
    MessageSchema,
    RegenerateRequest,
    RenameTitleRequest,
    SiblingSchema,
    SwitchBranchRequest,
    SwitchBranchResponse,
    UpdateActivePathRequest,
)
from src.chat.scope_context import fetch_answer_context, fetch_current_block_info, fetch_lesson_context, fetch_practice_question_text
from src.files import service as files_service
from src.learning.tests.session_service import TestSessionService
from src.prompts.manager import PromptManager
from src.runtime import AppContainer

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

_SSE_WATCHDOG_TIMEOUT = 15.0  # seconds of silence before closing the stream;
# generous to cover cold-start LLM latency without false positives (typical TTFT <3s)

CHAT_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


def _chat_replay_payload(
    *,
    user_message: str,
    assistant_message: str,
    conversation_id: object | None,
    user_message_id: object | None,
    assistant_message_id: object | None,
) -> dict[str, Any]:
    refs = {
        "conversation_id": str(conversation_id) if conversation_id else None,
        "user_message_id": str(user_message_id) if user_message_id else None,
        "assistant_message_id": str(assistant_message_id)
        if assistant_message_id
        else None,
    }
    return {
        "schema_version": 1,
        "items": [
            {
                "kind": "user_message",
                "title": "User message",
                "text": user_message,
            },
            {
                "kind": "llm_response",
                "title": "Assistant reply",
                "text": assistant_message,
            },
        ],
        "refs": {key: value for key, value in refs.items() if value is not None},
    }


def _chat_action_replay_payload(
    *,
    title: str,
    value: str,
    refs: dict[str, object | None],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "items": [
            {
                "kind": "user_action",
                "title": title,
                "value": value,
            }
        ],
        "refs": {
            key: str(value)
            for key, value in refs.items()
            if value is not None
        },
    }


@router.get("", include_in_schema=False)
async def chat_page() -> FileResponse:
    """Serve the RAG chat UI."""
    return FileResponse(CHAT_ASSETS_DIR / "index.html")


def get_chat_agent(request: Request) -> DocumentChatAgent:
    agent = getattr(request.app.state, "chat_agent", None)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat agent is not configured.",
        )
    return agent


def _get_test_session_service(
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TestSessionService:
    return TestSessionService(
        session_factory=container.session_factory,
        usage_service=getattr(request.app.state, "usage_service", None),
    )


def get_chat_repo(request: Request) -> ChatRepository:
    repo = getattr(request.app.state, "chat_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat repository is not configured.",
        )
    return repo


@router.get("/stream-test")
async def stream_test() -> StreamingResponse:
    """Test streaming: returns tokens one by one with 100ms delay."""

    async def gen() -> AsyncIterator[str]:
        words = "Это тест стриминга. Текст появляется по одному слову.".split()
        for w in words:
            chunk = _format_sse("token", {"content": w + " "})
            yield chunk
            await asyncio.sleep(0.1)
        yield _format_sse("message_complete", {"content": "Готово.", "citations": []})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def post_chat_message(
    payload: ChatMessageRequest,
    current_user: CurrentUser,
    request: Request,
    container: AppContainer = Depends(get_container),
    agent: DocumentChatAgent = Depends(get_chat_agent),
    repo: ChatRepository = Depends(get_chat_repo),
    tests_service: TestSessionService = Depends(_get_test_session_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> StreamingResponse:
    t_router_start = time.monotonic()
    user_id = str(current_user.id)

    is_general = payload.folder_id is None
    scoped_lesson_id: str | None = None

    if not is_general:
        try:
            uuid.UUID(payload.folder_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="folder_id must be a valid UUID",
            )

        await resolve_practice_scope_params(
            payload.folder_id,
            payload.test_session_id,
            payload.question_id,
            current_user,
            tests_service,
            scope_type=payload.scope_type,
        )
        scoped_lesson_id = await resolve_lesson_scope_param(
            payload.folder_id,
            payload.lesson_id,
            current_user,
            container.session_factory,
        )

    msg_preview = (payload.message or "")[:50] + (
        "…" if len(payload.message or "") > 50 else ""
    )
    logger.info(
        "[chat] user=%s folder=%s conv=%s model=%s reasoning=%s msg=%s",
        user_id[:8],
        (payload.folder_id or "-")[:8],
        payload.conversation_id or "new",
        payload.model or "default",
        payload.reasoning or "default",
        msg_preview,
    )

    # For general chat, skip the expensive pre-validation — the agent handles it.
    if not is_general and payload.conversation_id:
        conversation = await repo.get_conversation(payload.conversation_id)
        if (
            not conversation
            or conversation.user_id != user_id
            or conversation.folder_id != payload.folder_id
            or conversation.test_session_id != payload.test_session_id
            or conversation.question_id != payload.question_id
            or conversation.lesson_id != scoped_lesson_id
            or conversation.scope_type != payload.scope_type
            or str(conversation.feedback_note_id or "") != (payload.feedback_note_id or "")
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
            )

    if not is_general:
        folder_documents = await repo.get_folder_documents(
            user_id=user_id, folder_id=payload.folder_id
        )
        documents_by_id = {doc.document_id: doc for doc in folder_documents}
    else:
        folder_documents = []
        documents_by_id = {}

    if payload.current_document_id and payload.folder_id is not None:
        doc = documents_by_id.get(payload.current_document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="current_document_id is not part of this folder.",
            )
        if payload.current_page is None or payload.total_pages is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="current_page and total_pages are required with current_document_id.",
            )
        if payload.current_page < 1 or payload.current_page > doc.page_count:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"current_page must be within [1, {doc.page_count}].",
            )

    # Fetch scope context (lesson content + feynman history, or practice question).
    lesson_content: str | None = None
    feynman_history_text: str | None = None
    practice_question_text: str | None = None
    current_block_info: str | None = None
    answer_context_text: str | None = None

    if scoped_lesson_id:
        lesson_content, feynman_history_text = await fetch_lesson_context(
            session_factory=container.session_factory,
            lesson_id=scoped_lesson_id,
            user_id=user_id,
        )
        if payload.current_block_id:
            current_block_info = await fetch_current_block_info(
                session_factory=container.session_factory,
                block_id=payload.current_block_id,
            )
    elif payload.question_id:
        practice_question_text = await fetch_practice_question_text(
            session_factory=container.session_factory,
            question_id=payload.question_id,
        )
        # Fetch answer context for practice/review/feedback_review scopes
        if payload.test_session_id:
            answer_context_text = await fetch_answer_context(
                session_factory=container.session_factory,
                test_session_id=payload.test_session_id,
                question_id=payload.question_id,
                scope_type=payload.scope_type,
                feedback_note_id=payload.feedback_note_id,
            )

    t_router_done = time.monotonic()
    logger.info(
        "[ttft-router] user=%s router_overhead_ms=%.1f",
        user_id[:8],
        (t_router_done - t_router_start) * 1000,
    )

    # Validate required system prompt exists before establishing the SSE stream
    # so the client gets an HTTP error code rather than a silent stream failure.
    prompt_key = "system_prompt_general" if is_general else "system_prompt"
    if not scoped_lesson_id and pm.get_or_none("chat", prompt_key) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat service unavailable: prompt 'chat.{prompt_key}' is not configured.",
        )

    # Run agent in a separate task so it always completes (LLM stream +
    # persistence) even if the client disconnects mid-stream.
    event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    chat_activity_logged = False

    def _log_chat_activity(event: dict[str, Any]) -> None:
        nonlocal chat_activity_logged
        if event.get("event") != "message_complete" or chat_activity_logged:
            return
        data = event.get("data")
        data = data if isinstance(data, dict) else {}
        assistant_message = str(data.get("content") or "")
        conversation_id = data.get("conversation_id") or payload.conversation_id
        user_message_id = data.get("user_message_id")
        assistant_message_id = data.get("message_id")
        citations = data.get("citations")
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="chat_message_sent",
                event_group="chat",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="conversation" if conversation_id else None,
                entity_id=_uuid_or_none(
                    str(conversation_id) if conversation_id else None
                ),
                folder_id=_uuid_or_none(payload.folder_id),
                lesson_id=_uuid_or_none(scoped_lesson_id),
                test_session_id=_uuid_or_none(payload.test_session_id),
                metadata={
                    "message_length": len(payload.message or ""),
                    "assistant_message_length": len(assistant_message),
                    "citation_count": len(citations)
                    if isinstance(citations, list)
                    else 0,
                    "has_folder_scope": payload.folder_id is not None,
                    "has_test_scope": payload.test_session_id is not None,
                    "has_lesson_scope": scoped_lesson_id is not None,
                    "has_images": bool(payload.images),
                    "has_attachments": bool(payload.attachments),
                    "scope_type": payload.scope_type,
                    "conversation_id": str(conversation_id)
                    if conversation_id
                    else None,
                    "user_message_id": str(user_message_id)
                    if user_message_id
                    else None,
                    "assistant_message_id": str(assistant_message_id)
                    if assistant_message_id
                    else None,
                },
                replay_payload=_chat_replay_payload(
                    user_message=payload.message or "",
                    assistant_message=assistant_message,
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                ),
            ),
        )
        chat_activity_logged = True

    async def _run_agent() -> None:
        try:
            async for event in agent.handle_message(
                user_id=user_id,
                conversation_id=payload.conversation_id,
                folder_id=payload.folder_id,
                message=payload.message,
                current_document_id=payload.current_document_id,
                current_page=payload.current_page,
                total_pages=payload.total_pages,
                model=payload.model,
                reasoning=payload.reasoning,
                images=payload.images or [],
                user_citations=payload.citations or [],
                test_session_id=payload.test_session_id,
                question_id=payload.question_id,
                scope_type=payload.scope_type,
                feedback_note_id=payload.feedback_note_id,
                attachments=payload.attachments or [],
                lesson_id=scoped_lesson_id,
                lesson_content=lesson_content,
                feynman_history_text=feynman_history_text,
                practice_question_text=practice_question_text,
                answer_context_text=answer_context_text,
                current_block_info=current_block_info,
                inline_quiz_answers=payload.inline_quiz_answers or None,
            ):
                _log_chat_activity(event)
                await event_queue.put(event)
        except Exception:
            logger.exception("agent task error user=%s", user_id[:8])
        finally:
            await event_queue.put(None)  # sentinel

    agent_task = asyncio.create_task(_run_agent())

    async def stream_events() -> AsyncIterator[str]:
        yield ": " + (" " * 2046) + "\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(event_queue.get()),
                        timeout=_SSE_WATCHDOG_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "SSE watchdog timeout user=%s conv=%s — closing client stream; agent continues in background",
                        user_id[:8],
                        payload.conversation_id or "new",
                    )
                    yield _format_sse(
                        "error",
                        {"message": "Response timed out. Please try again.", "recoverable": True},
                    )
                    break
                if event is None:
                    break
                chunk = _format_sse(event_name=event["event"], data=event["data"])
                yield chunk
                if event.get("event") == "token":
                    await asyncio.sleep(0.05)
        except (GeneratorExit, asyncio.CancelledError):
            # Client disconnected — agent_task keeps running independently.
            logger.info("client disconnected, agent continues in background user=%s", user_id[:8])
            return

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


@router.get("/documents/{document_id}/pdf")
async def get_document_pdf(
    document_id: str,
    current_user: CurrentUser,
    container: Annotated[AppContainer, Depends(get_container)],
) -> Response:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_id must be a valid UUID",
        )

    async with container.session_factory() as db:
        try:
            document = await files_service.get_document(db, current_user.id, doc_uuid)
        except files_service.FilesError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
            )

    key = document.source_s3_key
    try:
        data = await container.s3.download_bytes(key)
    except Exception as e:
        logger.exception("Failed to download document %s from S3", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage error: {e}",
        ) from e

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{document_id}.pdf"'},
    )


@router.get("/documents", response_model=ListFolderDocumentsResponse)
async def list_folder_documents(
    current_user: CurrentUser,
    folder_id: str = Query(..., min_length=1),
    repo: ChatRepository = Depends(get_chat_repo),
) -> ListFolderDocumentsResponse:
    try:
        uuid.UUID(folder_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="folder_id must be a valid UUID",
        )

    user_id = str(current_user.id)
    docs = await repo.get_folder_documents(user_id=user_id, folder_id=folder_id)
    return ListFolderDocumentsResponse(
        documents=[
            FolderDocumentRead(id=d.document_id, name=d.name, page_count=d.page_count)
            for d in docs
        ]
    )


@router.get("/conversations", response_model=ListConversationsResponse)
async def list_conversations(
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
    repo: ChatRepository = Depends(get_chat_repo),
    tests_service: TestSessionService = Depends(_get_test_session_service),
    folder_id: str | None = Query(default=None),
    test_session_id: str | None = Query(default=None),
    question_id: str | None = Query(default=None),
    lesson_id: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    feedback_note_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ListConversationsResponse:
    if folder_id is not None:
        try:
            uuid.UUID(folder_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="folder_id must be a valid UUID",
            )

    if lesson_id is not None and test_session_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lesson_id cannot be combined with test session scope.",
        )

    scoped_ts, scoped_q = await resolve_practice_scope_params(
        folder_id,
        test_session_id,
        question_id,
        current_user,
        tests_service,
        scope_type=scope_type,
    )
    scoped_lesson_id = await resolve_lesson_scope_param(
        folder_id,
        lesson_id,
        current_user,
        container.session_factory,
    )

    user_id = str(current_user.id)
    rows = await repo.list_conversations(
        user_id=user_id,
        folder_id=folder_id,
        limit=limit,
        offset=offset,
        test_session_id=scoped_ts,
        question_id=scoped_q,
        lesson_id=scoped_lesson_id,
        scope_type=scope_type,
        feedback_note_id=feedback_note_id,
    )
    conversations = [ConversationSummary(**row) for row in rows]
    return ListConversationsResponse(
        conversations=conversations, has_more=len(conversations) == limit
    )


@router.get(
    "/conversations/{conversation_id}/messages", response_model=GetMessagesResponse
)
async def get_conversation_messages(
    current_user: CurrentUser,
    conversation_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    repo: ChatRepository = Depends(get_chat_repo),
    container: AppContainer = Depends(get_container),
) -> GetMessagesResponse:
    user_id = str(current_user.id)
    max_messages = container.settings.chat.max_history_messages
    if limit > max_messages:
        limit = max_messages

    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    messages, has_more, next_cursor = await repo.get_active_path_messages(
        conversation_id=conversation_id,
        roles=[MessageRole.USER, MessageRole.ASSISTANT],
        cursor=cursor,
        limit=limit,
    )

    # Batch fetch sibling counts + positions (single method instead of N+1)
    sibling_info = await repo.get_sibling_info_batch(
        [m.id for m in messages], conversation_id
    )

    serialized: list[MessageSchema] = []
    for message in messages:
        image_urls: list[str] = []
        for key in message.metadata.get("image_s3_keys", []):
            try:
                url = await container.s3.presigned_get_url(key)
                image_urls.append(url)
            except Exception:
                logger.warning("Failed to generate presigned URL for key=%s", key)

        # Build attachment schemas with presigned URLs for downloadable files.
        attachment_schemas: list[AttachmentSchema] = []
        for att_meta in message.metadata.get("attachments", []):
            att_url: str | None = None
            s3_key = att_meta.get("s3_key")
            if s3_key:
                try:
                    att_url = await container.s3.presigned_get_url(s3_key)
                except Exception:
                    logger.warning(
                        "Failed to generate presigned URL for attachment key=%s", s3_key
                    )
            attachment_schemas.append(
                AttachmentSchema(
                    filename=att_meta.get("filename", ""),
                    mime_type=att_meta.get("mime_type", ""),
                    type=att_meta.get("type", ""),
                    url=att_url,
                )
            )

        serialized.append(
            MessageSchema(
                id=message.id,
                role=message.role.value,
                content=message.content,
                metadata=message.metadata,
                citations=message.metadata.get("citations", []),
                images=image_urls,
                attachments=attachment_schemas,
                created_at=message.created_at,
                parent_id=message.parent_id,
                sibling_count=sibling_info.get(message.id, (1, 1))[0],
                version_index=sibling_info.get(message.id, (1, message.version_index))[1],
            )
        )

    return GetMessagesResponse(
        messages=serialized, has_more=has_more, next_cursor=next_cursor
    )


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser,
    repo: ChatRepository = Depends(get_chat_repo),
) -> Response:
    user_id = str(current_user.id)
    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    deleted = await repo.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/conversations/{conversation_id}/title", status_code=status.HTTP_204_NO_CONTENT
)
async def rename_conversation_title(
    conversation_id: str,
    body: RenameTitleRequest,
    current_user: CurrentUser,
    repo: ChatRepository = Depends(get_chat_repo),
) -> Response:
    user_id = str(current_user.id)
    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    await repo.update_conversation_title(conversation_id, body.title)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _find_active_path_head(
    repo: ChatRepository,
    start_id: str | None,
    conversation_id: str,
    active_path: list[str],
) -> list[str]:
    """Walk up from *start_id* through parent chain to find an ancestor in *active_path*.

    Returns the portion of active_path up to and including that ancestor.
    Returns ``[]`` if no ancestor is found or *start_id* is None.
    """
    if not start_id:
        return []
    active_set = set(active_path)
    current_id: str | None = start_id
    while current_id:
        if current_id in active_set:
            idx = active_path.index(current_id)
            return active_path[: idx + 1]
        msg = await repo.get_message(current_id, conversation_id)
        if msg is None:
            break
        current_id = msg.parent_id
    return []


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_message(
    conversation_id: str,
    message_id: str,
    body: RegenerateRequest,
    current_user: CurrentUser,
    request: Request,
    agent: DocumentChatAgent = Depends(get_chat_agent),
    repo: ChatRepository = Depends(get_chat_repo),
    container: AppContainer = Depends(get_container),
) -> StreamingResponse:
    """Create a new branch from *message_id* and re-run the agent.

    If *message_id* is a user message (edit), a new sibling user message is
    created with the same parent_id. If it is an assistant message (regenerate),
    the agent is re-run from the parent user message. Messages are never deleted;
    instead a new branch is created and active_path is updated.
    """
    user_id = str(current_user.id)

    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    try:
        uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid message ID. Please refresh the page and try again.",
        )

    target = await repo.get_message(message_id, conversation_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found."
        )

    active_path = conversation.active_path or []
    target_role = target.role.value

    if target.role == MessageRole.USER:
        # --- User edit: create a new sibling user message ---
        replay_content = body.message or target.content
        branch_parent_id = target.parent_id  # same parent as original

        next_vi = await repo.get_next_version_index(
            branch_parent_id, conversation_id, role=MessageRole.USER.value
        )
        new_user_id = str(uuid.uuid4())
        new_user_msg = Message(
            id=new_user_id,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=replay_content,
            metadata=target.metadata,
        )
        await repo.save_message(
            new_user_msg, parent_id=branch_parent_id, version_index=next_vi
        )

        # Truncate active_path: keep everything before the original user message,
        # then append the new user message.
        if message_id in active_path:
            idx = active_path.index(message_id)
            new_active_path = active_path[:idx] + [new_user_id]
        elif branch_parent_id and branch_parent_id in active_path:
            idx = active_path.index(branch_parent_id)
            new_active_path = active_path[: idx + 1] + [new_user_id]
        else:
            head = await _find_active_path_head(
                repo, branch_parent_id, conversation_id, active_path
            )
            new_active_path = head + [new_user_id]
        await repo.update_active_path(conversation_id, new_active_path)

        # Agent will re-run; user message already saved above — tell agent to skip.
        agent_replay_content = replay_content
        agent_parent_id = new_user_id
        regenerated_user_message_id = new_user_id
        agent_skip_user_save = True

    elif target.role == MessageRole.ASSISTANT:
        # --- Assistant regenerate: re-run from parent user message ---
        replay_parent_id = target.parent_id
        if replay_parent_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No parent user message found for this assistant response.",
            )

        parent_msg = await repo.get_message(replay_parent_id, conversation_id)
        if parent_msg is None or parent_msg.role != MessageRole.USER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No user message found before this assistant response.",
            )

        agent_replay_content = body.message or parent_msg.content

        # Truncate active_path before the assistant message (keep up to parent user).
        if message_id in active_path:
            idx = active_path.index(message_id)
            new_active_path = active_path[:idx]
        elif replay_parent_id in active_path:
            idx = active_path.index(replay_parent_id)
            new_active_path = active_path[: idx + 1]
        else:
            new_active_path = await _find_active_path_head(
                repo, replay_parent_id, conversation_id, active_path
            )
        await repo.update_active_path(conversation_id, new_active_path)
        # The parent user message is already on active_path; agent saves
        # the new assistant message as its child.
        agent_parent_id = replay_parent_id
        regenerated_user_message_id = replay_parent_id
        agent_skip_user_save = True
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Can only regenerate from a user or assistant message.",
        )

    # Re-fetch scope context so the regenerated response has the same context.
    regen_lesson_content: str | None = None
    regen_feynman_history: str | None = None
    regen_practice_question: str | None = None
    regen_current_block_info: str | None = None

    if conversation.lesson_id:
        regen_lesson_content, regen_feynman_history = await fetch_lesson_context(
            session_factory=container.session_factory,
            lesson_id=conversation.lesson_id,
            user_id=user_id,
        )
        if body.current_block_id:
            regen_current_block_info = await fetch_current_block_info(
                session_factory=container.session_factory,
                block_id=body.current_block_id,
            )
    elif conversation.question_id:
        regen_practice_question = await fetch_practice_question_text(
            session_factory=container.session_factory,
            question_id=conversation.question_id,
        )

    regen_answer_context: str | None = None
    if conversation.question_id and conversation.test_session_id:
        regen_answer_context = await fetch_answer_context(
            session_factory=container.session_factory,
            test_session_id=str(conversation.test_session_id),
            question_id=str(conversation.question_id),
            scope_type=conversation.scope_type,
            feedback_note_id=str(conversation.feedback_note_id) if conversation.feedback_note_id else None,
        )

    regen_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    regenerate_activity_logged = False

    def _log_regenerate_activity(event: dict[str, Any]) -> None:
        nonlocal regenerate_activity_logged
        if event.get("event") != "message_complete" or regenerate_activity_logged:
            return
        data = event.get("data")
        data = data if isinstance(data, dict) else {}
        assistant_message = str(data.get("content") or "")
        assistant_message_id = data.get("message_id")
        citations = data.get("citations")
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="chat_message_regenerated",
                event_group="chat",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="conversation",
                entity_id=_uuid_or_none(conversation_id),
                folder_id=_uuid_or_none(conversation.folder_id),
                lesson_id=_uuid_or_none(conversation.lesson_id),
                test_session_id=_uuid_or_none(conversation.test_session_id),
                metadata={
                    "conversation_id": conversation_id,
                    "target_message_id": message_id,
                    "target_role": target_role,
                    "user_message_id": regenerated_user_message_id,
                    "assistant_message_id": str(assistant_message_id)
                    if assistant_message_id
                    else None,
                    "message_length": len(agent_replay_content or ""),
                    "assistant_message_length": len(assistant_message),
                    "citation_count": len(citations)
                    if isinstance(citations, list)
                    else 0,
                    "edited_user_message": target.role == MessageRole.USER
                    and bool(body.message),
                },
                replay_payload=_chat_replay_payload(
                    user_message=agent_replay_content or "",
                    assistant_message=assistant_message,
                    conversation_id=conversation_id,
                    user_message_id=regenerated_user_message_id,
                    assistant_message_id=assistant_message_id,
                ),
            ),
        )
        regenerate_activity_logged = True

    async def _run_regen_agent() -> None:
        try:
            await asyncio.sleep(0)
            async for event in agent.handle_message(
                user_id=user_id,
                conversation_id=conversation_id,
                folder_id=conversation.folder_id,
                message=agent_replay_content,
                current_document_id=body.current_document_id,
                current_page=body.current_page,
                total_pages=body.total_pages,
                model=body.model,
                reasoning=body.reasoning,
                images=body.images or [],
                user_citations=body.citations or [],
                test_session_id=conversation.test_session_id,
                question_id=conversation.question_id,
                scope_type=conversation.scope_type,
                feedback_note_id=str(conversation.feedback_note_id) if conversation.feedback_note_id else None,
                attachments=body.attachments or [],
                lesson_id=conversation.lesson_id,
                lesson_content=regen_lesson_content,
                feynman_history_text=regen_feynman_history,
                practice_question_text=regen_practice_question,
                answer_context_text=regen_answer_context,
                current_block_info=regen_current_block_info,
                inline_quiz_answers=body.inline_quiz_answers or None,
                parent_id=agent_parent_id,
                skip_user_save=agent_skip_user_save,
            ):
                _log_regenerate_activity(event)
                await regen_queue.put(event)
        except Exception:
            logger.exception("regenerate agent task error user=%s", user_id[:8])
        finally:
            await regen_queue.put(None)

    regen_task = asyncio.create_task(_run_regen_agent())

    async def stream_events() -> AsyncIterator[str]:
        yield ": " + (" " * 2046) + "\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(regen_queue.get()),
                        timeout=_SSE_WATCHDOG_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "SSE watchdog timeout (regenerate) user=%s conv=%s — closing client stream; agent continues in background",
                        user_id[:8],
                        conversation_id,
                    )
                    yield _format_sse(
                        "error",
                        {"message": "Response timed out. Please try again.", "recoverable": True},
                    )
                    break
                if event is None:
                    break
                chunk = _format_sse(event_name=event["event"], data=event["data"])
                yield chunk
                if event.get("event") == "token":
                    await asyncio.sleep(0.05)
        except (GeneratorExit, asyncio.CancelledError):
            logger.info("client disconnected during regenerate, agent continues user=%s", user_id[:8])
            return

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


@router.post("/conversations/{conversation_id}/switch-branch")
async def switch_branch(
    conversation_id: str,
    body: SwitchBranchRequest,
    current_user: CurrentUser,
    request: Request,
    repo: ChatRepository = Depends(get_chat_repo),
    container: AppContainer = Depends(get_container),
) -> SwitchBranchResponse:
    """Switch to a sibling branch (next/prev) and return the new active path + messages."""
    user_id = str(current_user.id)

    # Step 1: fetch conversation + siblings in parallel (2 calls → concurrent)
    conv_task = repo.get_conversation(conversation_id)
    siblings_task = repo.get_siblings(body.message_id, conversation_id)
    conversation, siblings = await asyncio.gather(conv_task, siblings_task)

    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )
    if not siblings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No siblings found.",
        )

    # Find current position among siblings (also gives us the target message)
    current_idx: int | None = None
    target = None
    for i, sib in enumerate(siblings):
        if sib.id == body.message_id:
            current_idx = i
            target = sib
            break

    if current_idx is None or target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message not found among siblings.",
        )

    # Compute new index based on direction
    if body.direction == "next":
        new_idx = current_idx + 1
    else:  # "prev"
        new_idx = current_idx - 1

    if new_idx < 0 or new_idx >= len(siblings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No more branches in that direction.",
        )

    new_sibling = siblings[new_idx]
    old_active_path = conversation.active_path or []

    # Step 2: walk the subtree (single recursive CTE)
    subtree_path = await repo.get_subtree_path(
        new_sibling.id, conversation_id, old_active_path
    )

    # Build new active_path
    if body.message_id in old_active_path:
        idx = old_active_path.index(body.message_id)
        head = old_active_path[:idx]
    elif target.parent_id and target.parent_id in old_active_path:
        parent_idx = old_active_path.index(target.parent_id)
        head = old_active_path[: parent_idx + 1]
    else:
        head = []

    new_active_path = head + subtree_path

    # Step 3: update active_path + fetch messages in parallel
    update_task = repo.update_active_path(conversation_id, new_active_path)
    messages_task = repo.get_messages_batch(subtree_path, conversation_id)
    _, messages_by_id = await asyncio.gather(update_task, messages_task)

    visible_ids = [
        mid for mid in subtree_path
        if mid in messages_by_id
        and messages_by_id[mid].role in (MessageRole.USER, MessageRole.ASSISTANT)
    ]

    # Step 4: fetch sibling counts + positions
    sibling_info = await repo.get_sibling_info_batch(visible_ids, conversation_id)

    # Collect all S3 keys upfront, then fetch presigned URLs concurrently.
    all_s3_tasks: list[tuple[str, str]] = []  # (mid, s3_key)
    for mid in visible_ids:
        msg = messages_by_id[mid]
        for key in msg.metadata.get("image_s3_keys", []):
            all_s3_tasks.append((f"img:{mid}:{key}", key))
        for att_meta in msg.metadata.get("attachments", []):
            s3_key = att_meta.get("s3_key")
            if s3_key:
                all_s3_tasks.append((f"att:{mid}:{s3_key}", s3_key))

    async def _safe_presign(key: str) -> str | None:
        try:
            return await container.s3.presigned_get_url(key)
        except Exception:
            logger.warning("Failed to generate presigned URL for key=%s", key)
            return None

    presigned_results = await asyncio.gather(
        *[_safe_presign(s3_key) for _, s3_key in all_s3_tasks]
    ) if all_s3_tasks else []

    presigned_map: dict[str, str | None] = {
        tag: url for (tag, _), url in zip(all_s3_tasks, presigned_results)
    }

    tail_messages: list[MessageSchema] = []
    for mid in visible_ids:
        msg = messages_by_id[mid]

        image_urls: list[str] = [
            presigned_map[f"img:{mid}:{key}"]
            for key in msg.metadata.get("image_s3_keys", [])
            if presigned_map.get(f"img:{mid}:{key}")
        ]

        attachment_schemas: list[AttachmentSchema] = []
        for att_meta in msg.metadata.get("attachments", []):
            s3_key = att_meta.get("s3_key")
            att_url = presigned_map.get(f"att:{mid}:{s3_key}") if s3_key else None
            attachment_schemas.append(
                AttachmentSchema(
                    filename=att_meta.get("filename", ""),
                    mime_type=att_meta.get("mime_type", ""),
                    type=att_meta.get("type", ""),
                    url=att_url,
                )
            )

        tail_messages.append(
            MessageSchema(
                id=msg.id,
                role=msg.role.value,
                content=msg.content,
                metadata=msg.metadata,
                citations=msg.metadata.get("citations", []),
                images=image_urls,
                attachments=attachment_schemas,
                created_at=msg.created_at,
                parent_id=msg.parent_id,
                sibling_count=sibling_info.get(msg.id, (1, 1))[0],
                version_index=sibling_info.get(msg.id, (1, msg.version_index))[1],
            )
        )

    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="chat_branch_switched",
            event_group="chat",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="conversation",
            entity_id=_uuid_or_none(conversation_id),
            folder_id=_uuid_or_none(conversation.folder_id),
            lesson_id=_uuid_or_none(conversation.lesson_id),
            test_session_id=_uuid_or_none(conversation.test_session_id),
            metadata={
                "conversation_id": conversation_id,
                "direction": body.direction,
                "from_message_id": body.message_id,
                "to_message_id": new_sibling.id,
                "sibling_count": len(siblings),
            },
            replay_payload=_chat_action_replay_payload(
                title="Branch switched",
                value=f"Switched branch {body.direction}",
                refs={
                    "conversation_id": conversation_id,
                    "from_message_id": body.message_id,
                    "to_message_id": new_sibling.id,
                },
            ),
        ),
    )

    return SwitchBranchResponse(
        active_path=new_active_path,
        messages=tail_messages,
    )


@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/siblings",
    response_model=GetSiblingsResponse,
)
async def get_message_siblings(
    conversation_id: str,
    message_id: str,
    current_user: CurrentUser,
    repo: ChatRepository = Depends(get_chat_repo),
) -> GetSiblingsResponse:
    """Return all sibling messages (same parent, same role) for branch navigation."""
    user_id = str(current_user.id)

    try:
        uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid message ID.",
        )

    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    siblings = await repo.get_siblings(message_id, conversation_id)
    return GetSiblingsResponse(
        siblings=[
            SiblingSchema(
                id=s.id,
                role=s.role.value,
                content=s.content,
                metadata=s.metadata,
                created_at=s.created_at.isoformat() if s.created_at else None,
                parent_id=s.parent_id,
                version_index=idx + 1,  # 1-based position among siblings
            )
            for idx, s in enumerate(siblings)
        ]
    )


@router.post(
    "/conversations/{conversation_id}/update-active-path",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_active_path(
    conversation_id: str,
    body: UpdateActivePathRequest,
    current_user: CurrentUser,
    repo: ChatRepository = Depends(get_chat_repo),
) -> Response:
    """Fire-and-forget active_path update for optimistic frontend branch switching."""
    user_id = str(current_user.id)
    conversation = await repo.get_conversation(conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )

    await repo.update_active_path(conversation_id, body.active_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _format_sse(event_name: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


@router.get("/available-models", response_model=AvailableModelsResponse)
async def get_available_models(
    container: AppContainer = Depends(get_container),
) -> dict:
    llm = container.settings.llm
    reasoning_levels = [
        level for level in llm.reasoning_params_map.keys() if level != "default"
    ]
    return {
        "models": list(llm.model_id_map.keys()),
        "reasoning_levels": reasoning_levels,
    }
