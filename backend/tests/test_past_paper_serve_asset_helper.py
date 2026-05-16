from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock

from src.learning.past_paper.service import serve_asset


@pytest.mark.asyncio
async def test_serve_asset_returns_bytes_and_content_type():
    s3 = AsyncMock()
    s3.download_bytes = AsyncMock(return_value=b"PNGDATA")

    pid = uuid.uuid4()
    data, ct = await serve_asset(s3, pid, "images", "diagram.png")

    s3.download_bytes.assert_awaited_once_with(
        f"past-papers/{pid}/assets/images/diagram.png"
    )
    assert data == b"PNGDATA"
    assert ct == "image/png"


@pytest.mark.asyncio
async def test_serve_asset_unknown_extension_falls_back_to_octet_stream():
    s3 = AsyncMock()
    s3.download_bytes = AsyncMock(return_value=b"x")
    data, ct = await serve_asset(s3, uuid.uuid4(), "tables", "raw.bin")
    assert data == b"x"
    assert ct == "application/octet-stream"


@pytest.mark.asyncio
async def test_serve_asset_raises_filenotfound_on_s3_error():
    s3 = AsyncMock()
    s3.download_bytes = AsyncMock(side_effect=RuntimeError("nope"))
    with pytest.raises(FileNotFoundError):
        await serve_asset(s3, uuid.uuid4(), "images", "missing.png")
