from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth.models import User
from src.files import service as files_service
from src.roadmap.models import RoadmapNode


async def resolve_lesson_scope_param(
    folder_id: str | None,
    lesson_id: str | None,
    current_user: User,
    session_factory: async_sessionmaker[AsyncSession],
) -> str | None:
    if lesson_id is None:
        return None
    if lesson_id.strip() in ("", "null", "undefined"):
        return None
    if folder_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="folder_id is required when lesson_id is set.",
        )
    try:
        lid = uuid.UUID(lesson_id.strip())
        fid = uuid.UUID(folder_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lesson_id and folder_id must be valid UUIDs.",
        ) from e

    async with session_factory() as db:
        try:
            await files_service.get_folder(db, current_user.id, fid)
        except files_service.FilesError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found.",
            ) from None
        row = await db.execute(
            select(RoadmapNode.id)
            .where(
                RoadmapNode.folder_id == fid,
                RoadmapNode.lesson_id == lid,
            )
            .limit(1)
        )
        if row.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lesson not found in this folder.",
            )
    return str(lid)
