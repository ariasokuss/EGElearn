from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.activity.schemas import ClientActivityEventIn, ClientActivityEventOut
from src.activity.service import (
    CLIENT_EVENT_TYPES,
    ActivityEventInput,
    ActivityService,
    sanitize_metadata,
)
from src.api.deps import CurrentUser

router = APIRouter(prefix="/activity", tags=["activity"])


def _client_event_group(event_type: str) -> str:
    if event_type == "chat_opened":
        return "chat"
    return "navigation"


def get_activity_service(
    request: Request,
) -> ActivityService:
    service = getattr(request.app.state, "activity_service", None)
    if service is not None:
        return service
    return ActivityService(request.app.state.container.session_factory)


@router.post(
    "/events",
    response_model=ClientActivityEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_client_event(
    body: ClientActivityEventIn,
    request: Request,
    current_user: CurrentUser,
    service: ActivityService = Depends(get_activity_service),
) -> ClientActivityEventOut:
    if body.event_type not in CLIENT_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported activity event type.",
        )
    await service.log_event(
        ActivityEventInput(
            user_id=current_user.id,
            event_type=body.event_type,
            event_group=_client_event_group(body.event_type),
            request_path=request.url.path,
            http_method=request.method,
            route_label=body.route_label,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            folder_id=body.folder_id,
            lesson_id=body.lesson_id,
            test_session_id=body.test_session_id,
            metadata=sanitize_metadata(body.metadata),
        )
    )
    return ClientActivityEventOut(ok=True)
