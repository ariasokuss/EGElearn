#!/usr/bin/env python3
"""Replace all shared (user_id=NULL) lessons and roadmap nodes from lesson files.

Usage (from backend/):
    uv run python scripts/replace_shared_lessons.py

Reads the roadmap from docs/roadmaps/physics.md and lesson files from docs/lessons/.
Deletes all existing shared roadmap nodes, lessons, and progress, then re-seeds.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure backend src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _host_reachable(host: str, port: int) -> bool:
    """Quick check if a host:port is reachable."""
    import socket

    try:
        socket.getaddrinfo(host, port)
        return True
    except socket.gaierror:
        return False


async def main() -> None:
    from sqlalchemy import delete as sa_delete, select, func

    from src.config import get_settings
    from src.core.db import create_engine, create_session_factory

    # Import all model modules so SQLAlchemy resolves all relationships
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

    from src.files.models import Folder, FolderType
    from src.learning.models import Lesson
    from src.roadmap.data import parse_physics_roadmap
    from src.roadmap.models import RoadmapNode

    settings = get_settings()
    db_settings = settings.postgres

    # When running outside Docker, swap container hostname for localhost
    if "postgres:" in db_settings.dsn and not _host_reachable("postgres", 5432):
        db_settings.dsn = db_settings.dsn.replace("@postgres:", "@localhost:")
        logger.info("Rewrote DSN to use localhost (running outside Docker)")

    engine = create_engine(db_settings)
    session_factory = create_session_factory(engine)

    lessons_dir = Path(__file__).resolve().parent.parent.parent / "docs" / "lessons"
    if not lessons_dir.is_dir():
        logger.error("Lessons directory not found: %s", lessons_dir)
        sys.exit(1)

    async with session_factory() as session:
        # --- 1. Find shared folder ---
        folder = await session.scalar(
            select(Folder).where(
                Folder.user_id.is_(None),
                Folder.type == FolderType.a_level,
            )
        )
        if not folder:
            logger.error(
                "No shared a_level folder found. Run the app once first to create it."
            )
            sys.exit(1)

        logger.info("Found shared folder: %s (%s)", folder.name, folder.id)

        # --- 2. Count existing data ---
        old_node_count = await session.scalar(
            select(func.count())
            .select_from(RoadmapNode)
            .where(RoadmapNode.folder_id == folder.id)
        )
        old_lesson_ids = list(
            await session.scalars(
                select(RoadmapNode.lesson_id).where(
                    RoadmapNode.folder_id == folder.id,
                    RoadmapNode.lesson_id.is_not(None),
                )
            )
        )

        logger.info(
            "Existing: %d roadmap nodes, %d lessons",
            old_node_count,
            len(old_lesson_ids),
        )

        # --- 3. Delete all roadmap nodes (CASCADE deletes RoadmapProgress) ---
        await session.execute(
            sa_delete(RoadmapNode).where(RoadmapNode.folder_id == folder.id)
        )
        logger.info("Deleted roadmap nodes and progress")

        # --- 4. Delete shared lessons (CASCADE deletes blocks, progress, sessions) ---
        if old_lesson_ids:
            await session.execute(
                sa_delete(Lesson).where(Lesson.id.in_(old_lesson_ids))
            )
            logger.info("Deleted %d shared lessons", len(old_lesson_ids))

        await session.flush()

        # --- 5. Re-parse roadmap and re-seed ---
        sections = parse_physics_roadmap()

        node_count = 0
        lesson_count = 0
        missing_files: list[str] = []

        for section_data in sections:
            section_node = RoadmapNode(
                folder_id=folder.id,
                parent_id=None,
                level=1,
                name=section_data.name,
                position=section_data.position,
            )
            session.add(section_node)
            await session.flush()
            node_count += 1

            for sub_data in section_data.subsections:
                sub_node = RoadmapNode(
                    folder_id=folder.id,
                    parent_id=section_node.id,
                    level=2,
                    name=sub_data.name,
                    position=sub_data.position,
                )
                session.add(sub_node)
                await session.flush()
                node_count += 1

                for lesson_data in sub_data.lessons:
                    content, found = _load_lesson(
                        lessons_dir, lesson_data.id_str, lesson_data.name
                    )
                    if not found:
                        missing_files.append(f"{lesson_data.id_str} {lesson_data.name}")
                    await _create_lesson_and_node(
                        session,
                        folder.id,
                        sub_node.id,
                        lesson_data.name,
                        lesson_data.position,
                        content,
                    )
                    node_count += 1
                    lesson_count += 1

            for lesson_data in section_data.lessons:
                content, found = _load_lesson(
                    lessons_dir, lesson_data.id_str, lesson_data.name
                )
                if not found:
                    missing_files.append(f"{lesson_data.id_str} {lesson_data.name}")
                await _create_lesson_and_node(
                    session,
                    folder.id,
                    section_node.id,
                    lesson_data.name,
                    lesson_data.position,
                    content,
                )
                node_count += 1
                lesson_count += 1

        await session.commit()

    await engine.dispose()

    # --- Summary ---
    print("\n--- Done ---")
    print(f"Roadmap nodes created: {node_count}")
    print(f"Lessons created:       {lesson_count}")
    if missing_files:
        print(f"\nMissing lesson files ({len(missing_files)}):")
        for m in missing_files:
            print(f"  - {m}")
    else:
        print("All lesson files found.")


def _load_lesson(lessons_dir: Path, id_str: str, name: str) -> tuple[str, bool]:
    """Load lesson content from file. Returns (content, was_found)."""
    path = lessons_dir / f"{id_str} {name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8"), True

    if id_str:
        # Try exact prefix match (e.g. "2.1.3 *.md")
        candidates = list(lessons_dir.glob(f"{id_str} *.md"))
        if candidates:
            return candidates[0].read_text(encoding="utf-8"), True

        # Try embedded match for RPs (e.g. "3.1.3 RP 1 - *.md" for id_str="RP 1")
        candidates = list(lessons_dir.glob(f"*{id_str}*"))
        if candidates:
            return candidates[0].read_text(encoding="utf-8"), True

    return f"# {name}\n\nContent coming soon.", False


async def _create_lesson_and_node(
    session,
    folder_id,
    parent_id,
    name: str,
    position: int,
    content: str,
) -> None:
    from src.learning.models import FeynmanBlock, Lesson, LessonBlock
    from src.learning.parser import (
        extract_description,
        parse_feynman_blocks,
        parse_lesson_blocks,
    )
    from src.roadmap.models import RoadmapNode

    description = extract_description(content)

    lesson = Lesson(
        user_id=None,
        name=name,
        description=description,
        content=content,
    )
    session.add(lesson)
    await session.flush()

    if description is not None:
        parsed_blocks = parse_lesson_blocks(content)
        for pb in parsed_blocks:
            session.add(
                LessonBlock(
                    lesson_id=lesson.id,
                    user_id=None,
                    content=pb.content,
                    block_number=pb.block_number,
                    is_summary=pb.is_summary,
                )
            )

        parsed_feynman = parse_feynman_blocks(content)
        for pf in parsed_feynman:
            session.add(
                FeynmanBlock(
                    lesson_id=lesson.id,
                    user_id=None,
                    scope=pf.scope,
                    question=pf.question,
                    points=pf.points,
                )
            )

        lesson.num_blocks = len(parsed_blocks)

    node = RoadmapNode(
        folder_id=folder_id,
        parent_id=parent_id,
        level=3,
        name=name,
        position=position,
        lesson_id=lesson.id,
    )
    session.add(node)
    await session.flush()


if __name__ == "__main__":
    asyncio.run(main())
