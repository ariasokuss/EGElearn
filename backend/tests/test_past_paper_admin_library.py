from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.learning.past_paper.admin_library import (
    ADMIN_LIBRARY_FOLDER_ID,
    ensure_admin_library_folder,
)


@pytest.mark.asyncio
async def test_admin_library_uuid_is_stable():
    assert isinstance(ADMIN_LIBRARY_FOLDER_ID, uuid.UUID)
    assert str(ADMIN_LIBRARY_FOLDER_ID) == "00000000-0000-0000-0000-00000a574d11"


@pytest.mark.asyncio
async def test_ensure_admin_library_folder_inserts_when_missing():
    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=scalar_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    sf_cm = AsyncMock()
    sf_cm.__aenter__.return_value = session
    sf_cm.__aexit__.return_value = False
    session_factory = MagicMock(return_value=sf_cm)

    await ensure_admin_library_folder(session_factory)

    session.add.assert_called_once()
    folder = session.add.call_args.args[0]
    assert folder.id == ADMIN_LIBRARY_FOLDER_ID
    assert folder.user_id is None
    assert folder.name == "__admin_library__"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_admin_library_folder_is_idempotent():
    session = AsyncMock()
    existing = object()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=scalar_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    sf_cm = AsyncMock()
    sf_cm.__aenter__.return_value = session
    sf_cm.__aexit__.return_value = False
    session_factory = MagicMock(return_value=sf_cm)

    await ensure_admin_library_folder(session_factory)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
