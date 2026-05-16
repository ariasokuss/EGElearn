#!/usr/bin/env python3
"""Upload Economics diagrams from docs/ to S3 and verify lesson URLs match."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.core.s3 import S3Client

DIAGRAMS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "A-Level"
    / "Edexcel A-Level Economics"
    / "diagrams"
)
LESSONS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "A-Level"
    / "Edexcel A-Level Economics"
    / "lessons"
)

# "1.2.6 - 4.png" -> "diagrams/economics/1.2.6-4.png"
_FILE_RE = re.compile(r"^(\d+\.\d+\.\d+)\s+-\s+(\d+)\.png$", re.IGNORECASE)


def _s3_key(filename: str) -> str | None:
    m = _FILE_RE.match(filename)
    if not m:
        return None
    return f"diagrams/economics/{m.group(1)}-{m.group(2)}.png"


async def main() -> None:
    settings = get_settings()
    s3 = S3Client(settings.s3)
    await s3.open()
    await s3.ensure_bucket()

    # --- 1. Upload all diagrams ---
    uploaded = 0
    skipped = 0
    for png in sorted(DIAGRAMS_DIR.glob("*.png")):
        key = _s3_key(png.name)
        if key is None:
            print(f"  SKIP (name mismatch): {png.name}")
            skipped += 1
            continue
        await s3.upload_bytes(key, png.read_bytes(), content_type="image/png")
        print(f"  UP  {key}")
        uploaded += 1

    print(f"\nUploaded {uploaded}, skipped {skipped}")

    # --- 2. Verify lesson URLs match uploaded keys ---
    base_url = f"https://{settings.s3.bucket}.s3.{settings.s3.region}.amazonaws.com"
    url_re = re.compile(r"!\[Diagram\]\((https://[^\)]+)\)")

    missing: list[str] = []
    for lesson in sorted(LESSONS_DIR.glob("*.md")):
        content = lesson.read_text()
        for url in url_re.findall(content):
            if not url.startswith(base_url):
                print(f"  WARN foreign URL in {lesson.name}: {url}")
            key = url.split(base_url + "/", 1)[-1] if base_url in url else url
            # check key was among uploaded
            expected_file = key.split("/")[-1]  # e.g. "1.1.4-1.png"
            # reconstruct what local file would be
            km = re.match(r"(\d+\.\d+\.\d+)-(\d+)\.png", expected_file)
            if not km:
                print(f"  WARN unrecognised key pattern: {key}")
                continue
            local_name = f"{km.group(1)} - {km.group(2)}.png"
            local_path = DIAGRAMS_DIR / local_name
            if not local_path.exists():
                print(f"  MISSING local file for URL: {url}")
                missing.append(url)

    if missing:
        print(f"\n{len(missing)} URL(s) have no matching local diagram - check above")
    else:
        print("\nAll lesson diagram URLs have a matching local file that was uploaded.")

    await s3.close()


if __name__ == "__main__":
    asyncio.run(main())
