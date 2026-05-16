"""Seed pre-authored lesson tests from JSON files into the database.

Called during the A-Level seed pipeline.  Each subject folder contains a
tests/ directory with files named:

    {id_str} {lesson_name}_test.json
    e.g. "1.1.1 Economics as a social science_test.json"

Creates shared TestTemplate + TestQuestion rows (user_id=NULL) for each
matched lesson.  Idempotent — clears existing shared lesson templates for the
folder before re-inserting.

Field compatibility
-------------------
* New economics format uses ``"correct_option": 2``  (1-indexed: A=1 … D=4)
* Legacy physics format uses ``"correct_option_index": 1``  (0-indexed)
Both are handled; the stored value is always 0-indexed ``correct_option_index``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.learning.models import Lesson
from src.learning.tests.models import TestTemplate, TestQuestion
from src.roadmap.models import RoadmapNode

logger = logging.getLogger(__name__)


def _compute_item_id(node_id: uuid.UUID | None, question_text: str) -> str:
    import re

    normalized = re.sub(r"\s+", " ", question_text.strip().lower())
    raw = f"{node_id or 'none'}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _resolve_test_file(id_str: str, name: str, tests_dir: Path) -> Path | None:
    """Locate the test JSON for a lesson using direct filename lookup."""
    # Exact match
    exact = tests_dir / f"{id_str} {name}_test.json"
    if exact.is_file():
        return exact

    # Glob fallback: any file starting with id_str
    if id_str:
        candidates = list(tests_dir.glob(f"{id_str} *_test.json"))
        if candidates:
            return candidates[0]

    return None


def _correct_option_index(q: dict) -> int | None:
    """Return 0-indexed correct option, supporting both field name conventions."""
    # Legacy physics: already 0-indexed
    legacy = q.get("correct_option_index")
    if legacy is not None:
        return int(legacy)

    # New economics: 1-indexed (A=1, B=2, C=3, D=4) → convert to 0-indexed
    new = q.get("correct_option")
    if new is not None:
        return int(new) - 1

    return None


async def seed_subject_tests(
    session: AsyncSession,
    folder_id: uuid.UUID,
    tests_dir: Path,
    lesson_nodes: list[tuple[str, str, "Lesson", "RoadmapNode"]],
) -> int:
    """Seed pre-authored tests for all lessons in a subject folder.

    Parameters
    ----------
    session:
        Active async DB session.
    folder_id:
        UUID of the shared folder this subject belongs to.
    tests_dir:
        Path to the subject's tests/ directory
        (e.g. docs/A-Level/Edexcel A-Level Economics/tests/).
    lesson_nodes:
        List of (id_str, name, Lesson, RoadmapNode) tuples produced during
        the main seeding loop — provides direct access to id_str for filename
        resolution without any fuzzy matching.

    Returns
    -------
    int
        Number of lesson tests seeded.
    """
    if not tests_dir.is_dir():
        logger.warning("Tests dir not found: %s", tests_dir)
        return 0

    # Clear existing shared lesson test templates for this folder
    from sqlalchemy import delete

    await session.execute(
        delete(TestTemplate).where(
            TestTemplate.folder_id == folder_id,
            TestTemplate.user_id.is_(None),
            TestTemplate.type == "lesson_test",
        )
    )
    await session.flush()

    seeded = 0

    for id_str, name, lesson, node in lesson_nodes:
        test_file = _resolve_test_file(id_str, name, tests_dir)
        if not test_file:
            logger.debug("No test file found for %s (%s)", id_str, name)
            continue

        with open(test_file, encoding="utf-8") as f:
            questions_data = json.load(f)

        if not isinstance(questions_data, list) or not questions_data:
            logger.warning("Empty or invalid test file: %s", test_file)
            continue

        total_marks = sum(q.get("points", 1) for q in questions_data)

        template = TestTemplate(
            user_id=None,
            folder_id=folder_id,
            lesson_id=lesson.id,
            name=f"Lesson Test: {name}",
            type="lesson_test",
            status="ready",
            node_ids=[node.id],
            total_questions=len(questions_data),
            total_marks=total_marks,
        )
        session.add(template)
        await session.flush()

        for idx, q in enumerate(questions_data):
            tq = TestQuestion(
                template_id=template.id,
                node_ids=[node.id],
                item_id=_compute_item_id(node.id, q.get("question", "")),
                index=idx,
                type=q.get("type", "short"),
                question=q.get("question", ""),
                options=q.get("options"),
                correct_option_index=_correct_option_index(q),
                model_answer=q.get("model_answer", ""),
                mark_scheme=q.get("mark_scheme"),
                hint=q.get("hint"),
                points=1 if q.get("type") == "mcq" else min(q.get("points", 1), 25),
                sources=q.get("sources"),
                context=q.get("context"),
            )
            session.add(tq)

        seeded += 1
        logger.info(
            "Seeded test for '%s': %d questions, %d marks",
            name,
            len(questions_data),
            total_marks,
        )

    return seeded
