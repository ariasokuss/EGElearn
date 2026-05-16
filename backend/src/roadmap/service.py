"""Roadmap service — read roadmap tree and update per-user progress."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.files.models import Folder
from src.learning.models import Lesson, LessonProgress
from src.roadmap.models import RoadmapNode, RoadmapProgress
from src.roadmap.optional_themes import OPTIONAL_THEMES
from src.roadmap.schemas import (
    OptionalThemeOption,
    OptionalThemesOut,
    RoadmapLessonOut,
    RoadmapOut,
    RoadmapSectionOut,
    RoadmapSubsectionOut,
)

logger = logging.getLogger(__name__)


def _build_lesson_out(
    node: RoadmapNode,
    rp: RoadmapProgress | None,
    lp: LessonProgress | None,
    *,
    lesson_description: str | None = None,
) -> RoadmapLessonOut:
    """Build a RoadmapLessonOut from a node and its optional progress row."""
    return RoadmapLessonOut(
        id=node.id,
        name=node.name,
        lesson_id=node.lesson_id,
        description=lesson_description,
        progress=rp.progress if rp else 0,
        mastery=rp.mastery if rp else None,
        confidence=rp.confidence if rp else None,
        study_star=lp.study_star if lp else False,
        feynman_star=lp.feynman_star if lp else False,
        test_star=lp.test_star if lp else False,
    )


class RoadmapError(Exception):
    """Raised for business-logic failures in the roadmap domain."""


async def get_roadmap(
    db: AsyncSession,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RoadmapOut:
    """Load the full roadmap tree for a folder with the user's progress."""
    # 1. Load all nodes for this folder
    nodes_result = await db.scalars(
        select(RoadmapNode)
        .where(RoadmapNode.folder_id == folder_id)
        .order_by(RoadmapNode.level, RoadmapNode.position)
    )
    all_nodes = list(nodes_result)

    if not all_nodes:
        raise RoadmapError("Roadmap not found for this folder")

    lesson_node_ids = [n.id for n in all_nodes if n.level == 3]
    lesson_ids = [n.lesson_id for n in all_nodes if n.level == 3 and n.lesson_id is not None]
    progress_map: dict[uuid.UUID, RoadmapProgress] = {}
    lesson_progress_map: dict[uuid.UUID, LessonProgress] = {}

    if lesson_node_ids:
        progress_result = await db.scalars(
            select(RoadmapProgress).where(
                RoadmapProgress.user_id == user_id,
                RoadmapProgress.node_id.in_(lesson_node_ids),
            )
        )
        for p in progress_result:
            progress_map[p.node_id] = p
    if lesson_ids:
        lesson_progress_result = await db.scalars(
            select(LessonProgress).where(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id.in_(lesson_ids),
            )
        )
        for lp in lesson_progress_result:
            lesson_progress_map[lp.lesson_id] = lp

    lesson_descriptions: dict[uuid.UUID, str | None] = {}
    if lesson_ids:
        lesson_rows = await db.scalars(select(Lesson).where(Lesson.id.in_(lesson_ids)))
        for row in lesson_rows:
            lesson_descriptions[row.id] = row.description

    # 3. Build lookup tables
    children_by_parent: dict[uuid.UUID | None, list[RoadmapNode]] = {}
    for n in all_nodes:
        children_by_parent.setdefault(n.parent_id, []).append(n)

    # 4. Assemble the tree
    sections: list[RoadmapSectionOut] = []
    total_lessons = 0
    completed_lessons = 0
    progress_sum = 0

    for section_node in children_by_parent.get(None, []):
        if section_node.level != 1:
            continue

        section_subsections: list[RoadmapSubsectionOut] = []
        section_direct_lessons: list[RoadmapLessonOut] = []

        for child in children_by_parent.get(section_node.id, []):
            if child.level == 2:
                # Subsection — collect its lessons
                sub_lessons: list[RoadmapLessonOut] = []
                for lesson_node in children_by_parent.get(child.id, []):
                    if lesson_node.level == 3:
                        rp = progress_map.get(lesson_node.id)
                        lp = (
                            lesson_progress_map.get(lesson_node.lesson_id)
                            if lesson_node.lesson_id is not None
                            else None
                        )
                        _ld = (
                            lesson_descriptions.get(lesson_node.lesson_id)
                            if lesson_node.lesson_id
                            else None
                        )
                        sub_lessons.append(
                            _build_lesson_out(
                                lesson_node, rp, lp, lesson_description=_ld
                            )
                        )
                        prog = (
                            rp.mastery
                            if rp and rp.mastery is not None
                            else (rp.progress if rp else 0)
                        )
                        total_lessons += 1
                        progress_sum += prog
                        if prog >= 100:
                            completed_lessons += 1

                section_subsections.append(
                    RoadmapSubsectionOut(
                        id=child.id,
                        name=child.name,
                        lessons=sub_lessons,
                    )
                )

            elif child.level == 3:
                # Direct lesson under section
                rp = progress_map.get(child.id)
                lp = (
                    lesson_progress_map.get(child.lesson_id)
                    if child.lesson_id is not None
                    else None
                )
                _ld = (
                    lesson_descriptions.get(child.lesson_id)
                    if child.lesson_id
                    else None
                )
                section_direct_lessons.append(
                    _build_lesson_out(child, rp, lp, lesson_description=_ld)
                )
                prog = (
                    rp.mastery
                    if rp and rp.mastery is not None
                    else (rp.progress if rp else 0)
                )
                total_lessons += 1
                progress_sum += prog
                if prog >= 100:
                    completed_lessons += 1

        sections.append(
            RoadmapSectionOut(
                id=section_node.id,
                name=section_node.name,
                subsections=section_subsections,
                lessons=section_direct_lessons,
            )
        )

    overall = (progress_sum / total_lessons) if total_lessons > 0 else 0.0

    return RoadmapOut(
        folder_id=folder_id,
        sections=sections,
        total_lessons=total_lessons,
        completed_lessons=completed_lessons,
        overall_progress=round(overall, 2),
    )


async def update_progress(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
    progress: int,
) -> int:
    """Update (upsert) progress for a level-3 roadmap node. Returns the new progress value."""
    # Validate the node exists and is level 3
    node = await db.get(RoadmapNode, node_id)
    if node is None:
        raise RoadmapError("Roadmap node not found")
    if node.level != 3:
        raise RoadmapError("Progress can only be set on lesson nodes (level 3)")

    # Derive stars from progress (inverse of _STARS_TO_PROGRESS mapping)
    if progress >= 100:
        stars = 3
    elif progress >= 66:
        stars = 2
    elif progress >= 33:
        stars = 1
    else:
        stars = 0

    # Upsert progress
    stmt = (
        pg_insert(RoadmapProgress)
        .values(
            node_id=node_id,
            user_id=user_id,
            progress=progress,
            stars=stars,
        )
        .on_conflict_do_update(
            constraint="uq_roadmap_progress_node_user",
            set_={"progress": progress, "stars": stars},
        )
    )
    await db.execute(stmt)
    await db.commit()

    return progress


async def resolve_optional_themes(
    db: AsyncSession,
    folder_id: uuid.UUID,
) -> OptionalThemesOut | None:
    """Return resolved optional theme blocks for a folder, or None if not configured."""
    folder = await db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        return None

    config = OPTIONAL_THEMES.get(folder.name)
    if config is None:
        return None

    all_backend_names: list[str] = []
    for block in config["blocks"]:
        for option in block:
            all_backend_names.append(
                option["backend_name"] if isinstance(option, dict) else option
            )

    rows = await db.scalars(
        select(RoadmapNode).where(
            RoadmapNode.folder_id == folder_id,
            RoadmapNode.level.in_([1, 2]),
            RoadmapNode.name.in_(all_backend_names),
        )
    )
    nodes_by_name: dict[str, uuid.UUID] = {n.name: n.id for n in rows}

    resolved_blocks: list[list[OptionalThemeOption]] = []
    for block in config["blocks"]:
        resolved_block: list[OptionalThemeOption] = []
        for option in block:
            if isinstance(option, dict):
                display_name: str = option["name"]
                backend_name: str = option["backend_name"]
            else:
                display_name = option
                backend_name = option
            node_id = nodes_by_name.get(backend_name)
            if node_id is None:
                continue
            resolved_block.append(OptionalThemeOption(id=node_id, name=display_name))
        if resolved_block:
            resolved_blocks.append(resolved_block)

    return OptionalThemesOut(
        title=config["title"],
        exam_date=config["exam_date"],
        blocks=resolved_blocks,
    )


class RoadmapError(Exception):
    """Raised for business-logic failures in the roadmap domain."""


async def apply_optional_themes_selection(
    db: AsyncSession,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
    selected_option_ids: list[uuid.UUID],
):
    """Upsert a per-user optional-themes exam for the folder.

    Combines the subject's `base_themes` (if any) with the user's option picks,
    expands to leaf lesson nodes, and stores a personal exam stamped with the
    config's sentinel exam_date so it shadows any shared seeded exam.
    """
    from datetime import datetime as dt

    from src.exam.models import Exam
    from src.exam.service import _expand_nodes

    folder = await db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise RoadmapError("Folder not found")

    config = OPTIONAL_THEMES.get(folder.name)
    if config is None:
        raise RoadmapError("No optional themes configured for this folder")

    # Build pool of valid option node IDs (level 1 or 2 nodes named in blocks)
    all_backend_names: list[str] = []
    for block in config["blocks"]:
        for option in block:
            all_backend_names.append(
                option["backend_name"] if isinstance(option, dict) else option
            )
    pool_rows = await db.scalars(
        select(RoadmapNode).where(
            RoadmapNode.folder_id == folder_id,
            RoadmapNode.level.in_([1, 2]),
            RoadmapNode.name.in_(all_backend_names),
        )
    )
    pool_ids = {n.id for n in pool_rows}

    selected_set = set(selected_option_ids)
    if not selected_set.issubset(pool_ids):
        raise RoadmapError("One or more selected option IDs are not valid for this folder")

    # Resolve base themes (positional level-1 sections) when configured
    base_node_ids: list[uuid.UUID] = []
    base_themes = config.get("base_themes") or []
    if base_themes:
        l1_rows = await db.scalars(
            select(RoadmapNode).where(
                RoadmapNode.folder_id == folder_id,
                RoadmapNode.level == 1,
            )
        )
        pos_to_id = {n.position: n.id for n in l1_rows}
        base_node_ids = [pos_to_id[t - 1] for t in base_themes if (t - 1) in pos_to_id]

    final_top_ids = list({*base_node_ids, *selected_set})
    final_nodes = await _expand_nodes(db, final_top_ids)

    exam_date = dt.fromisoformat(config["exam_date"])

    # Find this user's existing optional-themes exam (sentinel: microsecond == 929929)
    user_exams = await db.scalars(
        select(Exam).where(Exam.folder_id == folder_id, Exam.user_id == user_id)
    )
    existing = next(
        (
            e
            for e in user_exams
            if e.exam_date is not None and e.exam_date.microsecond == 929929
        ),
        None,
    )

    if existing is not None:
        existing.name = config["title"]
        existing.exam_date = exam_date
        existing.roadmap_nodes = final_nodes
        await db.commit()
        await db.refresh(existing)
        return existing

    exam = Exam(
        user_id=user_id,
        folder_id=folder_id,
        name=config["title"],
        exam_date=exam_date,
        roadmap_nodes=final_nodes,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam
