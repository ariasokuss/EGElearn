from __future__ import annotations

import uuid
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.learning import models as _learning_models  # noqa: F401 — ensures all SQLAlchemy mappers are registered
from src.learning.past_paper.service import _find_cached_past_paper


def _session_factory_returning(scalar_value):
    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = scalar_value
    session.execute = AsyncMock(return_value=scalar_result)
    sf_cm = AsyncMock()
    sf_cm.__aenter__.return_value = session
    sf_cm.__aexit__.return_value = False
    sf = MagicMock(return_value=sf_cm)
    return sf, session


@pytest.mark.asyncio
async def test_canonical_lookup_returns_match():
    canonical = SimpleNamespace(
        id=uuid.uuid4(),
        is_canonical=True,
        source_pdf_sha256="abc",
        questions=[SimpleNamespace(index=0)],
    )
    sf, session = _session_factory_returning(canonical)

    result = await _find_cached_past_paper(sf, pdf_sha256="abc")

    assert result is canonical
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_canonical_lookup_returns_none_when_missing():
    sf, _session = _session_factory_returning(None)
    result = await _find_cached_past_paper(sf, pdf_sha256="missing")
    assert result is None


@pytest.mark.asyncio
async def test_canonical_lookup_skips_match_with_no_questions():
    empty_canonical = SimpleNamespace(
        id=uuid.uuid4(),
        is_canonical=True,
        source_pdf_sha256="abc",
        questions=[],
    )
    sf, _session = _session_factory_returning(empty_canonical)
    result = await _find_cached_past_paper(sf, pdf_sha256="abc")
    assert result is None
