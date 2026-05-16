import asyncio
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db
from src.roadmap import service as roadmap_svc
from src.roadmap.progress_bus import progress_bus
from src.roadmap.schemas import (
    OptionalThemesOut,
    OptionalThemesSelectionIn,
    ProgressUpdate,
    RoadmapOut,
)

router = APIRouter(prefix="/roadmap", tags=["roadmap"])

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@router.get("/checker", include_in_schema=False)
async def roadmap_checker() -> FileResponse:
    return FileResponse(_ASSETS_DIR / "index.html")


DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/folders/{folder_id}",
    response_model=RoadmapOut,
    summary="Get the full roadmap tree with user's progress",
)
async def get_roadmap(
    folder_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> RoadmapOut:
    try:
        return await roadmap_svc.get_roadmap(db, folder_id, current_user.id)
    except roadmap_svc.RoadmapError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/folders/{folder_id}/optional-themes",
    response_model=OptionalThemesOut,
    summary="Get optional exam theme blocks for a folder (404 if none configured)",
)
async def get_optional_themes(
    folder_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,  # auth guard — optional themes are folder-level
) -> OptionalThemesOut:
    result = await roadmap_svc.resolve_optional_themes(db, folder_id)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No optional themes configured for this folder",
        )
    return result


@router.put(
    "/folders/{folder_id}/optional-themes/selection",
    summary="Save the user's optional-topic selection for this folder's optional paper",
)
async def save_optional_themes_selection(
    folder_id: uuid.UUID,
    body: OptionalThemesSelectionIn,
    db: DbDep,
    current_user: CurrentUser,
) -> dict:
    try:
        exam = await roadmap_svc.apply_optional_themes_selection(
            db, folder_id, current_user.id, body.option_ids
        )
    except roadmap_svc.RoadmapError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"exam_id": str(exam.id)}


@router.patch(
    "/nodes/{node_id}/progress",
    response_model=ProgressUpdate,
    summary="Update progress (0–100) for a lesson node",
)
async def update_progress(
    node_id: uuid.UUID,
    body: ProgressUpdate,
    db: DbDep,
    current_user: CurrentUser,
) -> ProgressUpdate:
    try:
        new_progress = await roadmap_svc.update_progress(
            db, current_user.id, node_id, body.progress
        )
        return ProgressUpdate(progress=new_progress)
    except roadmap_svc.RoadmapError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


async def _progress_stream(
    folder_id: uuid.UUID,
) -> AsyncGenerator[str, None]:
    """Yield SSE events when lesson progress/stars change for a folder."""
    q = progress_bus.subscribe(folder_id)
    yield "event: heartbeat\ndata: {}\n\n"  # immediate ping so the proxy doesn't time out
    try:
        while True:
            try:
                update = await asyncio.wait_for(q.get(), timeout=30)
                yield update.to_sse()
            except asyncio.TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"
    finally:
        progress_bus.unsubscribe(folder_id, q)


@router.get(
    "/folders/{folder_id}/progress/stream",
    summary="SSE stream of lesson progress updates for a folder",
)
async def stream_folder_progress(
    folder_id: uuid.UUID,
    current_user: CurrentUser,
) -> StreamingResponse:
    return StreamingResponse(
        _progress_stream(folder_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
