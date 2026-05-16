import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db, get_settings
from src.config import Settings
from src.events import service as events_svc

router = APIRouter(prefix="/events", tags=["events"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get(
    "/folders/{folder_id}/documents/stream",
    summary="Stream document processing state for a folder",
)
async def stream_folder_documents(
    folder_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    settings: SettingsDep,
) -> StreamingResponse:
    return StreamingResponse(
        events_svc.stream_folder_documents(
            db,
            current_user.id,
            folder_id,
            interval_seconds=settings.processing.stream_interval_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
