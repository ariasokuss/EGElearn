from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.learning.image_rewrite import rewrite_image_urls_to_presigned as _rewrite_image_urls_to_presigned


@pytest.fixture
def mock_s3():
    s3 = AsyncMock()
    s3.presigned_get_url = AsyncMock(
        side_effect=lambda key, **_: f"https://s3.example.com/{key}?X-Amz-Signature=abc"
    )
    return s3


@pytest.mark.asyncio
async def test_rewrites_image_url_in_context(mock_s3):
    paper_id = "3df3a66b-1d5c-4c65-8127-b68ba7ef8b30"
    context = f"Some text\n![img](/api/v1/past-papers/{paper_id}/assets/images/img-0.jpeg)\nMore text"

    result = await _rewrite_image_urls_to_presigned(context, mock_s3)

    assert "/api/v1/" not in result
    assert f"past-papers/{paper_id}/assets/images/img-0.jpeg" in result
    assert "X-Amz-Signature" in result
    mock_s3.presigned_get_url.assert_awaited_once_with(
        f"past-papers/{paper_id}/assets/images/img-0.jpeg", expires_in=3600
    )


@pytest.mark.asyncio
async def test_deduplicates_same_url(mock_s3):
    paper_id = "3df3a66b-1d5c-4c65-8127-b68ba7ef8b30"
    url = f"/api/v1/past-papers/{paper_id}/assets/images/img-5.jpeg"
    context = f"![a]({url})\n![b]({url})"

    await _rewrite_image_urls_to_presigned(context, mock_s3)

    assert mock_s3.presigned_get_url.await_count == 1


@pytest.mark.asyncio
async def test_returns_none_unchanged(mock_s3):
    assert await _rewrite_image_urls_to_presigned(None, mock_s3) is None
    mock_s3.presigned_get_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_images_skips_s3(mock_s3):
    result = await _rewrite_image_urls_to_presigned("No images here", mock_s3)
    assert result == "No images here"
    mock_s3.presigned_get_url.assert_not_awaited()
