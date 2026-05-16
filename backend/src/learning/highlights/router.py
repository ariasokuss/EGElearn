"""FastAPI routes for lesson highlights/notes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import CurrentUser, get_container
from src.learning.highlights.schemas import HighlightCreate, HighlightPatch, HighlightRead
from src.learning.highlights.service import HighlightService
from src.runtime import AppContainer

router = APIRouter(prefix="/learning", tags=["highlights"])


def get_highlight_service(
    container: AppContainer = Depends(get_container),
) -> HighlightService:
    return HighlightService(session_factory=container.session_factory)


@router.post(
    "/lessons/{lesson_id}/highlights",
    response_model=HighlightRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_highlight(
    lesson_id: uuid.UUID,
    body: HighlightCreate,
    current_user: CurrentUser,
    service: HighlightService = Depends(get_highlight_service),
) -> HighlightRead:
    highlight = await service.create(
        user_id=current_user.id,
        lesson_id=lesson_id,
        text=body.text,
        comment=body.comment,
    )
    return HighlightRead.model_validate(highlight)


@router.get(
    "/lessons/{lesson_id}/highlights",
    response_model=list[HighlightRead],
)
async def list_lesson_highlights(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    type: str | None = None,
    service: HighlightService = Depends(get_highlight_service),
) -> list[HighlightRead]:
    highlights = await service.list_by_lesson(
        user_id=current_user.id,
        lesson_id=lesson_id,
        type_filter=type,
    )
    return [HighlightRead.model_validate(h) for h in highlights]


@router.get(
    "/highlights",
    response_model=list[HighlightRead],
)
async def list_all_highlights(
    current_user: CurrentUser,
    type: str | None = None,
    service: HighlightService = Depends(get_highlight_service),
) -> list[HighlightRead]:
    highlights = await service.list_all(
        user_id=current_user.id,
        type_filter=type,
    )
    return [HighlightRead.model_validate(h) for h in highlights]


@router.patch(
    "/highlights/{highlight_id}",
    response_model=HighlightRead,
)
async def patch_highlight(
    highlight_id: uuid.UUID,
    body: HighlightPatch,
    current_user: CurrentUser,
    service: HighlightService = Depends(get_highlight_service),
) -> HighlightRead:
    highlight = await service.patch(
        highlight_id=highlight_id,
        user_id=current_user.id,
        comment=body.comment,
    )
    if highlight is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Highlight not found")
    return HighlightRead.model_validate(highlight)


@router.delete(
    "/highlights/{highlight_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_highlight(
    highlight_id: uuid.UUID,
    current_user: CurrentUser,
    service: HighlightService = Depends(get_highlight_service),
) -> None:
    deleted = await service.delete(
        highlight_id=highlight_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Highlight not found")
