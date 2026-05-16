"""
Upload a local image directly to S3 and print the image_key.
Use this to test the diagram grading pipeline without a frontend.

Usage:
    uv run python scripts/upload_diagram_test.py \
        --session-id <SESSION_ID> \
        --question-id <QUESTION_ID> \
        --image /path/to/photo.jpg

Then submit with curl:
    curl -X POST http://localhost:8000/api/v1/tests/sessions/<SESSION_ID>/answers/<QUESTION_ID>/diagram \
        -H "Authorization: Bearer <TOKEN>" \
        -H "Content-Type: application/json" \
        -d '{"image_key": "<printed key>"}'
"""

import argparse
import asyncio
import uuid
from pathlib import Path

from src.config import get_settings
from src.core.s3 import S3Client

_EXT_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".heic": "image/heic"}


async def main(session_id: str, question_id: str, image_path: Path) -> None:
    ext = image_path.suffix.lower()
    content_type = _EXT_MAP.get(ext, "image/jpeg")
    image_key = f"session-answers/{session_id}/{question_id}/{uuid.uuid4()}{ext}"

    s3 = S3Client(get_settings().s3)
    async with s3:
        data = image_path.read_bytes()
        await s3.upload_bytes(image_key, data, content_type=content_type)

    print(f"\nUploaded OK")
    print(f"image_key: {image_key}")
    print(f"\nSubmit with:")
    print(f'  curl -X POST "http://localhost:8080/api/v1/tests/sessions/{session_id}/answers/{question_id}/diagram" \\')
    print(f'    -H "Authorization: Bearer <TOKEN>" \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"image_key": "{image_key}"}}\'\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.session_id, args.question_id, args.image))
