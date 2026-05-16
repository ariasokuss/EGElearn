#!/usr/bin/env python3
"""Delete all shared (user_id=NULL) folders, roadmap nodes, lessons, and tests.

Usage (from backend/):
    uv run python scripts/prune_shared_data.py            # execute
    uv run python scripts/prune_shared_data.py --dry-run   # preview only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _host_reachable(host: str, port: int) -> bool:
    try:
        socket.getaddrinfo(host, port)
        return True
    except socket.gaierror:
        return False


async def main(dry_run: bool) -> None:
    from sqlalchemy import delete as sa_delete, select, func

    from src.config import get_settings
    from src.core.db import create_engine, create_session_factory

    # Import all models so SQLAlchemy resolves relationships
    import src.auth.models  # noqa: F401
    import src.files.models  # noqa: F401
    import src.processing.models  # noqa: F401
    import src.learning.models  # noqa: F401
    import src.learning.tests.models  # noqa: F401
    import src.roadmap.models  # noqa: F401
    import src.chat.models  # noqa: F401
    import src.exam.models  # noqa: F401
    import src.mail.models  # noqa: F401
    import src.prompts.models  # noqa: F401

    from src.files.models import Folder
    from src.learning.models import Lesson
    from src.learning.tests.models import TestTemplate
    from src.roadmap.models import RoadmapNode, RoadmapProgress, UserFolderPosition

    settings = get_settings()
    db_settings = settings.postgres

    if "postgres:" in db_settings.dsn and not _host_reachable("postgres", 5432):
        db_settings.dsn = db_settings.dsn.replace("@postgres:", "@localhost:")
        logger.info("Rewrote DSN to use localhost (running outside Docker)")

    engine = create_engine(db_settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        # --- Collect shared folder IDs ---
        shared_folder_ids = list(
            await session.scalars(select(Folder.id).where(Folder.user_id.is_(None)))
        )

        if not shared_folder_ids:
            print("No shared folders found — nothing to prune.")
            await engine.dispose()
            return

        # --- Collect shared lesson IDs ---
        shared_lesson_ids = list(
            await session.scalars(select(Lesson.id).where(Lesson.user_id.is_(None)))
        )

        # --- Count what will be deleted ---
        node_count = (
            await session.scalar(
                select(func.count())
                .select_from(RoadmapNode)
                .where(RoadmapNode.folder_id.in_(shared_folder_ids))
            )
            or 0
        )

        progress_count = (
            await session.scalar(
                select(func.count())
                .select_from(RoadmapProgress)
                .where(
                    RoadmapProgress.node_id.in_(
                        select(RoadmapNode.id).where(
                            RoadmapNode.folder_id.in_(shared_folder_ids)
                        )
                    )
                )
            )
            or 0
        )

        test_count = (
            await session.scalar(
                select(func.count())
                .select_from(TestTemplate)
                .where(TestTemplate.folder_id.in_(shared_folder_ids))
            )
            or 0
        )

        pos_count = (
            await session.scalar(
                select(func.count())
                .select_from(UserFolderPosition)
                .where(UserFolderPosition.folder_id.in_(shared_folder_ids))
            )
            or 0
        )

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Shared data to prune:")
        print(f"  Folders:            {len(shared_folder_ids)}")
        print(f"  Roadmap nodes:      {node_count}")
        print(f"  Roadmap progress:   {progress_count}")
        print(f"  Test templates:     {test_count}")
        print(f"  Folder positions:   {pos_count}")
        print(f"  Lessons:            {len(shared_lesson_ids)}")

        if dry_run:
            print("\nDry run — no data deleted.")
            await engine.dispose()
            return

        # --- Delete (order: children first, then parents) ---

        # 1. Roadmap nodes (CASCADE deletes roadmap_progress + child nodes)
        r = await session.execute(
            sa_delete(RoadmapNode).where(
                RoadmapNode.folder_id.in_(shared_folder_ids),
                RoadmapNode.parent_id.is_(
                    None
                ),  # delete roots; CASCADE handles children
            )
        )
        logger.info(
            "Deleted %d root roadmap nodes (+ children via CASCADE)", r.rowcount
        )

        # 2. Test templates (CASCADE deletes questions, sessions, answers)
        r = await session.execute(
            sa_delete(TestTemplate).where(TestTemplate.folder_id.in_(shared_folder_ids))
        )
        logger.info(
            "Deleted %d test templates (+ questions/sessions via CASCADE)", r.rowcount
        )

        # 3. User folder positions
        r = await session.execute(
            sa_delete(UserFolderPosition).where(
                UserFolderPosition.folder_id.in_(shared_folder_ids)
            )
        )
        logger.info("Deleted %d folder positions", r.rowcount)

        # 4. Shared lessons (CASCADE deletes blocks, feynman, progress)
        if shared_lesson_ids:
            r = await session.execute(
                sa_delete(Lesson).where(Lesson.id.in_(shared_lesson_ids))
            )
            logger.info(
                "Deleted %d shared lessons (+ blocks/feynman/progress via CASCADE)",
                r.rowcount,
            )

        # 5. Shared folders
        r = await session.execute(
            sa_delete(Folder).where(Folder.id.in_(shared_folder_ids))
        )
        logger.info("Deleted %d shared folders", r.rowcount)

        await session.commit()

    await engine.dispose()
    print("\nDone. Restart the app to re-seed from docs/A-Level/.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prune all shared data from the database"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview counts without deleting"
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
