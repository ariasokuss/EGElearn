from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.auth.models import User
from src.core.db import Base
from src.files.models import Folder, FolderType
from src.processing import models as _processing_models  # noqa: F401
from src.roadmap.ege_seed import _lock_ege_seed, seed_ege_subject_folders
from src.roadmap.ege_subjects import EGE_SUBJECT_NAMES


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, Folder.__table__],
        )

    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seed_ege_subject_folders_creates_empty_shared_subjects(session_factory):
    await seed_ege_subject_folders(session_factory)

    async with session_factory() as session:
        folders = list(
            await session.scalars(select(Folder).order_by(Folder.created_at.asc()))
        )

    assert [folder.name for folder in folders] == list(EGE_SUBJECT_NAMES)
    assert all(folder.user_id is None for folder in folders)
    assert all(folder.type == FolderType.a_level for folder in folders)
    assert all(folder.pqg_service is None for folder in folders)


@pytest.mark.asyncio
async def test_seed_ege_subject_folders_is_idempotent(session_factory):
    await seed_ege_subject_folders(session_factory)
    await seed_ege_subject_folders(session_factory)

    async with session_factory() as session:
        folders = list(await session.scalars(select(Folder)))

    assert len(folders) == len(EGE_SUBJECT_NAMES)


@pytest.mark.asyncio
async def test_seed_ege_subject_folders_ignores_user_owned_and_non_ege_folders(
    session_factory,
):
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add_all(
            [
                Folder(
                    user_id=user_id,
                    name=EGE_SUBJECT_NAMES[0],
                    type=FolderType.a_level,
                ),
                Folder(
                    user_id=None,
                    name="Edexcel A-Level Economics",
                    type=FolderType.a_level,
                ),
            ]
        )
        await session.commit()

    await seed_ege_subject_folders(session_factory)

    async with session_factory() as session:
        folders = list(
            await session.scalars(select(Folder).order_by(Folder.created_at.asc()))
        )

    shared_ege_names = [
        folder.name
        for folder in folders
        if folder.user_id is None and folder.name in EGE_SUBJECT_NAMES
    ]
    assert shared_ege_names == list(EGE_SUBJECT_NAMES)
    assert sum(folder.user_id == user_id for folder in folders) == 1
    assert sum(folder.name == "Edexcel A-Level Economics" for folder in folders) == 1


@pytest.mark.asyncio
async def test_lock_ege_seed_uses_postgres_advisory_transaction_lock():
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql")
        ),
        execute=AsyncMock(),
    )

    await _lock_ege_seed(session)

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_ege_seed_skips_sqlite():
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
        execute=AsyncMock(),
    )

    await _lock_ege_seed(session)

    session.execute.assert_not_awaited()
