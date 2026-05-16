"""Standalone A-Level seeder.

Run via:
    make seed               (inside Docker)
    uv run python scripts/seed_alevel.py   (locally)
"""

import asyncio
import logging
import sys

# Ensure project root is on sys.path when run directly
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import all ORM models so SQLAlchemy can resolve every relationship before
# any query runs.  Without these imports the mapper raises KeyError on models
# referenced by relationships that weren't loaded (e.g. ProcessingJob).
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
from src.roadmap.seed import seed_roadmap

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)

    try:
        logger.info("Starting A-Level seed…")
        await seed_roadmap(session_factory)
        logger.info("A-Level seed complete.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
