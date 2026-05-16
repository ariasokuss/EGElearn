#!/usr/bin/env python3
"""Sync one shared A-Level subject from docs into S3-backed lesson content."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.auth.models  # noqa: F401
import src.chat.models  # noqa: F401
import src.exam.models  # noqa: F401
import src.files.models  # noqa: F401
import src.learning.models  # noqa: F401
import src.learning.tests.models  # noqa: F401
import src.mail.models  # noqa: F401
import src.processing.models  # noqa: F401
import src.prompts.models  # noqa: F401
import src.roadmap.models  # noqa: F401

from src.config import get_settings
from src.core.db import create_engine, create_session_factory
from src.core.logging import configure_logging
from src.core.s3 import S3Client
from src.roadmap.seed import seed_roadmap, sync_shared_subject

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload subject diagrams to S3 and refresh shared lesson content."
    )
    parser.add_argument(
        "--subject",
        default="Edexcel A-Level Economics",
        help="Shared A-Level subject folder name under docs/A-Level/",
    )
    return parser


async def _run(subject_name: str) -> dict[str, int]:
    settings = get_settings()
    configure_logging(settings)

    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)
    s3 = S3Client(settings.s3)

    await s3.open()
    await s3.ensure_bucket()

    try:
        logger.info("Ensuring shared A-Level subjects are seeded before sync")
        await seed_roadmap(session_factory)

        async with session_factory() as session:
            result = await sync_shared_subject(
                session,
                subject_name,
                s3,
                settings.s3,
            )
            await session.commit()
            return result
    finally:
        await s3.close()
        await engine.dispose()


def main() -> None:
    args = _build_parser().parse_args()
    result = asyncio.run(_run(args.subject))
    print(f"Subject sync complete for {args.subject}")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
