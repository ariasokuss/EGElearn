from __future__ import annotations

import re
from src.config import get_settings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.s3 import S3Client

config = get_settings()
_ASSET_IMG_RE = re.compile(
    config.app.api_prefix + r"/past-papers/[0-9a-f-]{36}/assets/images/[^\s)\"']+"
)


async def rewrite_image_urls_to_presigned(text: str | None, s3: "S3Client") -> str | None:
    if not text:
        return text
    matches = _ASSET_IMG_RE.findall(text)
    if not matches:
        return text
    for url in dict.fromkeys(matches):
        s3_key = url[len("/api/v1/"):]
        presigned = await s3.presigned_get_url(s3_key, expires_in=3600)
        text = text.replace(url, presigned)
    return text
