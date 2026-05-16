"""Learning API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request as FastAPIRequest, UploadFile, status

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_container, get_db
from src.activity.service import ActivityEventInput, log_activity_from_request
from src.learning.results_service import LessonResultsService
from src.learning.schemas import (
    CompleteStepRequest,
    CompleteStepResponse,
    FeynmanBlockRead,
    LessonBlockSchema,
    LessonDetailRead,
    LessonListSchema,
    LessonProgressRead,
    LessonResultRead,
    LessonSchema,
    LessonUploadResponse,
    ParseFeynmanResponse,
    RoadmapContextRead,
)
from src.learning.service import LearningService
from src.runtime import AppContainer

router = APIRouter(prefix="/learning", tags=["learning"])


def _lesson_opened_metadata(
    *,
    lesson: Any,
    lesson_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    block_count: int,
    feynman_block_count: int,
    has_progress: bool,
    has_roadmap_context: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "block_count": block_count,
        "feynman_block_count": feynman_block_count,
        "has_progress": has_progress,
        "has_roadmap_context": has_roadmap_context,
        "lesson_id": str(lesson_id),
    }
    lesson_name = getattr(lesson, "name", None)
    if lesson_name:
        metadata["lesson_name"] = str(lesson_name)
    if folder_id is not None:
        metadata["folder_id"] = str(folder_id)
    return metadata


def _lesson_opened_replay_payload(
    *,
    lesson: Any,
    lesson_id: uuid.UUID,
    folder_id: uuid.UUID | None,
) -> dict[str, Any]:
    refs: dict[str, str] = {"lesson_id": str(lesson_id)}
    if folder_id is not None:
        refs["folder_id"] = str(folder_id)

    lesson_name = getattr(lesson, "name", None)
    items: list[dict[str, Any]] = []
    if lesson_name:
        items.append(
            {
                "kind": "lesson",
                "title": "Lesson",
                "text": str(lesson_name),
            }
        )

    return {"schema_version": 1, "items": items, "refs": refs}


def get_learning_service(
    container: AppContainer = Depends(get_container),
) -> LearningService:
    return LearningService(session_factory=container.session_factory)


async def get_results_service(
    request: FastAPIRequest,
    container: AppContainer = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> LessonResultsService:
    return LessonResultsService(
        learning_service=LearningService(session_factory=container.session_factory),
        usage_service=getattr(request.app.state, "usage_service", None),
        db=db,
    )


@router.post(
    "/lessons/upload",
    response_model=LessonUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a .md lesson file and parse it into blocks",
)
async def upload_lesson(
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(...)],
    service: LearningService = Depends(get_learning_service),
    name: Annotated[str | None, Form()] = None,
) -> LessonUploadResponse:
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .md files are accepted",
        )

    raw = await file.read()
    content = raw.decode("utf-8")

    lesson_name = name or file.filename.removesuffix(".md")
    lesson, blocks = await service.upload_lesson(current_user.id, lesson_name, content)

    return LessonUploadResponse(
        lesson=LessonSchema.model_validate(lesson),
        blocks=[LessonBlockSchema.model_validate(b) for b in blocks],
        num_blocks=len(blocks),
    )


@router.get("/lessons", response_model=list[LessonListSchema])
async def list_lessons(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    service: LearningService = Depends(get_learning_service),
    shared: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[LessonListSchema]:
    rows = await service.list_lessons(
        current_user.id, include_shared=shared, limit=limit, offset=offset, session=db
    )
    return [LessonListSchema(**row) for row in rows]


@router.get("/lessons/last-accessed", response_model=list[LessonListSchema])
async def list_last_accessed_lessons(
    current_user: CurrentUser,
    folder_id: Annotated[uuid.UUID, Query(...)],
    db: AsyncSession = Depends(get_db),
    service: LearningService = Depends(get_learning_service),
) -> list[LessonListSchema]:
    rows = await service.list_last_accessed_lessons(
        current_user.id,
        folder_id=folder_id,
        session=db,
    )
    return [LessonListSchema(**row) for row in rows]


@router.get("/lessons/{lesson_id}", response_model=LessonDetailRead)
async def get_lesson(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    db: AsyncSession = Depends(get_db),
    service: LearningService = Depends(get_learning_service),
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
) -> LessonDetailRead:
    detail = await service.get_lesson_detail(
        lesson_id, current_user.id, folder_id=folder_id, session=db
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found"
        )

    lesson, blocks, feynman_blocks, progress, roadmap_ctx = detail
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="lesson_opened",
            event_group="lesson",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="lesson",
            entity_id=lesson_id,
            folder_id=folder_id,
            lesson_id=lesson_id,
            metadata=_lesson_opened_metadata(
                lesson=lesson,
                lesson_id=lesson_id,
                folder_id=folder_id,
                block_count=len(blocks),
                feynman_block_count=len(feynman_blocks),
                has_progress=progress is not None,
                has_roadmap_context=roadmap_ctx is not None,
            ),
            replay_payload=_lesson_opened_replay_payload(
                lesson=lesson,
                lesson_id=lesson_id,
                folder_id=folder_id,
            ),
        ),
    )

    return LessonDetailRead(
        lesson=LessonSchema.model_validate(lesson),
        blocks=[LessonBlockSchema.model_validate(b) for b in blocks],
        feynman_blocks=[FeynmanBlockRead.model_validate(fb) for fb in feynman_blocks],
        progress=LessonProgressRead.model_validate(progress) if progress else None,
        roadmap_context=RoadmapContextRead(**roadmap_ctx) if roadmap_ctx else None,
    )


@router.delete("/lessons/{lesson_id}/delete", response_model=LessonDetailRead)
async def delete_lesson(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(get_learning_service),
) -> LessonDetailRead:
    lesson = await service.delete_lesson(lesson_id, current_user.id)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found"
        )
    blocks = await service.get_lesson_blocks(lesson_id)
    return LessonDetailRead(
        lesson=LessonSchema.model_validate(lesson),
        blocks=[LessonBlockSchema.model_validate(b) for b in blocks],
        feynman_blocks=[
            FeynmanBlockRead.model_validate(fb) for fb in lesson.feynman_blocks
        ],
    )


@router.post("/lessons/{lesson_id}/parse-feynman", response_model=ParseFeynmanResponse)
async def parse_feynman(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(get_learning_service),
) -> ParseFeynmanResponse:
    blocks = await service.parse_and_store_feynman_blocks(lesson_id, current_user.id)
    return ParseFeynmanResponse(
        count=len(blocks),
        blocks=[FeynmanBlockRead.model_validate(b) for b in blocks],
    )


@router.get("/feynman/{feynman_block_id}", response_model=FeynmanBlockRead)
async def get_feynman_block(
    feynman_block_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(get_learning_service),
) -> FeynmanBlockRead:
    block = await service.get_feynman_block(feynman_block_id, current_user.id)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feynman block not found"
        )
    return FeynmanBlockRead.model_validate(block)


@router.get("/lessons/{lesson_id}/progress", response_model=LessonProgressRead)
async def get_lesson_progress(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(get_learning_service),
) -> LessonProgressRead:
    progress = await service.get_lesson_progress(lesson_id, current_user.id)
    if progress is None:
        return LessonProgressRead(
            lesson_id=lesson_id,
            stars=0,
            updated_at=datetime.now(timezone.utc),
        )
    return LessonProgressRead.model_validate(progress)


@router.post(
    "/lessons/{lesson_id}/star-reward-shown",
    response_model=LessonProgressRead,
)
async def mark_star_reward_shown(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: LearningService = Depends(get_learning_service),
) -> LessonProgressRead:
    progress = await service.mark_star_reward_shown(lesson_id, current_user.id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson progress not found",
        )
    return LessonProgressRead.model_validate(progress)


@router.post("/lessons/{lesson_id}/complete-step", response_model=CompleteStepResponse)
async def complete_step(
    lesson_id: uuid.UUID,
    body: CompleteStepRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: LearningService = Depends(get_learning_service),
) -> CompleteStepResponse:
    try:
        stars_eval, rp_info = await service.complete_step(
            lesson_id,
            current_user.id,
            body.step,
        )
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="lesson_step_completed",
                event_group="lesson",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="lesson",
                entity_id=lesson_id,
                lesson_id=lesson_id,
                metadata={
                    "step": body.step,
                    "stars": stars_eval.stars,
                    "study_star": stars_eval.study,
                    "feynman_star": stars_eval.feynman,
                    "test_star": stars_eval.test,
                    "roadmap_progress": rp_info.get("progress"),
                    "mastery": rp_info.get("mastery"),
                    "confidence": rp_info.get("confidence"),
                },
            ),
        )
        return CompleteStepResponse(
            stars=stars_eval.stars,
            study_star=stars_eval.study,
            feynman_star=stars_eval.feynman,
            test_star=stars_eval.test,
            roadmap_progress=rp_info.get("progress"),
            mastery=rp_info.get("mastery"),
            confidence=rp_info.get("confidence"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/lessons/{lesson_id}/reset")
async def reset_lesson(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: LearningService = Depends(get_learning_service),
) -> dict:
    """Fully reset a lesson: clear sessions, stars, evidence, and mastery."""
    await service.reset_lesson(lesson_id, current_user.id)
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="lesson_reset",
            event_group="lesson",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="lesson",
            entity_id=lesson_id,
            lesson_id=lesson_id,
        ),
    )
    return {"ok": True}


@router.get("/lessons/{lesson_id}/results", response_model=LessonResultRead)
async def get_lesson_results(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    learning_service: LearningService = Depends(get_learning_service),
    results_service: LessonResultsService = Depends(get_results_service),
) -> LessonResultRead:
    lesson = await learning_service.get_lesson(lesson_id, current_user.id)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found"
        )
    return await results_service.get_lesson_results(lesson_id, current_user.id)
