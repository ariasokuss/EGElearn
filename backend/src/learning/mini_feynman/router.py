"""Feynman API routes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.api.deps import CurrentUser, get_container
from src.activity.service import ActivityEventInput, log_activity_from_request
from src.learning.schemas import (
    FeynmanBlockRead,
    FeynmanMessageRead,
    FeynmanSessionRead,
    SessionDetailRead,
    SessionFeedbackRead,
    SessionHistoryItem,
    StartSessionResponse,
)
from src.learning.service import LearningService
from src.learning.mini_feynman.service import FeynmanPipelineService
from src.runtime import AppContainer

router = APIRouter(prefix="/mini-feynman", tags=["mini-feynman"])

FEYNMAN_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ALLOWED_ASSETS = {
    "feynman.js": FEYNMAN_ASSETS_DIR / "feynman.js",
    "feynman.css": FEYNMAN_ASSETS_DIR / "feynman.css",
}


def _event_data_from_sse_chunk(chunk: str, event_name: str) -> dict:
    if f"event: {event_name}" not in chunk:
        return {}
    for line in chunk.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            data = json.loads(line.removeprefix("data:").strip())
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _messages_replay_payload(
    messages: list[dict[str, str]], refs: dict[str, object | None] | None = None
) -> dict[str, Any]:
    items = [
        {
            "kind": "user_message" if message.get("role") == "user" else "llm_response",
            "title": "User answer" if message.get("role") == "user" else "Assistant reply",
            "text": message.get("content", ""),
        }
        for message in messages
    ]
    payload: dict[str, Any] = {"schema_version": 1, "items": items}
    clean_refs = {
        key: str(value) for key, value in (refs or {}).items() if value is not None
    }
    if clean_refs:
        payload["refs"] = clean_refs
    return payload


def _get_learning_service(
    container: AppContainer = Depends(get_container),
) -> LearningService:
    return LearningService(session_factory=container.session_factory)


def _get_feynman_service(
    request: FastAPIRequest,
    container: AppContainer = Depends(get_container),
) -> FeynmanPipelineService:
    return FeynmanPipelineService(
        learning_service=LearningService(session_factory=container.session_factory),
        prompt_manager=container.prompt_manager,
        usage_service=getattr(request.app.state, "usage_service", None),
    )


# -------------------------------------------------------------------------
# UI
# -------------------------------------------------------------------------


@router.get("", include_in_schema=False)
async def feynman_page() -> FileResponse:
    """Serve the Feynman exercise UI."""
    return FileResponse(FEYNMAN_ASSETS_DIR / "index.html")


@router.get("/assets/{asset_name}", include_in_schema=False)
async def feynman_asset(asset_name: str) -> FileResponse:
    path = ALLOWED_ASSETS.get(asset_name)
    if path is None or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    return FileResponse(path)


# -------------------------------------------------------------------------
# Session lifecycle
# -------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    feynman_block_id: uuid.UUID


class AnswerRequest(BaseModel):
    answer: str


@router.post("/session", response_model=StartSessionResponse)
async def start_session(
    body: StartSessionRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: LearningService = Depends(_get_learning_service),
) -> StartSessionResponse:
    """
    Start a feynman session for a given feynman block.
    Returns the session and the first (pre-authored) question immediately — no LLM call.
    """
    block = await service.get_feynman_block(body.feynman_block_id, current_user.id)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feynman block not found"
        )

    feynman_session = await service.create_session(
        body.feynman_block_id, current_user.id
    )

    # Store the pre-authored question as the first assistant message (iteration 1)
    first_message = await service.add_message(
        session_id=feynman_session.id,
        role="assistant",
        content=block.question,
        iteration=1,
    )
    first_message_content = str(getattr(first_message, "content", "") or "")
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="feynman_started",
            event_group="feynman",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="feynman_session",
            entity_id=feynman_session.id,
            lesson_id=block.lesson_id,
            metadata={
                "type": getattr(feynman_session, "type", "mini"),
                "feynman_block_id": str(body.feynman_block_id),
                "scope_count": len(block.scope or []),
                "point_count": len(block.points or []),
                "opening_length": len(first_message_content),
            },
            replay_payload=_messages_replay_payload(
                [{"role": "assistant", "content": first_message_content}],
                refs={
                    "session_id": feynman_session.id,
                    "feynman_block_id": body.feynman_block_id,
                    "lesson_id": block.lesson_id,
                    "assistant_message_id": getattr(first_message, "id", None),
                },
            ),
        ),
    )
    return StartSessionResponse(
        session=FeynmanSessionRead.model_validate(feynman_session),
        first_message=FeynmanMessageRead.model_validate(first_message),
        feynman_block=FeynmanBlockRead.model_validate(block),
    )


@router.get("/session/{session_id}", response_model=SessionDetailRead)
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(_get_learning_service),
) -> SessionDetailRead:
    feynman_session = await service.get_session_with_block(session_id, current_user.id)
    if feynman_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    return SessionDetailRead(
        session=feynman_session,
        feynman_block=FeynmanBlockRead.model_validate(feynman_session.feynman_block),
        messages=[
            FeynmanMessageRead.model_validate(m) for m in feynman_session.messages
        ],
    )


@router.post("/session/{session_id}/answer")
async def submit_answer(
    session_id: uuid.UUID,
    body: AnswerRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    pipeline: FeynmanPipelineService = Depends(_get_feynman_service),
) -> StreamingResponse:
    """
    Submit a student answer. Streams SSE events:
      token            {"content": "..."}
      message_complete {"role": "assistant", "content": "...", "iteration": N, "covered": [...]}
      summary          {"text": "...", "covered": [...], "points": [...], "all_covered": bool}
      error            {"detail": "..."}
    """
    if not body.answer.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Answer cannot be empty",
        )
    clean_answer = body.answer.strip()

    async def event_stream():
        answer_logged = False
        async for chunk in pipeline.handle_answer(
            session_id=session_id,
            user_answer=clean_answer,
            user_id=current_user.id,
        ):
            message_complete = _event_data_from_sse_chunk(chunk, "message_complete")
            summary = _event_data_from_sse_chunk(chunk, "summary")
            if message_complete and not answer_logged:
                assistant_reply = message_complete.get("content")
                assistant_reply = (
                    assistant_reply if isinstance(assistant_reply, str) else ""
                )
                covered = message_complete.get("covered")
                log_activity_from_request(
                    request,
                    ActivityEventInput(
                        user_id=current_user.id,
                        event_type="feynman_answered",
                        event_group="feynman",
                        request_path=request.url.path,
                        http_method=request.method,
                        entity_type="feynman_session",
                        entity_id=session_id,
                        metadata={
                            "type": "mini",
                            "status": "active",
                            "answer_length": len(clean_answer),
                            "reply_length": len(assistant_reply),
                            "covered_count": sum(1 for value in covered if value)
                            if isinstance(covered, list)
                            else None,
                            "point_count": len(covered)
                            if isinstance(covered, list)
                            else None,
                            "iteration": message_complete.get("iteration"),
                        },
                        replay_payload=_messages_replay_payload(
                            [
                                {"role": "user", "content": clean_answer},
                                {"role": "assistant", "content": assistant_reply},
                            ],
                            refs={"session_id": session_id},
                        ),
                    ),
                )
                answer_logged = True
            elif summary and not answer_logged:
                assistant_reply = summary.get("text")
                assistant_reply = (
                    assistant_reply if isinstance(assistant_reply, str) else ""
                )
                covered = summary.get("covered")
                points = summary.get("points")
                log_activity_from_request(
                    request,
                    ActivityEventInput(
                        user_id=current_user.id,
                        event_type="feynman_completed",
                        event_group="feynman",
                        request_path=request.url.path,
                        http_method=request.method,
                        entity_type="feynman_session",
                        entity_id=session_id,
                        metadata={
                            "type": "mini",
                            "answer_length": len(clean_answer),
                            "reply_length": len(assistant_reply),
                            "covered_count": sum(1 for value in covered if value)
                            if isinstance(covered, list)
                            else None,
                            "point_count": len(points)
                            if isinstance(points, list)
                            else None,
                            "all_covered": summary.get("all_covered"),
                        },
                        replay_payload=_messages_replay_payload(
                            [
                                {"role": "user", "content": clean_answer},
                                {"role": "assistant", "content": assistant_reply},
                            ],
                            refs={"session_id": session_id},
                        ),
                    ),
                )
                answer_logged = True
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/session/{session_id}/abort", response_model=FeynmanSessionRead)
async def abort_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: LearningService = Depends(_get_learning_service),
) -> FeynmanSessionRead:
    """
    Abort an active session. The session is marked as **aborted** and can no longer
    accept answers. Completed sessions are returned as-is (no double-state change).
    """
    feynman_session = await service.abort_session(session_id, current_user.id)
    if feynman_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if feynman_session.status == "aborted":
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="feynman_aborted",
                event_group="feynman",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="feynman_session",
                entity_id=session_id,
                metadata={"type": getattr(feynman_session, "type", "mini")},
            ),
        )
    return FeynmanSessionRead.model_validate(feynman_session)


# -------------------------------------------------------------------------
# History & feedback
# -------------------------------------------------------------------------


@router.get("/history/lesson/{lesson_id}", response_model=list[SessionHistoryItem])
async def get_lesson_history(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(_get_learning_service),
) -> list[SessionHistoryItem]:
    """Return mini-feynman sessions the current user has started for a given lesson."""
    sessions = await service.list_sessions_for_lesson(lesson_id, current_user.id)
    return [
        SessionHistoryItem(
            session=FeynmanSessionRead.model_validate(s),
            feynman_block=FeynmanBlockRead.model_validate(s.feynman_block),
        )
        for s in sessions
        if s.type == "mini"
    ]


@router.post("/session/lesson/{lesson_id}", response_model=StartSessionResponse)
async def start_session_by_lesson(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: LearningService = Depends(_get_learning_service),
) -> StartSessionResponse:
    """
    Start a feynman session using a **lesson UUID** instead of a feynman block UUID.
    Uses the first feynman block found for the lesson. Returns the session and the
    pre-authored opening question — no LLM call.
    """
    blocks = await service.list_feynman_blocks(lesson_id, current_user.id)
    if not blocks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feynman blocks found for this lesson",
        )
    block = blocks[0]

    feynman_session = await service.create_session(block.id, current_user.id)
    first_message = await service.add_message(
        session_id=feynman_session.id,
        role="assistant",
        content=block.question,
        iteration=1,
    )
    return StartSessionResponse(
        session=FeynmanSessionRead.model_validate(feynman_session),
        first_message=FeynmanMessageRead.model_validate(first_message),
        feynman_block=FeynmanBlockRead.model_validate(block),
    )


@router.get("/session/{session_id}/feedback", response_model=SessionFeedbackRead)
async def get_session_feedback(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(_get_learning_service),
) -> SessionFeedbackRead:
    """
    Return the feedback/results for a feynman session.
    Available for **completed** and **aborted** sessions.
    """
    feynman_session = await service.get_session_with_block(session_id, current_user.id)
    if feynman_session is None or feynman_session.type != "mini":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if feynman_session.status == "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session is still active — complete or abort it first",
        )

    # The summary is the last assistant message (set by the pipeline on completion)
    summary_text: str | None = None
    for msg in reversed(feynman_session.messages):
        if msg.role == "assistant":
            summary_text = msg.content
            break

    covered = feynman_session.covered_points or []
    points = feynman_session.feynman_block.points

    return SessionFeedbackRead(
        session=FeynmanSessionRead.model_validate(feynman_session),
        feynman_block=FeynmanBlockRead.model_validate(feynman_session.feynman_block),
        summary=summary_text,
        covered_points=covered,
        points=points,
        all_covered=bool(covered) and all(covered),
    )
