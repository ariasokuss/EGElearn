#!/usr/bin/env python3
"""Process a PDF through Mistral OCR and save all artifacts to local storage.

Mirrors the exact same processing as the past-paper upload pipeline but writes
everything to a local directory instead of S3.

Usage:
    uv run python scripts/ocr_to_local.py paper.pdf [--mark-scheme ms.pdf] [--out ./output]

Output structure (mirrors S3 layout):
    {out}/{name}/origin/paper.pdf
    {out}/{name}/origin/mark-scheme.pdf        (if provided)
    {out}/{name}/origin_md/paper.md
    {out}/{name}/origin_md/mark-scheme.md      (if provided)
    {out}/{name}/assets/{image_id}.png          (all extracted images/tables)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import re
import shutil
import sys
from pathlib import Path

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,")

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.learning.past_paper.mistral import PastPaperOCR


async def process(
    paper_path: Path,
    mark_scheme_path: Path | None,
    out_dir: Path,
) -> None:
    settings = get_settings()
    ocr = PastPaperOCR(settings.mistral)

    name = paper_path.stem
    root = out_dir / name

    # Create directories
    (root / "origin").mkdir(parents=True, exist_ok=True)
    (root / "origin_md").mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(parents=True, exist_ok=True)

    # ── Paper ────────────────────────────────────────────────────────────────
    pdf_bytes = paper_path.read_bytes()
    print(f"Processing {paper_path.name} ({len(pdf_bytes):,} bytes)...")

    # Save origin PDF
    shutil.copy2(paper_path, root / "origin" / "paper.pdf")

    # OCR — use raw response to also save individual table files
    document_url = await ocr._upload_pdf_and_get_signed_url(pdf_bytes)
    from mistralai.client import Mistral as _MistralClient
    _client = _MistralClient(api_key=settings.mistral.api_key)
    response = await _client.ocr.process_async(
        model=settings.mistral.ocr_model,
        document={"type": "document_url", "document_url": document_url},
        include_image_base64=True,
        table_format="markdown",
    )

    # Save individual table files
    tables_dir = root / "assets" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    table_count = 0
    for page in response.pages:
        for tbl in getattr(page, "tables", None) or []:
            tbl_id = getattr(tbl, "id", None)
            tbl_content = getattr(tbl, "content", None)
            if tbl_id and tbl_content:
                (tables_dir / tbl_id).write_text(tbl_content, encoding="utf-8")
                table_count += 1
    if table_count:
        print(f"  Saved {table_count} table files")

    # Now process through normal pipeline (inlines tables into markdown)
    markdown, images_dict, _ = await ocr.pdf_to_markdown_with_images(pdf_bytes)
    print(f"  OCR complete: {len(markdown):,} chars, {len(images_dict)} images")

    # Save markdown (with tables inlined)
    (root / "origin_md" / "paper.md").write_text(markdown, encoding="utf-8")

    # Save all images/tables
    (root / "assets" / "images").mkdir(parents=True, exist_ok=True)
    for image_id, b64_data in images_dict.items():
        image_bytes = base64.b64decode(_DATA_URI_RE.sub("", b64_data))
        if "." in image_id:
            filename = image_id
        elif image_bytes[:2] == b"\xff\xd8":
            filename = f"{image_id}.jpeg"
        else:
            filename = f"{image_id}.png"
        (root / "assets" / "images" / filename).write_bytes(image_bytes)
    print(f"  Saved {len(images_dict)} images")

    # ── Mark scheme ──────────────────────────────────────────────────────────
    if mark_scheme_path:
        ms_bytes = mark_scheme_path.read_bytes()
        print(f"Processing {mark_scheme_path.name} ({len(ms_bytes):,} bytes)...")

        shutil.copy2(mark_scheme_path, root / "origin" / "mark-scheme.pdf")

        ms_markdown, ms_images, _ = await ocr.pdf_to_markdown_with_images(ms_bytes)
        print(f"  OCR complete: {len(ms_markdown):,} chars, {len(ms_images)} images")

        (root / "origin_md" / "mark-scheme.md").write_text(
            ms_markdown, encoding="utf-8"
        )

        for image_id, b64_data in ms_images.items():
            image_bytes = base64.b64decode(_DATA_URI_RE.sub("", b64_data))
            if "." in image_id:
                filename = f"ms_{image_id}"
            elif image_bytes[:2] == b"\xff\xd8":
                filename = f"ms_{image_id}.jpeg"
            else:
                filename = f"ms_{image_id}.png"
            (root / "assets" / "images" / filename).write_bytes(image_bytes)
        print(f"  Saved {len(ms_images)} mark scheme images")

    print(f"\nAll artifacts saved to: {root}")
    print("  origin/        — original PDFs")
    print("  origin_md/     — OCR markdown")
    print("  assets/        — extracted images & tables")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process a PDF through Mistral OCR and save all artifacts locally."
    )
    parser.add_argument("paper", type=Path, help="Path to the past paper PDF")
    parser.add_argument(
        "--mark-scheme", "-m", type=Path, default=None,
        help="Path to the mark scheme PDF (optional)",
    )
    parser.add_argument(
        "--out", "-o", type=Path, default=Path("./ocr_output"),
        help="Output directory (default: ./ocr_output)",
    )
    args = parser.parse_args()

    if not args.paper.exists():
        print(f"Error: {args.paper} not found", file=sys.stderr)
        sys.exit(1)
    if args.mark_scheme and not args.mark_scheme.exists():
        print(f"Error: {args.mark_scheme} not found", file=sys.stderr)
        sys.exit(1)

    asyncio.run(process(args.paper, args.mark_scheme, args.out))


if __name__ == "__main__":
    main()
