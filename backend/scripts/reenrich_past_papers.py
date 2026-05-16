"""Re-run past-paper context enrichment over existing DB rows.

Idempotent. Default mode is --dry-run. Use --apply to actually write changes.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before importing src modules.
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import asyncpg  # noqa: E402

from src.learning.past_paper.service import (  # noqa: E402
    _build_enriched_context,
    _dedupe_question_against_context,
    _extract_image_blocks,
    _extract_table_blocks,
)

logger = logging.getLogger("reenrich")

_IMG_URL_RE = re.compile(r"!\[[^\]]*\]\((/api/v1/past-papers/[^)\s]+)\)")


def _make_dsn(raw: str) -> str:
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def _build_image_url_map(ocr_markdown: str) -> dict[str, str]:
    """For OCR markdown that already contains resolved /api/v1/... URLs,
    map each URL to itself so _extract_image_blocks finds them."""
    urls = set(_IMG_URL_RE.findall(ocr_markdown or ""))
    return {url: url for url in urls}


async def _process_template(
    conn: asyncpg.Connection,
    template_id: uuid.UUID,
    ocr_markdown: str,
    apply: bool,
) -> dict[str, int]:
    counts = {
        "questions": 0,
        "context_changed": 0,
        "question_changed": 0,
        "both_changed": 0,
        "unchanged": 0,
    }
    image_url_by_path = _build_image_url_map(ocr_markdown)
    table_blocks = _extract_table_blocks(ocr_markdown)
    (
        table_images,
        figure_images,
        table_captions,
        figure_captions,
    ) = _extract_image_blocks(ocr_markdown, image_url_by_path)

    rows = await conn.fetch(
        """
        SELECT id, question, context
        FROM test_questions
        WHERE template_id = $1
        ORDER BY index
        """,
        template_id,
    )

    examples: list[tuple[str, str, str, str, str]] = []

    for r in rows:
        counts["questions"] += 1
        old_question = r["question"] or ""
        old_context = r["context"]

        new_context = _build_enriched_context(
            question_text=old_question,
            context=old_context,
            table_blocks=table_blocks,
            table_images=table_images,
            figure_images=figure_images,
            image_url_by_path=image_url_by_path,
            table_captions=table_captions,
            figure_captions=figure_captions,
        )
        new_question = _dedupe_question_against_context(old_question, new_context)

        ctx_changed = (new_context or None) != (old_context or None)
        q_changed = new_question != old_question

        if ctx_changed and q_changed:
            counts["both_changed"] += 1
        elif ctx_changed:
            counts["context_changed"] += 1
        elif q_changed:
            counts["question_changed"] += 1
        else:
            counts["unchanged"] += 1
            continue

        if len(examples) < 3:
            examples.append((
                str(r["id"]),
                "ctx" if ctx_changed else "",
                "q" if q_changed else "",
                (old_context or "")[:300],
                (new_context or "")[:300],
            ))

        if apply:
            await conn.execute(
                """
                UPDATE test_questions
                SET context = $1, question = $2
                WHERE id = $3
                """,
                new_context,
                new_question,
                r["id"],
            )

    if examples:
        logger.info("template=%s examples:", template_id)
        for qid, ctx_flag, q_flag, old_ctx, new_ctx in examples:
            logger.info("  q=%s changed=[%s%s]", qid, ctx_flag, q_flag)
            logger.info("    OLD ctx: %s", old_ctx)
            logger.info("    NEW ctx: %s", new_ctx)

    return counts


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    parser.add_argument(
        "--template-id", type=str, default=None,
        help="Only process this template UUID",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N templates",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    dsn = _make_dsn(os.environ["POSTGRES__DSN"])
    ssl_insecure = os.environ.get("POSTGRES__SSL_INSECURE", "").lower() in (
        "1", "true", "yes",
    )
    conn = await asyncpg.connect(dsn, ssl="require" if ssl_insecure else None)

    sql = """
        SELECT id, ocr_markdown
        FROM test_templates
        WHERE type = 'past_paper'
          AND status = 'ready'
          AND ocr_markdown IS NOT NULL
        ORDER BY created_at DESC
    """
    params: list = []
    if args.template_id:
        sql = sql.replace(
            "WHERE type = 'past_paper'",
            "WHERE type = 'past_paper' AND id = $1",
        )
        params.append(uuid.UUID(args.template_id))
    if args.limit:
        sql += f"\nLIMIT {int(args.limit)}"

    templates = await conn.fetch(sql, *params)

    totals: dict[str, int] = {
        "templates": 0, "questions": 0,
        "context_changed": 0, "question_changed": 0,
        "both_changed": 0, "unchanged": 0,
    }
    for t in templates:
        totals["templates"] += 1
        if args.apply:
            tr = conn.transaction()
            await tr.start()
            try:
                counts = await _process_template(
                    conn, t["id"], t["ocr_markdown"] or "", apply=True,
                )
                await tr.commit()
            except Exception:
                await tr.rollback()
                raise
        else:
            counts = await _process_template(
                conn, t["id"], t["ocr_markdown"] or "", apply=False,
            )
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    logger.info("=== SUMMARY (%s) ===", "APPLY" if args.apply else "DRY-RUN")
    for k, v in totals.items():
        logger.info("  %s: %d", k, v)

    await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
