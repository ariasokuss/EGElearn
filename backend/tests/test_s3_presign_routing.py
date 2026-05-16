"""Tests for S3Client presigned-URL endpoint routing.

Locks the contract: when `public_endpoint_url` is set and differs from
`endpoint_url`, presigned URLs are generated with the public endpoint host
so the browser can reach them, while regular API calls (upload/download)
still go through the internal endpoint.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import S3Settings
from src.core.s3 import S3Client


def _make_client(public: str = "") -> S3Client:
    settings = S3Settings(
        endpoint_url="http://minio:9000",
        public_endpoint_url=public,
    )
    return S3Client(settings)


@pytest.mark.asyncio
async def test_presigned_put_uses_signing_client():
    """presigned_put_url calls generate_presigned_url on _signing_client."""
    client = _make_client()
    client._client = MagicMock()
    client._client.generate_presigned_url = AsyncMock(return_value="signed-url")

    out = await client.presigned_put_url("k", content_type="image/png")

    assert out == "signed-url"
    client._client.generate_presigned_url.assert_awaited_once()
    assert client._signing_client is client._client


@pytest.mark.asyncio
async def test_presigned_put_routes_to_public_client_when_set():
    """When public_endpoint_url is set, presigned URLs are signed by the public client."""
    client = _make_client(public="http://localhost:9000")
    client._client = MagicMock()
    client._client.generate_presigned_url = AsyncMock(return_value="internal-url")
    client._presign_client = MagicMock()
    client._presign_client.generate_presigned_url = AsyncMock(return_value="public-url")

    out = await client.presigned_put_url("k", content_type="image/png")

    assert out == "public-url"
    client._presign_client.generate_presigned_url.assert_awaited_once()
    client._client.generate_presigned_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_presigned_get_routes_to_public_client_when_set():
    client = _make_client(public="http://localhost:9000")
    client._client = MagicMock()
    client._client.generate_presigned_url = AsyncMock(return_value="internal-url")
    client._presign_client = MagicMock()
    client._presign_client.generate_presigned_url = AsyncMock(return_value="public-url")

    out = await client.presigned_get_url("k")

    assert out == "public-url"
    client._presign_client.generate_presigned_url.assert_awaited_once()
    client._client.generate_presigned_url.assert_not_awaited()


def test_signing_client_falls_back_to_main_when_public_empty():
    client = _make_client(public="")
    client._client = "main"
    assert client._signing_client == "main"


def test_signing_client_uses_presign_client_when_set():
    client = _make_client(public="http://localhost:9000")
    client._client = "main"
    client._presign_client = "presign"
    assert client._signing_client == "presign"
