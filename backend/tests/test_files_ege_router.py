from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status

from src.files.models import Folder, FolderType
from src.learning import models as _learning_models  # noqa: F401
from src.files.router import get_ege_folders, reorder_ege_folders
from src.files.schemas import FolderReorderRequest


def _folder(
    name: str,
    *,
    folder_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Folder:
    now = datetime(2026, 5, 16, tzinfo=UTC)
    return Folder(
        id=folder_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        type=FolderType.a_level,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_get_ege_folders_filters_legacy_and_user_folders(monkeypatch):
    user_id = uuid.uuid4()
    db = object()
    shared_ege = _folder("Русский язык")
    legacy_a_level = _folder("Edexcel A-Level Economics")
    user_owned_ege = _folder("Физика", user_id=user_id)

    list_folders_by_type = AsyncMock(
        return_value=[
            (legacy_a_level, 0),
            (shared_ege, 1),
            (user_owned_ege, 2),
        ]
    )
    monkeypatch.setattr(
        "src.files.router.files_svc.list_folders_by_type",
        list_folders_by_type,
    )

    result = await get_ege_folders(db, SimpleNamespace(id=user_id))

    list_folders_by_type.assert_awaited_once_with(db, user_id, FolderType.a_level)
    assert [folder.name for folder in result] == ["Русский язык"]
    assert result[0].position == 1


@pytest.mark.asyncio
async def test_reorder_ege_folders_requires_every_ege_id(monkeypatch):
    user_id = uuid.uuid4()
    first = _folder("Русский язык")
    second = _folder("Физика")

    monkeypatch.setattr(
        "src.files.router.files_svc.list_folders_by_type",
        AsyncMock(return_value=[(first, 0), (second, 1)]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await reorder_ege_folders(
            FolderReorderRequest(folder_ids=[first.id]),
            object(),
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_reorder_ege_folders_rejects_duplicate_ege_id(monkeypatch):
    user_id = uuid.uuid4()
    first = _folder("Русский язык")
    second = _folder("Физика")

    monkeypatch.setattr(
        "src.files.router.files_svc.list_folders_by_type",
        AsyncMock(return_value=[(first, 0), (second, 1)]),
    )
    monkeypatch.setattr(
        "src.files.router.files_svc.reorder_folders",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await reorder_ege_folders(
            FolderReorderRequest(folder_ids=[first.id, second.id, first.id]),
            object(),
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_reorder_ege_folders_persists_requested_order(monkeypatch):
    user_id = uuid.uuid4()
    db = object()
    legacy_before = _folder("Edexcel A-Level Economics")
    first = _folder("Русский язык")
    legacy_between = _folder("AQA A-Level Psychology")
    second = _folder("Физика")
    legacy_after = _folder("OCR A-Level Chemistry")
    requested_ids = [second.id, first.id]

    monkeypatch.setattr(
        "src.files.router.files_svc.list_folders_by_type",
        AsyncMock(
            return_value=[
                (legacy_before, 0),
                (first, 1),
                (legacy_between, 2),
                (second, 3),
                (legacy_after, 4),
            ]
        ),
    )
    reorder_folders = AsyncMock(
        return_value=[
            (legacy_before, 0),
            (second, 1),
            (legacy_between, 2),
            (first, 3),
            (legacy_after, 4),
        ]
    )
    monkeypatch.setattr(
        "src.files.router.files_svc.reorder_folders",
        reorder_folders,
    )

    result = await reorder_ege_folders(
        FolderReorderRequest(folder_ids=requested_ids),
        db,
        SimpleNamespace(id=user_id),
    )

    reorder_folders.assert_awaited_once_with(
        db,
        user_id,
        FolderType.a_level,
        [
            legacy_before.id,
            second.id,
            legacy_between.id,
            first.id,
            legacy_after.id,
        ],
    )
    assert [folder.name for folder in result] == ["Физика", "Русский язык"]
    assert [folder.position for folder in result] == [1, 3]
