"""Standard Feynman API routes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.deps import CurrentUser, get_container
from src.activity.service import ActivityEventInput, log_activity_from_request
from src.learning.feynman.service import StandardFeynmanService
from src.learning.schemas import (
    FeynmanBlockRead,
    FeynmanMessageRead,
    FeynmanSessionRead,
    SessionDetailRead,
    SessionFeedbackRead,
    SessionHistoryItem,
)
from src.learning.service import LearningService
from src.runtime import AppContainer

router = APIRouter(prefix="/feynman", tags=["feynman"])

FEYNMAN_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


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


def _summary_reply_text(summary: dict) -> str:
    text = summary.get("text")
    if isinstance(text, str):
        return text

    feedback = summary.get("feedback")
    if isinstance(feedback, str):
        return feedback
    if isinstance(feedback, list):
        parts: list[str] = []
        for item in feedback:
            if isinstance(item, dict):
                value = item.get("feedback") or item.get("text")
            else:
                value = item
            if isinstance(value, str) and value:
                parts.append(value)
        return "\n".join(parts)
    return ""


def _uuid_or_none(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


@router.get("", include_in_schema=False)
async def feynman_page() -> FileResponse:
    """Serve the standard Feynman session UI."""
    return FileResponse(FEYNMAN_ASSETS_DIR / "index.html")


def _get_learning_service(
    container: AppContainer = Depends(get_container),
) -> LearningService:
    return LearningService(session_factory=container.session_factory)


def _get_standard_service(
    request: FastAPIRequest,
    container: AppContainer = Depends(get_container),
) -> StandardFeynmanService:
    return StandardFeynmanService(
        learning_service=LearningService(session_factory=container.session_factory),
        prompt_manager=container.prompt_manager,
        usage_service=getattr(request.app.state, "usage_service", None),
    )


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class StartStandardSessionRequest(BaseModel):
    lesson_id: uuid.UUID


class AnswerRequest(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)

    @field_validator("citations")
    @classmethod
    def _validate_citations(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c and str(c).strip()]
        if len(cleaned) > 3:
            raise ValueError("At most 3 citations are allowed")
        for c in cleaned:
            if len(c) > 500:
                raise ValueError("Each citation must be at most 500 characters")
        return cleaned


@router.post("/session")
async def start_session(
    body: StartStandardSessionRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    pipeline: StandardFeynmanService = Depends(_get_standard_service),
) -> StreamingResponse:
    """
    Start a standard Feynman session for a lesson.
    Parses PART themes from the lesson markdown and streams the LLM-generated opening question.

    SSE events:
      token           {"content": "..."}
      session_started {"session_id": "...", "feynman_block_id": "...",
                       "theme_titles": [...], "theme_scores": [...]}
      error           {"detail": "..."}
    """

    async def event_stream():
        opening_chunks: list[str] = []
        async for chunk in pipeline.start_session(
            lesson_id=body.lesson_id,
            user_id=current_user.id,
        ):
            token = _event_data_from_sse_chunk(chunk, "token")
            token_content = token.get("content")
            if isinstance(token_content, str):
                opening_chunks.append(token_content)

            session_started = _event_data_from_sse_chunk(chunk, "session_started")
            if session_started:
                theme_titles = session_started.get("theme_titles")
                theme_scores = session_started.get("theme_scores")
                feynman_block_id = session_started.get("feynman_block_id")
                opening_message = "".join(opening_chunks)
                log_activity_from_request(
                    request,
                    ActivityEventInput(
                        user_id=current_user.id,
                        event_type="feynman_started",
                        event_group="feynman",
                        request_path=request.url.path,
                        http_method=request.method,
                        entity_type="feynman_session",
                        entity_id=_uuid_or_none(session_started.get("session_id")),
                        lesson_id=body.lesson_id,
                        metadata={
                            "type": "standard",
                            "feynman_block_id": str(feynman_block_id)
                            if feynman_block_id
                            else None,
                            "theme_count": len(theme_titles)
                            if isinstance(theme_titles, list)
                            else None,
                            "theme_score_count": len(theme_scores)
                            if isinstance(theme_scores, list)
                            else None,
                            "opening_length": len(opening_message),
                        },
                        replay_payload=_messages_replay_payload(
                            [{"role": "assistant", "content": opening_message}],
                            refs={
                                "session_id": session_started.get("session_id"),
                                "feynman_block_id": feynman_block_id,
                                "lesson_id": body.lesson_id,
                            },
                        ),
                    ),
                )
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    pipeline: StandardFeynmanService = Depends(_get_standard_service),
) -> StreamingResponse:
    """
    Submit a student answer. Streams SSE events:
      token            {"content": "..."}
      message_complete {"role": "assistant", "content": "...",
                        "iteration": N, "theme_scores": [...]}
      summary          {"text": "...", "theme_scores": [...], "theme_titles": [...],
                        "all_covered": bool, "feedback": "..."}
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
            user_citations=body.citations or None,
        ):
            message_complete = _event_data_from_sse_chunk(chunk, "message_complete")
            summary = _event_data_from_sse_chunk(chunk, "summary")
            if message_complete and not answer_logged:
                assistant_reply = message_complete.get("content")
                assistant_reply = (
                    assistant_reply if isinstance(assistant_reply, str) else ""
                )
                theme_scores = message_complete.get("theme_scores")
                citations = message_complete.get("citations")
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
                            "type": "standard",
                            "status": "active",
                            "answer_length": len(clean_answer),
                            "reply_length": len(assistant_reply),
                            "citation_count": len(body.citations or []),
                            "assistant_citation_count": len(citations)
                            if isinstance(citations, list)
                            else 0,
                            "theme_score_count": len(theme_scores)
                            if isinstance(theme_scores, list)
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
                assistant_reply = _summary_reply_text(summary)
                theme_scores = summary.get("theme_scores")
                feedback = summary.get("feedback")
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
                            "type": "standard",
                            "answer_length": len(clean_answer),
                            "reply_length": len(assistant_reply),
                            "citation_count": len(body.citations or []),
                            "theme_score_count": len(theme_scores)
                            if isinstance(theme_scores, list)
                            else None,
                            "feedback_count": len(feedback)
                            if isinstance(feedback, list)
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


class AbortSessionRequest(BaseModel):
    exhausted: bool = False


@router.post("/session/{session_id}/abort", response_model=FeynmanSessionRead)
async def abort_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    body: AbortSessionRequest = AbortSessionRequest(),
    pipeline: StandardFeynmanService = Depends(_get_standard_service),
) -> FeynmanSessionRead:
    """
    End an active session.

    - `exhausted=false` (default): user just exits. Uncovered themes stay null in stats.
    - `exhausted=true`: user has said everything they know. Null themes are set to 0.

    Both modes generate LLM feedback for any themes that were evaluated.
    """
    feynman_session = await pipeline.abort_session(
        session_id, current_user.id, exhausted=body.exhausted
    )
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
                metadata={
                    "type": "standard",
                    "exhausted": body.exhausted,
                    "status": feynman_session.status,
                },
            ),
        )
    return FeynmanSessionRead.model_validate(feynman_session)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


@router.get("/session/{session_id}/feedback", response_model=SessionFeedbackRead)
async def get_session_feedback(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(_get_learning_service),
) -> SessionFeedbackRead:
    """
    Return feedback for a completed or aborted standard Feynman session.
    The `summary` field contains the LLM-generated narrative feedback stored in `feedback` column.
    """
    feynman_session = await service.get_session_with_block(session_id, current_user.id)
    if feynman_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if feynman_session.status == "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session is still active — complete or abort it first",
        )

    # Determine all_covered from session data: all scored themes >= threshold (1)
    points = feynman_session.covered_points or []
    all_covered = bool(points) and all(
        isinstance(p, (int, float)) and p >= 1 for p in points
    )

    return SessionFeedbackRead(
        session=FeynmanSessionRead.model_validate(feynman_session),
        feynman_block=FeynmanBlockRead.model_validate(feynman_session.feynman_block),
        all_covered=all_covered,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get("/history/lesson/{lesson_id}", response_model=list[SessionHistoryItem])
async def get_lesson_history(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(_get_learning_service),
) -> list[SessionHistoryItem]:
    """Return all standard Feynman sessions the user has started for a given lesson."""
    sessions = await service.list_sessions_for_lesson(lesson_id, current_user.id)
    standard_sessions = [s for s in sessions if s.type == "standard"]
    return [
        SessionHistoryItem(
            session=FeynmanSessionRead.model_validate(s),
            feynman_block=FeynmanBlockRead.model_validate(s.feynman_block),
        )
        for s in standard_sessions
    ]
