"""Idempotent startup seeder for shared A-Level roadmaps.

Auto-discovers every subject folder inside docs/A-Level/.  Each folder must
contain:
    roadmap.md          — parsed into the roadmap node tree
    lessons/            — {id_str} {name}.md lesson files
    tests/              — {id_str} {name}_test.json test files

The shared DB folder is named exactly after the folder
(e.g. "Edexcel A-Level Economics").  Safe to run on every startup.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import S3Settings
from src.exam.models import Exam
from src.files.models import Folder, FolderType
from src.learning.models import FeynmanBlock, Lesson, LessonBlock, LessonProgress
from src.learning.parser import (
    extract_description,
    parse_feynman_blocks,
    parse_lesson_blocks,
)
from src.roadmap.data import parse_roadmap
from src.roadmap.models import RoadmapNode, RoadmapProgress
from src.roadmap.pqg_seeder import seed_pqg_prompts, slugify_service_name

logger = logging.getLogger(__name__)

_PLACEHOLDER_SUFFIX = "Content coming soon."
_DEFAULT_ALEVEL_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "docs" / "A-Level"
)
_ALEVEL_DIR = Path(os.environ.get("ALEVEL_DIR", str(_DEFAULT_ALEVEL_DIR)))
_LESSON_ID_TOKEN = (
    r"\d+(?:\.\d+)+(?:"
    r"[A-Za-z](?:-[A-Za-z])?(?:,[A-Za-z])?"
    r"|\([A-Za-z0-9,-]+\)(?:-\d+)?"
    r")?"
)
_LESSON_ID_PREFIX_RE = re.compile(rf"^(?P<id>{_LESSON_ID_TOKEN})\s+")
_LESSON_FILENAME_ID_RE = re.compile(rf"^(?P<id>{_LESSON_ID_TOKEN})(?:\s+-\s+|\s+)")
_DIAGRAM_FILENAME_RE = re.compile(
    rf"^(?P<lesson_id>{_LESSON_ID_TOKEN})\s*-\s*(?P<ordinal>\d+)\.(?P<ext>[a-z0-9]+)$",
    re.IGNORECASE,
)
_DIAGRAM_MARKER_RE = re.compile(r"^\[DIAGRAM:[^\n]*\]$", re.IGNORECASE)
_MARKDOWN_IMAGE_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)$")
_SHARED_SUBJECT_MEDIA_SLUGS = {
    "Edexcel A-Level Economics": "economics",
    "AQA A-Level Psyhology": "psychology",
    "Edexcel A-Level Business": "business",
    "AQA A-Level Physics": "physics",
    "AQA A-Level Chemistry": "chemistry",
    "AQA A-Level Biology": "biology",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def seed_roadmap(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Seed all shared A-Level roadmaps into the database (idempotent)."""
    subject_dirs = _discover_alevel_subjects()
    if not subject_dirs:
        logger.warning("No A-Level subject folders found in %s", _ALEVEL_DIR)
        return

    for subject_dir in subject_dirs:
        async with session_factory() as session:
            await _seed_subject(session, subject_dir)


async def sync_shared_subject(
    session: AsyncSession,
    subject_name: str,
    s3: "S3Client",
    s3_settings: S3Settings,
) -> dict[str, int]:
    """Upload subject diagrams, rewrite lesson markdown, and refresh shared data."""
    subject_dir = _ALEVEL_DIR / subject_name
    if not subject_dir.is_dir():
        raise FileNotFoundError(f"Subject dir not found: {subject_dir}")
    if not (subject_dir / "roadmap.md").is_file():
        raise FileNotFoundError(f"Roadmap not found for subject: {subject_dir}")

    folder = await session.scalar(
        select(Folder).where(
            Folder.name == subject_name,
            Folder.type == FolderType.a_level,
            Folder.user_id.is_(None),
        )
    )
    if folder is None:
        raise LookupError(
            f"Shared folder not found for subject {subject_name!r}. Run the A-Level seed first."
        )

    diagrams_uploaded, lessons_rewritten = await _sync_subject_diagrams_to_s3(
        subject_dir,
        subject_name,
        s3,
        s3_settings,
    )
    lesson_nodes = await _sync_subject_lessons_in_place(
        session,
        subject_dir,
        folder.id,
    )

    tests_dir = subject_dir / "tests"

    from src.learning.tests.inline_quiz import seed_inline_quizzes
    from src.learning.tests.lesson_tests import seed_subject_tests

    test_count = await seed_subject_tests(session, folder.id, tests_dir, lesson_nodes)
    inline_count = await seed_inline_quizzes(session, folder.id, lesson_nodes)
    exam_count = await seed_exams(session, folder.id, subject_dir)

    logger.info(
        "Synced subject '%s': diagrams_uploaded=%d lessons_rewritten=%d lessons_refreshed=%d tests=%d inline_quizzes=%d exams=%d",
        subject_name,
        diagrams_uploaded,
        lessons_rewritten,
        len(lesson_nodes),
        test_count,
        inline_count,
        exam_count,
    )
    return {
        "diagrams_uploaded": diagrams_uploaded,
        "lessons_rewritten": lessons_rewritten,
        "lessons_refreshed": len(lesson_nodes),
        "tests_seeded": test_count,
        "inline_quizzes_seeded": inline_count,
        "exams_seeded": exam_count,
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _discover_alevel_subjects() -> list[Path]:
    """Return sorted list of subject dirs that contain a roadmap.md."""
    if not _ALEVEL_DIR.is_dir():
        return []
    return sorted(
        d for d in _ALEVEL_DIR.iterdir() if d.is_dir() and (d / "roadmap.md").exists()
    )


# ---------------------------------------------------------------------------
# Per-subject seeding
# ---------------------------------------------------------------------------


async def _seed_subject(session: AsyncSession, subject_dir: Path) -> None:
    """Seed one subject from its docs/A-Level/{name}/ folder (idempotent)."""
    folder_name = subject_dir.name  # e.g. "Edexcel A-Level Economics"

    # 1. Find or create the shared folder
    folder = await _get_or_create_shared_folder(session, folder_name)

    # 2. Check idempotency
    existing_node = await session.scalar(
        select(RoadmapNode)
        .where(
            RoadmapNode.folder_id == folder.id,
            RoadmapNode.level == 1,
        )
        .order_by(RoadmapNode.position)
        .limit(1)
    )
    if existing_node:
        await _update_subject(session, subject_dir, folder.id)
        await session.commit()
        logger.debug("Subject '%s' already seeded — ran update pass.", folder_name)
        return

    # 3. Parse roadmap from the subject's own roadmap.md
    roadmap_md = (subject_dir / "roadmap.md").read_text(encoding="utf-8")
    sections = parse_roadmap("", md=roadmap_md)

    lessons_dir = subject_dir / "lessons"
    tests_dir = subject_dir / "tests"

    # 4. Build node tree and collect (id_str, name, lesson, node) tuples for tests
    node_count = 0
    lesson_nodes: list[tuple[str, str, Lesson, RoadmapNode]] = []

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
                lesson, node = await _create_lesson_and_node(
                    session,
                    folder.id,
                    sub_node.id,
                    lesson_data.name,
                    lesson_data.position,
                    lesson_data.id_str,
                    lessons_dir,
                )
                lesson_nodes.append(
                    (lesson_data.id_str, lesson_data.name, lesson, node)
                )
                node_count += 1

        for lesson_data in section_data.lessons:
            lesson, node = await _create_lesson_and_node(
                session,
                folder.id,
                section_node.id,
                lesson_data.name,
                lesson_data.position,
                lesson_data.id_str,
                lessons_dir,
            )
            lesson_nodes.append((lesson_data.id_str, lesson_data.name, lesson, node))
            node_count += 1

    # 5. Seed tests
    from src.learning.tests.lesson_tests import seed_subject_tests

    test_count = await seed_subject_tests(session, folder.id, tests_dir, lesson_nodes)

    # 6. Seed inline quizzes (extract ::: question directives from lesson content)
    from src.learning.tests.inline_quiz import seed_inline_quizzes

    inline_count = await seed_inline_quizzes(session, folder.id, lesson_nodes)

    # 7. Seed predefined exams from exams.json (if present)
    exam_count = await seed_exams(session, folder.id, subject_dir)

    await session.commit()

    # Seed PQG prompts if question-types.md exists
    pqg_service = slugify_service_name(folder_name)
    if (subject_dir / "question-types.md").exists():
        folder.pqg_service = pqg_service
        await seed_pqg_prompts(session, subject_dir, pqg_service)
        await session.commit()

    logger.info(
        "Seeded '%s': %d nodes, %d lessons, %d lesson tests, %d inline quizzes, %d exams",
        folder_name,
        node_count,
        len(lesson_nodes),
        test_count,
        inline_count,
        exam_count,
    )


async def _update_subject(
    session: AsyncSession,
    subject_dir: Path,
    folder_id: uuid.UUID,
) -> int:
    """Reconcile docs/A-Level/{subject} into the DB.

    Renames roadmap nodes to match the current ``roadmap.md``, refreshes lesson
    content from disk, and re-seeds tests, inline quizzes, exams, and PQG
    prompts. Idempotent — safe to re-run.

    Returns number of lessons whose content was refreshed.
    """
    from sqlalchemy.orm import selectinload

    lessons_dir = subject_dir / "lessons"
    tests_dir = subject_dir / "tests"

    # Parse the current roadmap and build two indexes:
    #   stored_name_to_parts: stored display name → (id_str, clean_name)
    #   id_to_parts: id_str → (id_str, clean_name) for non-empty id_str
    roadmap_md = (subject_dir / "roadmap.md").read_text(encoding="utf-8")
    sections = parse_roadmap("", md=roadmap_md)
    stored_name_to_parts: dict[str, tuple[str, str]] = {}
    id_to_parts: dict[str, tuple[str, str]] = {}
    for section in sections:
        for sub in section.subsections:
            for ld in sub.lessons:
                stored = f"{ld.id_str} {ld.name}" if ld.id_str else ld.name
                stored_name_to_parts[stored] = (ld.id_str, ld.name)
                if ld.id_str:
                    id_to_parts.setdefault(ld.id_str, (ld.id_str, ld.name))
        for ld in section.lessons:
            stored = f"{ld.id_str} {ld.name}" if ld.id_str else ld.name
            stored_name_to_parts[stored] = (ld.id_str, ld.name)
            if ld.id_str:
                id_to_parts.setdefault(ld.id_str, (ld.id_str, ld.name))

    nodes = list(
        (
            await session.execute(
                select(RoadmapNode)
                .where(
                    RoadmapNode.folder_id == folder_id,
                    RoadmapNode.level == 3,
                    RoadmapNode.lesson_id.is_not(None),
                )
                .options(selectinload(RoadmapNode.lesson))
            )
        )
        .scalars()
        .all()
    )

    updated = 0
    renamed = 0
    lesson_nodes: list[tuple[str, str, Lesson, RoadmapNode]] = []

    for node in nodes:
        lesson = node.lesson
        if lesson is None:
            continue

        # Resolve (id_str, clean_name) by trying current stored name, then by
        # extracting id_str from the stored name and looking up in id_to_parts.
        if node.name in stored_name_to_parts:
            id_str, clean_name = stored_name_to_parts[node.name]
        else:
            extracted_id, extracted_name = _split_display_name(node.name)
            if extracted_id and extracted_id in id_to_parts:
                id_str, clean_name = id_to_parts[extracted_id]
            else:
                id_str, clean_name = extracted_id, extracted_name

        new_display_name = f"{id_str} {clean_name}" if id_str else clean_name

        if node.name != new_display_name:
            logger.info(
                "Renaming roadmap node %r → %r", node.name, new_display_name
            )
            node.name = new_display_name
            renamed += 1
        if lesson.name != new_display_name:
            lesson.name = new_display_name

        # Always refresh lesson content from disk (not just placeholders).
        content = _load_lesson_content(id_str, clean_name, lessons_dir)
        if content is not None and lesson.content != content:
            lesson.content = content
            lesson.description = extract_description(content)
            await session.flush()
            await _parse_and_store_blocks(session, lesson.id, content)
            updated += 1
            logger.debug("Refreshed lesson content for %s (%s)", id_str, clean_name)

        lesson_nodes.append((id_str, clean_name, lesson, node))

    if renamed or updated:
        await session.flush()
    if renamed:
        logger.info(
            "Renamed %d roadmap nodes for '%s'", renamed, subject_dir.name
        )

    # Re-seed tests (idempotent — clears and re-inserts)
    from src.learning.tests.lesson_tests import seed_subject_tests

    test_count = await seed_subject_tests(session, folder_id, tests_dir, lesson_nodes)
    logger.debug("Re-seeded %d lesson tests for '%s'", test_count, subject_dir.name)

    # Re-seed inline quizzes
    from src.learning.tests.inline_quiz import seed_inline_quizzes

    inline_count = await seed_inline_quizzes(session, folder_id, lesson_nodes)
    logger.debug("Re-seeded %d inline quizzes for '%s'", inline_count, subject_dir.name)

    # Re-seed predefined exams
    exam_count = await seed_exams(session, folder_id, subject_dir)
    logger.debug("Re-seeded %d exams for '%s'", exam_count, subject_dir.name)

    # Re-sync PQG prompts on every startup
    pqg_service = slugify_service_name(subject_dir.name)
    if (subject_dir / "question-types.md").exists():
        folder = await session.scalar(
            select(Folder).where(
                Folder.name == subject_dir.name,
                Folder.type == FolderType.a_level,
                Folder.user_id.is_(None),
            )
        )
        if folder:
            folder.pqg_service = pqg_service
            await seed_pqg_prompts(session, subject_dir, pqg_service)

    return updated


async def _sync_subject_diagrams_to_s3(
    subject_dir: Path,
    subject_name: str,
    s3: "S3Client",
    s3_settings: S3Settings,
) -> tuple[int, int]:
    """Upload subject diagrams to S3 and rewrite lesson markdown in place."""
    lessons_dir = subject_dir / "lessons"
    diagrams_dir = subject_dir / "diagrams"
    if not lessons_dir.is_dir():
        raise FileNotFoundError(f"Lessons dir not found: {lessons_dir}")
    if not diagrams_dir.exists():
        return 0, 0

    diagrams_uploaded = 0
    lessons_rewritten = 0

    for lesson_path in sorted(lessons_dir.glob("*.md")):
        id_str = _extract_lesson_id_from_filename(lesson_path)
        if not id_str:
            continue

        content = lesson_path.read_text(encoding="utf-8")
        diagram_paths = _find_ordered_diagram_paths(id_str, diagrams_dir)
        marker_count = _count_diagram_markers(content)

        if marker_count == 0 and not diagram_paths:
            continue
        if marker_count > len(diagram_paths):
            raise ValueError(
                f"Diagram marker count mismatch for {lesson_path.name}: "
                f"{marker_count} marker(s), {len(diagram_paths)} diagram(s)"
            )
        if len(diagram_paths) > marker_count:
            logger.warning(
                "Ignoring %d extra diagram(s) for %s beyond the %d lesson marker(s)",
                len(diagram_paths) - marker_count,
                lesson_path.name,
                marker_count,
            )
            diagram_paths = diagram_paths[:marker_count]

        diagram_urls: list[str] = []
        for index, diagram_path in enumerate(diagram_paths, start=1):
            key = _build_subject_diagram_s3_key(
                subject_name,
                id_str,
                index,
                ext=diagram_path.suffix.lstrip(".") or "png",
            )
            content_type, _ = mimetypes.guess_type(diagram_path.name)
            await s3.upload_bytes(
                key,
                diagram_path.read_bytes(),
                content_type=content_type or "application/octet-stream",
            )
            diagrams_uploaded += 1
            diagram_urls.append(_build_diagram_public_url(s3_settings, key))

        rewritten = _rewrite_diagram_markers(content, diagram_urls)
        if rewritten != content:
            lesson_path.write_text(rewritten, encoding="utf-8")
            lessons_rewritten += 1

    return diagrams_uploaded, lessons_rewritten


async def _sync_subject_lessons_in_place(
    session: AsyncSession,
    subject_dir: Path,
    folder_id: uuid.UUID,
) -> list[tuple[str, str, Lesson, RoadmapNode]]:
    """Refresh all level-3 shared lessons in place for one seeded subject."""
    from sqlalchemy.orm import selectinload

    lessons_dir = subject_dir / "lessons"
    if not lessons_dir.is_dir():
        raise FileNotFoundError(f"Lessons dir not found: {lessons_dir}")

    stored_name_to_parts = _build_stored_name_map(subject_dir)
    nodes = list(
        (
            await session.execute(
                select(RoadmapNode)
                .where(
                    RoadmapNode.folder_id == folder_id,
                    RoadmapNode.level == 3,
                )
                .options(selectinload(RoadmapNode.lesson))
            )
        )
        .scalars()
        .all()
    )
    if not nodes:
        raise LookupError(
            f"No level-3 roadmap nodes found for subject folder {folder_id}"
        )

    lesson_nodes: list[tuple[str, str, Lesson, RoadmapNode]] = []
    for node in nodes:
        id_str, clean_name = stored_name_to_parts.get(
            node.name, _split_display_name(node.name)
        )
        content = _load_lesson_content(id_str, clean_name, lessons_dir)
        if content is None:
            raise FileNotFoundError(
                f"Lesson markdown not found for node {node.name!r} in {lessons_dir}"
            )

        display_name = f"{id_str} {clean_name}" if id_str else clean_name
        lesson = node.lesson
        if lesson is None:
            lesson = Lesson(
                user_id=None,
                name=display_name,
                description=None,
                content=content,
            )
            session.add(lesson)
            await session.flush()
            node.lesson_id = lesson.id
            node.lesson = lesson

        lesson.name = display_name
        lesson.content = content
        lesson.description = extract_description(content)
        await session.flush()
        await _parse_and_store_blocks(session, lesson.id, content)
        lesson_nodes.append((id_str, clean_name, lesson, node))

    return lesson_nodes


# ---------------------------------------------------------------------------
# User progress seeding
# ---------------------------------------------------------------------------


async def seed_progress_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Create progress=0 rows for all level-3 shared roadmap nodes for a user.

    Also creates LessonProgress(stars=0) rows for shared lessons.
    Idempotent: skips nodes/lessons that already have progress for this user.
    Returns the number of new roadmap progress rows created.
    """
    shared_folders = list(
        await db.scalars(select(Folder.id).where(Folder.user_id.is_(None)))
    )
    if not shared_folders:
        return 0

    lesson_node_ids = list(
        await db.scalars(
            select(RoadmapNode.id).where(
                RoadmapNode.folder_id.in_(shared_folders),
                RoadmapNode.level == 3,
            )
        )
    )
    if not lesson_node_ids:
        return 0

    existing = set(
        await db.scalars(
            select(RoadmapProgress.node_id).where(
                RoadmapProgress.user_id == user_id,
                RoadmapProgress.node_id.in_(lesson_node_ids),
            )
        )
    )

    new_rows = []
    for node_id in lesson_node_ids:
        if node_id not in existing:
            new_rows.append(
                RoadmapProgress(node_id=node_id, user_id=user_id, progress=0)
            )

    if new_rows:
        db.add_all(new_rows)
        await db.flush()

    lesson_ids = list(
        await db.scalars(
            select(RoadmapNode.lesson_id).where(
                RoadmapNode.folder_id.in_(shared_folders),
                RoadmapNode.level == 3,
                RoadmapNode.lesson_id.is_not(None),
            )
        )
    )
    if lesson_ids:
        existing_lesson_progress = set(
            await db.scalars(
                select(LessonProgress.lesson_id).where(
                    LessonProgress.user_id == user_id,
                    LessonProgress.lesson_id.in_(lesson_ids),
                )
            )
        )
        new_lesson_rows = [
            LessonProgress(lesson_id=lid, user_id=user_id, stars=0)
            for lid in lesson_ids
            if lid not in existing_lesson_progress
        ]
        if new_lesson_rows:
            db.add_all(new_lesson_rows)
            await db.flush()

    return len(new_rows)


# ---------------------------------------------------------------------------
# Exam seeding
# ---------------------------------------------------------------------------


async def seed_exams(
    session: AsyncSession,
    folder_id: uuid.UUID,
    subject_dir: Path,
) -> int:
    """Seed predefined exams from exams.json (idempotent).

    Each entry maps theme positions (1-based) to level-1 RoadmapNode IDs.
    Returns the number of exams created (skips already-existing ones).
    """
    import json
    from datetime import datetime as dt

    exams_file = subject_dir / "exams.json"
    if not exams_file.is_file():
        return 0

    exams_data = json.loads(exams_file.read_text(encoding="utf-8"))
    if not exams_data:
        return 0

    # Build position → level-1 node ID mapping for this folder
    l1_nodes = list(
        (
            await session.execute(
                select(RoadmapNode).where(
                    RoadmapNode.folder_id == folder_id,
                    RoadmapNode.level == 1,
                )
            )
        )
        .scalars()
        .all()
    )
    pos_to_id: dict[int, uuid.UUID] = {n.position: n.id for n in l1_nodes}

    # Fetch existing shared exams for idempotency / correction
    existing_exams: dict[str, Exam] = {
        e.name: e
        for e in (
            await session.scalars(
                select(Exam).where(
                    Exam.folder_id == folder_id,
                    Exam.user_id.is_(None),
                )
            )
        )
    }

    created = 0
    for entry in exams_data:
        name = entry["name"]
        node_ids = [pos_to_id[t - 1] for t in entry["themes"] if (t - 1) in pos_to_id]
        if not node_ids:
            logger.warning("Exam '%s': no matching theme nodes found, skipping", name)
            continue

        exam_date = dt.fromisoformat(entry["exam_date"])

        existing = existing_exams.get(name)
        if existing is not None:
            # Fix existing exam if node IDs differ (e.g. off-by-one correction)
            if set(existing.roadmap_nodes or []) != set(node_ids):
                existing.roadmap_nodes = node_ids
            if existing.exam_date != exam_date:
                existing.exam_date = exam_date
            continue

        session.add(
            Exam(
                user_id=None,
                folder_id=folder_id,
                name=name,
                exam_date=exam_date,
                roadmap_nodes=node_ids,
            )
        )
        created += 1

    if created:
        await session.flush()

    return created


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_stored_name_map(subject_dir: Path) -> dict[str, tuple[str, str]]:
    """Rebuild the shared stored display name to (id_str, clean_name) map."""
    roadmap_md = (subject_dir / "roadmap.md").read_text(encoding="utf-8")
    sections = parse_roadmap("", md=roadmap_md)
    stored_name_to_parts: dict[str, tuple[str, str]] = {}
    for section in sections:
        for sub in section.subsections:
            for lesson_data in sub.lessons:
                stored = (
                    f"{lesson_data.id_str} {lesson_data.name}"
                    if lesson_data.id_str
                    else lesson_data.name
                )
                stored_name_to_parts[stored] = (lesson_data.id_str, lesson_data.name)
        for lesson_data in section.lessons:
            stored = (
                f"{lesson_data.id_str} {lesson_data.name}"
                if lesson_data.id_str
                else lesson_data.name
            )
            stored_name_to_parts[stored] = (lesson_data.id_str, lesson_data.name)
    return stored_name_to_parts


_RP_PREFIX_RE = re.compile(r"^(?P<id>RP\s+\d+)\s+")
_OPTION_PREFIX_RE = re.compile(r"^(?P<id>[A-Z]\.\d+(?:\.\d+)*)\s+")


def _split_display_name(display_name: str) -> tuple[str, str]:
    """Split a stored display name into its lesson id and clean lesson name."""
    for pattern in (_LESSON_ID_PREFIX_RE, _RP_PREFIX_RE, _OPTION_PREFIX_RE):
        match = pattern.match(display_name)
        if match:
            id_str = match.group("id")
            return id_str, display_name[len(id_str) + 1 :]
    return "", display_name


def _extract_lesson_id_from_filename(path: Path) -> str:
    match = _LESSON_FILENAME_ID_RE.match(path.name)
    return match.group("id") if match else ""


def _count_diagram_markers(content: str) -> int:
    return sum(
        1 for line in content.splitlines() if _DIAGRAM_MARKER_RE.match(line.strip())
    )


def _find_ordered_diagram_paths(id_str: str, diagrams_dir: Path) -> list[Path]:
    """Return diagram files for one lesson id ordered by numeric suffix."""
    if not diagrams_dir.is_dir():
        return []

    by_ordinal: dict[int, Path] = {}
    for path in diagrams_dir.iterdir():
        if not path.is_file():
            continue
        match = _DIAGRAM_FILENAME_RE.match(path.name)
        if not match or match.group("lesson_id") != id_str:
            continue
        ordinal = int(match.group("ordinal"))
        if ordinal in by_ordinal:
            raise ValueError(
                f"Duplicate diagram ordinal {ordinal} for lesson {id_str} in {diagrams_dir}"
            )
        by_ordinal[ordinal] = path

    return [by_ordinal[n] for n in sorted(by_ordinal)]


def _rewrite_diagram_markers(content: str, diagram_urls: list[str]) -> str:
    """Insert or replace markdown image lines directly below [DIAGRAM: ...] markers."""
    marker_count = _count_diagram_markers(content)
    if marker_count != len(diagram_urls):
        raise ValueError(
            f"Diagram marker count mismatch: {marker_count} marker(s), {len(diagram_urls)} url(s)"
        )

    urls = iter(diagram_urls)
    out: list[str] = []
    lines = content.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if _DIAGRAM_MARKER_RE.match(line.strip()):
            if i + 1 < len(lines) and _MARKDOWN_IMAGE_RE.match(lines[i + 1].strip()):
                i += 1
            out.append(f"![Diagram]({next(urls)})\n")
        i += 1

    return "".join(out)


def _subject_media_slug(subject_name: str) -> str:
    if subject_name in _SHARED_SUBJECT_MEDIA_SLUGS:
        return _SHARED_SUBJECT_MEDIA_SLUGS[subject_name]
    return re.sub(r"[^a-z0-9]+", "-", subject_name.lower()).strip("-")


def _build_subject_diagram_s3_key(
    subject_name: str,
    lesson_id: str,
    ordinal: int,
    *,
    ext: str = "png",
) -> str:
    return f"diagrams/{_subject_media_slug(subject_name)}/{lesson_id}-{ordinal}.{ext.lower()}"


def _build_diagram_public_url(settings: S3Settings, key: str) -> str:
    """Build a stable public URL for a bucket object using configured S3 settings."""
    parsed = urlparse(settings.endpoint_url.strip())
    scheme = parsed.scheme or ("https" if settings.use_ssl else "http")
    host = parsed.netloc or parsed.path
    if not host:
        raise ValueError("S3 endpoint_url is required to build a public object URL")

    key_path = quote(key, safe="/")

    if settings.use_path_style:
        base = settings.endpoint_url.rstrip("/")
        return f"{base}/{settings.bucket}/{key_path}"

    if "amazonaws.com" in host and settings.region:
        return f"{scheme}://{settings.bucket}.s3.{settings.region}.amazonaws.com/{key_path}"

    return f"{scheme}://{settings.bucket}.{host}/{key_path}"


async def _get_or_create_shared_folder(session: AsyncSession, name: str) -> Folder:
    """Get or create a shared a_level folder by name."""
    folder = await session.scalar(
        select(Folder).where(
            Folder.name == name,
            Folder.type == FolderType.a_level,
            Folder.user_id.is_(None),
        )
    )
    if folder:
        return folder
    folder = Folder(user_id=None, name=name, type=FolderType.a_level)
    session.add(folder)
    await session.flush()
    return folder


async def _create_lesson_and_node(
    session: AsyncSession,
    folder_id: uuid.UUID,
    parent_id: uuid.UUID,
    name: str,
    position: int,
    id_str: str,
    lessons_dir: Path,
) -> tuple[Lesson, RoadmapNode]:
    """Create a Lesson record and a level-3 RoadmapNode linked to it."""
    # Display name includes the id_str prefix to match the filename convention,
    # e.g. "2.3.1 Short-run AS" rather than bare "Short-run AS".
    display_name = f"{id_str} {name}" if id_str else name

    content = _load_lesson_content(id_str, name, lessons_dir)
    description = None

    if content is not None:
        description = extract_description(content)
        logger.info("Loaded lesson %s (%s)", id_str, name)
    else:
        content = f"# {display_name}\n\n{_PLACEHOLDER_SUFFIX}"

    lesson = Lesson(
        user_id=None,
        name=display_name,
        description=description,
        content=content,
    )
    session.add(lesson)
    await session.flush()

    if description is not None:  # proxy for "real content loaded"
        await _parse_and_store_blocks(session, lesson.id, content)

    node = RoadmapNode(
        folder_id=folder_id,
        parent_id=parent_id,
        level=3,
        name=display_name,
        position=position,
        lesson_id=lesson.id,
    )
    session.add(node)
    await session.flush()

    return lesson, node


async def _parse_and_store_blocks(
    session: AsyncSession,
    lesson_id: uuid.UUID,
    content: str,
) -> None:
    """Parse lesson content into blocks and feynman blocks, store in DB."""
    from sqlalchemy import delete as sa_delete

    await session.execute(
        sa_delete(LessonBlock).where(LessonBlock.lesson_id == lesson_id)
    )
    await session.execute(
        sa_delete(FeynmanBlock).where(FeynmanBlock.lesson_id == lesson_id)
    )

    parsed_blocks = parse_lesson_blocks(content)
    for pb in parsed_blocks:
        session.add(
            LessonBlock(
                lesson_id=lesson_id,
                user_id=None,
                content=pb.content,
                block_number=pb.block_number,
                block_id=pb.block_id or None,
                title=pb.title or None,
                is_summary=pb.is_summary,
            )
        )

    parsed_feynman = parse_feynman_blocks(content)
    for pf in parsed_feynman:
        session.add(
            FeynmanBlock(
                lesson_id=lesson_id,
                user_id=None,
                scope=pf.scope,
                question=pf.question,
                points=pf.points,
            )
        )

    lesson = await session.get(Lesson, lesson_id)
    if lesson:
        lesson.num_blocks = len(parsed_blocks)

    await session.flush()


def _load_lesson_content(id_str: str, name: str, lessons_dir: Path) -> str | None:
    """Try to load lesson content from lessons_dir/{id_str} {name}.md."""
    if not lessons_dir.is_dir():
        return None

    # Exact match first
    path = lessons_dir / f"{id_str} {name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")

    # Glob fallback: any file starting with the id_str
    if id_str:
        candidates = list(lessons_dir.glob(f"{id_str} *.md"))
        if candidates:
            return candidates[0].read_text(encoding="utf-8")

    return None
