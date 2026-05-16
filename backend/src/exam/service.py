"""Exam service — list, create, update, and delete exams."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.exam.models import Exam
from src.exam.schemas import ExamCreate, ExamUpdate, RoadmapNodeOut
from src.roadmap.models import RoadmapNode, RoadmapProgress


class ExamError(Exception):
    """Raised for business-logic failures in the exam domain."""


async def _expand_nodes(
    db: AsyncSession,
    node_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Expand section/subsection IDs into their leaf lesson (level-3) nodes.

    Level-3 nodes pass through unchanged. Section (level 1) and subsection
    (level 2) nodes are replaced by all their level-3 descendants.
    Returns a deduplicated list preserving original level-3 entries.
    """
    if not node_ids:
        return node_ids

    nodes_result = await db.scalars(
        select(RoadmapNode).where(RoadmapNode.id.in_(node_ids))
    )
    nodes = {n.id: n for n in nodes_result}

    expanded: set[uuid.UUID] = set()
    l1_ids: list[uuid.UUID] = []
    l2_ids: list[uuid.UUID] = []

    for node_id in node_ids:
        node = nodes.get(node_id)
        if node is None or node.level == 3:
            expanded.add(node_id)
        elif node.level == 1:
            l1_ids.append(node_id)
        elif node.level == 2:
            l2_ids.append(node_id)

    # Batch: for level-1 nodes, fetch all direct children (l2 + l3)
    if l1_ids:
        children_of_l1 = await db.scalars(
            select(RoadmapNode).where(
                RoadmapNode.parent_id.in_(l1_ids),
            )
        )
        for child in children_of_l1:
            if child.level == 3:
                expanded.add(child.id)
            elif child.level == 2:
                l2_ids.append(child.id)

    # Batch: for all level-2 nodes (original + discovered), fetch l3 children
    if l2_ids:
        l3_via_l2 = await db.scalars(
            select(RoadmapNode).where(
                RoadmapNode.parent_id.in_(l2_ids),
                RoadmapNode.level == 3,
            )
        )
        expanded.update(n.id for n in l3_via_l2)

    return list(expanded)


async def bulk_exam_progress(
    db: AsyncSession,
    exams: list[Exam],
    user_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """Return a mapping of exam_id → average progress (0-100) for *user_id*.

    Fetches all relevant RoadmapProgress rows in a single query, then
    aggregates per-exam without further round-trips.
    """
    if not exams:
        return {}

    # Collect all unique node IDs across all exams, remembering which exam
    # each node belongs to.
    node_to_exams: dict[uuid.UUID, list[uuid.UUID]] = {}
    for exam in exams:
        for node_id in exam.roadmap_nodes or []:
            node_to_exams.setdefault(node_id, []).append(exam.id)

    all_node_ids = list(node_to_exams)
    if not all_node_ids:
        return {exam.id: 0 for exam in exams}

    rows = await db.execute(
        select(
            RoadmapProgress.node_id,
            RoadmapProgress.mastery,
            RoadmapProgress.progress,
        ).where(
            RoadmapProgress.node_id.in_(all_node_ids),
            RoadmapProgress.user_id == user_id,
        )
    )
    # node_id -> mastery (preferred) or legacy progress
    node_progress: dict[uuid.UUID, int] = {
        row.node_id: int(round(row.mastery)) if row.mastery is not None else row.progress
        for row in rows
    }

    result: dict[uuid.UUID, int] = {}
    for exam in exams:
        nodes = exam.roadmap_nodes or []
        if not nodes:
            result[exam.id] = 0
            continue
        total = sum(node_progress.get(n, 0) for n in nodes)
        result[exam.id] = int(round(total / len(nodes)))

    return result


async def get_exams_for_folder(
    db: AsyncSession,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Exam]:
    """Return all exams in a folder visible to the user (personal + common).

    Shared exams stamped with the optional-themes sentinel (microsecond 929929)
    are hidden when the user already has a personal exam with the same sentinel
    — the personal one represents the user's optional-topic selection and
    replaces the shared baseline.
    """
    result = await db.scalars(
        select(Exam)
        .where(
            Exam.folder_id == folder_id,
            or_(Exam.user_id == user_id, Exam.user_id.is_(None)),
        )
        .order_by(Exam.exam_date.asc())
    )
    exams = list(result)
    user_has_optional = any(
        e.user_id == user_id
        and e.exam_date is not None
        and e.exam_date.microsecond == 929929
        for e in exams
    )
    if user_has_optional:
        exams = [
            e
            for e in exams
            if not (
                e.user_id is None
                and e.exam_date is not None
                and e.exam_date.microsecond == 929929
            )
        ]
    return exams


async def fetch_nodes_for_exam(
    db: AsyncSession,
    node_ids: list[uuid.UUID],
) -> list[RoadmapNodeOut]:
    """Fetch RoadmapNode rows for the given IDs, preserving exam order."""
    if not node_ids:
        return []
    rows = await db.scalars(select(RoadmapNode).where(RoadmapNode.id.in_(node_ids)))
    by_id = {n.id: n for n in rows}
    return [
        RoadmapNodeOut.model_validate(by_id[nid]) for nid in node_ids if nid in by_id
    ]


async def get_exam(
    db: AsyncSession,
    exam_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Exam | None:
    """Return the exam if it belongs to the user (or is a common exam)."""
    return await db.scalar(
        select(Exam).where(
            Exam.id == exam_id,
            or_(Exam.user_id == user_id, Exam.user_id.is_(None)),
        )
    )


async def update_exam(
    db: AsyncSession,
    exam_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ExamUpdate,
) -> Exam:
    """Partially update a personal exam owned by user_id."""
    exam = await db.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.user_id == user_id)
    )
    if exam is None:
        raise ExamError("Exam not found or not editable")

    if data.name is not None:
        exam.name = data.name
    if data.exam_date is not None:
        exam.exam_date = data.exam_date
    if data.roadmap_nodes is not None:
        exam.roadmap_nodes = await _expand_nodes(db, data.roadmap_nodes)

    await db.commit()
    await db.refresh(exam)
    return exam


async def delete_exam(
    db: AsyncSession,
    exam_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete a personal exam owned by user_id."""
    exam = await db.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.user_id == user_id)
    )
    if exam is None:
        raise ExamError("Exam not found or not editable")

    await db.delete(exam)
    await db.commit()


async def create_exam(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: ExamCreate,
) -> Exam:
    """Create a personal exam for the current user.

    Section/subsection node IDs in roadmap_nodes are automatically expanded
    to all their level-3 lesson descendants before storing.
    """
    resolved_nodes = await _expand_nodes(db, data.roadmap_nodes)

    exam = Exam(
        user_id=user_id,
        folder_id=data.folder_id,
        name=data.name,
        exam_date=data.exam_date,
        roadmap_nodes=resolved_nodes,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam
