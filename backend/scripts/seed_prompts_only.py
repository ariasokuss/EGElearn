"""Seed only PQG prompts from docs/A-Level into the DB.

Skips roadmap/lesson/test/exam re-parsing — useful when you've only edited
prompt .md files and don't want to wait for the full A-Level seed.

Usage:
    uv run python scripts/seed_prompts_only.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.prompts.models  # noqa: F401  — register ORM
import src.roadmap.models  # noqa: F401

from src.config import get_settings
from src.core.db import create_engine, create_session_factory
from src.core.logging import configure_logging
from src.roadmap.pqg_seeder import seed_pqg_prompts, slugify_service_name

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "A-Level"


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)

    if not DOCS_DIR.is_dir():
        raise SystemExit(f"docs/A-Level not found at {DOCS_DIR}")

    subject_dirs = sorted(p for p in DOCS_DIR.iterdir() if p.is_dir())
    total = 0
    try:
        for subject_dir in subject_dirs:
            if not (subject_dir / "question-types.md").exists():
                continue
            pqg_service = slugify_service_name(subject_dir.name)
            async with session_factory() as session:
                count = await seed_pqg_prompts(session, subject_dir, pqg_service)
                await session.commit()
            logger.info("%s — %d prompts upserted", subject_dir.name, count)
            total += count
    finally:
        await engine.dispose()

    logger.info("Done. Total prompts upserted: %d", total)


if __name__ == "__main__":
    asyncio.run(main())
