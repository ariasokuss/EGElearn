"""Bootstraps the system-owned folder that holds admin-uploaded past papers.

A single folder row, owned by no user, is created on app startup if missing.
All papers uploaded from /admin/past-papers attach to this folder so they
remain isolated from regular user libraries.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.processing.models as _processing_models  # noqa: F401 — registers ProcessingJob mapper
from src.files.models import Folder, FolderType


ADMIN_LIBRARY_FOLDER_ID: uuid.UUID = uuid.UUID(
    "00000000-0000-0000-0000-00000a574d11"
)
ADMIN_LIBRARY_NAME = "__admin_library__"


async def ensure_admin_library_folder(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        existing = (
            await session.execute(
                select(Folder).where(Folder.id == ADMIN_LIBRARY_FOLDER_ID)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        session.add(
            Folder(
                id=ADMIN_LIBRARY_FOLDER_ID,
                user_id=None,
                name=ADMIN_LIBRARY_NAME,
                type=FolderType.user,
            )
        )
        await session.commit()
