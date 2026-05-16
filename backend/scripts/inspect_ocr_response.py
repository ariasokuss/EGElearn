#!/usr/bin/env python3
"""Inspect the full Mistral OCR response structure to discover table fields.

Usage:
    uv run python scripts/inspect_ocr_response.py paper.pdf
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.learning.past_paper.mistral import PastPaperOCR


async def inspect(paper_path: Path) -> None:
    settings = get_settings()
    ocr = PastPaperOCR(settings.mistral)

    pdf_bytes = paper_path.read_bytes()
    print(f"Processing {paper_path.name}...\n")

    document_url = await ocr._upload_pdf_and_get_signed_url(pdf_bytes)

    from mistralai.client import Mistral
    client = Mistral(api_key=settings.mistral.api_key)
    response = await client.ocr.process_async(
        model=settings.mistral.ocr_model,
        document={"type": "document_url", "document_url": document_url},
        include_image_base64=True,
        table_format="markdown",
    )

    # Inspect top-level response fields
    print("=== TOP-LEVEL RESPONSE FIELDS ===")
    for attr in dir(response):
        if attr.startswith("_"):
            continue
        val = getattr(response, attr)
        if callable(val):
            continue
        print(f"  {attr}: {type(val).__name__} = {repr(val)[:200]}")

    print(f"\n=== PAGES ({len(response.pages)}) ===")
    for page in response.pages:
        print(f"\n--- Page {page.index} ---")
        for attr in dir(page):
            if attr.startswith("_"):
                continue
            val = getattr(page, attr)
            if callable(val):
                continue
            if attr == "markdown":
                print(f"  markdown: {len(val or '')} chars")
                # Show tbl references
                for line in (val or "").splitlines():
                    if "tbl-" in line.lower():
                        print(f"    tbl ref: {line.strip()}")
            elif attr == "images":
                imgs = val or []
                print(f"  images: {len(imgs)} items")
                for img in imgs:
                    img_id = getattr(img, "id", "?")
                    b64 = getattr(img, "image_base64", None)
                    b64_len = len(b64) if b64 else 0
                    print(f"    - id={img_id}, base64_len={b64_len}")
                    # Show ALL attributes of image objects
                    for iattr in dir(img):
                        if iattr.startswith("_") or iattr in ("id", "image_base64"):
                            continue
                        ival = getattr(img, iattr)
                        if callable(ival):
                            continue
                        print(f"      {iattr}: {repr(ival)[:150]}")
            else:
                print(f"  {attr}: {type(val).__name__} = {repr(val)[:200]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/inspect_ocr_response.py <paper.pdf>")
        sys.exit(1)
    asyncio.run(inspect(Path(sys.argv[1])))
