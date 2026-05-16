"""Feedback Hub API endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.deps import CurrentUser, get_container
from src.learning.feedback.schemas import (
    FeedbackNoteOut,
    FeedbackSummaryOut,
    NoteAnswerOut,
    NoteAnswerRequest,
    NoteStatusUpdate,
)
from src.learning.feedback.service import FeedbackNoteService
from src.learning.feedback.models import FeedbackNote as FeedbackNoteModel
from src.runtime import AppContainer

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _get_feedback_service(
    container: AppContainer = Depends(get_container),
) -> FeedbackNoteService:
    return FeedbackNoteService(session_factory=container.session_factory)


async def _enrich_with_question_ids(
    notes: list[FeedbackNoteModel],
    session_factory: async_sessionmaker[AsyncSession],
) -> list[FeedbackNoteOut]:
    """Convert notes to schema and resolve question_id from source_answer_id."""
    from src.learning.tests.models import SessionAnswer

    answer_ids = [
        n.source_answer_id
        for n in notes
        if n.source_type == "test" and n.source_answer_id is not None
    ]

    qid_map: dict[uuid.UUID, uuid.UUID] = {}
    if answer_ids:
        async with session_factory() as session:
            stmt = select(
                SessionAnswer.id, SessionAnswer.question_id
            ).where(SessionAnswer.id.in_(answer_ids))
            rows = await session.execute(stmt)
            for aid, qid in rows:
                qid_map[aid] = qid

    result: list[FeedbackNoteOut] = []
    for n in notes:
        out = FeedbackNoteOut.model_validate(n)
        if n.source_answer_id and n.source_answer_id in qid_map:
            out.question_id = qid_map[n.source_answer_id]
        result.append(out)
    return result


@router.get("/notes", response_model=list[FeedbackNoteOut])
async def list_notes(
    current_user: CurrentUser,
    folder_id: uuid.UUID,
    service: FeedbackNoteService = Depends(_get_feedback_service),
    container: AppContainer = Depends(get_container),
    source_type: str | None = Query(None, pattern="^(test|feynman)$"),
    status: str | None = Query(None, pattern="^(see|review|complete)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[FeedbackNoteOut]:
    notes = await service.list_for_user(
        user_id=current_user.id,
        folder_id=folder_id,
        source_type=source_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return await _enrich_with_question_ids(notes, container.session_factory)


@router.get("/notes/session/{session_id}", response_model=list[FeedbackNoteOut])
async def list_notes_for_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    service: FeedbackNoteService = Depends(_get_feedback_service),
    container: AppContainer = Depends(get_container),
) -> list[FeedbackNoteOut]:
    notes = await service.list_for_session(
        user_id=current_user.id,
        source_session_id=session_id,
    )
    return await _enrich_with_question_ids(notes, container.session_factory)


@router.patch("/notes/{note_id}/status", response_model=FeedbackNoteOut)
async def update_note_status(
    note_id: uuid.UUID,
    body: NoteStatusUpdate,
    current_user: CurrentUser,
    service: FeedbackNoteService = Depends(_get_feedback_service),
    container: AppContainer = Depends(get_container),
) -> FeedbackNoteOut:
    note = await service.update_note_status(
        note_id=note_id,
        user_id=current_user.id,
        new_status=body.status,
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    enriched = await _enrich_with_question_ids([note], container.session_factory)
    return enriched[0]


@router.post("/notes/{note_id}/answer", response_model=NoteAnswerOut)
async def answer_note(
    note_id: uuid.UUID,
    body: NoteAnswerRequest,
    current_user: CurrentUser,
    service: FeedbackNoteService = Depends(_get_feedback_service),
) -> NoteAnswerOut:
    try:
        result = await service.answer_note(
            note_id=note_id,
            user_id=current_user.id,
            answer_text=body.answer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return NoteAnswerOut(**result)


@router.get("/summary", response_model=FeedbackSummaryOut)
async def get_summary(
    current_user: CurrentUser,
    folder_id: uuid.UUID,
    service: FeedbackNoteService = Depends(_get_feedback_service),
) -> FeedbackSummaryOut:
    data = await service.get_summary(user_id=current_user.id, folder_id=folder_id)
    return FeedbackSummaryOut(**data)
