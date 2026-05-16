import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_prompt_manager, get_prompt_service
from src.prompts.manager import PromptManager
from src.prompts.schemas import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    PromptVersionRead,
)
from src.prompts.service import PromptService

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptRead])
async def list_prompts(
    service: str | None = Query(None),
    svc: PromptService = Depends(get_prompt_service),
) -> list[PromptRead]:
    return await svc.list_all(service=service)


@router.get("/{prompt_id}", response_model=PromptRead)
async def get_prompt(
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    prompt = await svc.get(prompt_id)
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )
    return prompt


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> PromptRead:
    try:
        result = await svc.create(payload)
        await pm.reload()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{prompt_id}", response_model=PromptRead)
async def update_prompt(
    prompt_id: uuid.UUID,
    payload: PromptUpdate,
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> PromptRead:
    try:
        result = await svc.update(prompt_id, payload)
        await pm.reload()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> None:
    try:
        await svc.delete(prompt_id)
        await pm.reload()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionRead])
async def list_versions(
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
) -> list[PromptVersionRead]:
    return await svc.list_versions(prompt_id)


@router.post("/{prompt_id}/restore/{version_id}", response_model=PromptRead)
async def restore_version(
    prompt_id: uuid.UUID,
    version_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> PromptRead:
    try:
        result = await svc.restore_version(prompt_id, version_id)
        await pm.reload()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
