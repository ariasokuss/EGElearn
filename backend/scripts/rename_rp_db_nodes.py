"""One-shot: rename existing RP roadmap nodes to match the new short
roadmap.md names. Pairs each old 'RP NN Long Name' DB node with the
corresponding new short name, by RP number.
"""

from __future__ import annotations

import asyncio
import logging
import re
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

from sqlalchemy import select

from src.config import get_settings
from src.core.db import create_engine, create_session_factory
from src.core.logging import configure_logging
from src.files.models import Folder
from src.learning.models import Lesson
from src.roadmap.models import RoadmapNode

logger = logging.getLogger(__name__)


# Same mappings as scripts/rename_rp_files.py
CHEM_OLD_TO_NEW = {
    1: "Volumetric solution and acid-base titration",
    2: "Enthalpy change by calorimetry",
    3: "Rate and temperature",
    7: "Rate of reaction methods",
    8: "Electrochemical cell EMF",
    9: "Acid-base pH curves",
    4: "Cation and anion tests",
    11: "Transition metal ion tests",
    5: "Distillation of a reaction product",
    6: "Organic functional group tests",
    10: "Organic product preparation and purity",
    12: "Thin-layer chromatography",
}


def parse_new_rp_names(roadmap_md: str) -> list[str]:
    names: list[str] = []
    for line in roadmap_md.splitlines():
        m = re.match(r"^\|\s*RP\s*\|\s*(.+?)\s*\|$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def build_old_num_to_new_name(subject: str) -> dict[int, str]:
    """For Biology and Physics: positional. For Chemistry: explicit."""
    if subject == "AQA A-Level Chemistry":
        return CHEM_OLD_TO_NEW
    md = (
        Path("/Users/ivan/Developer/novalearn/docs/A-Level")
        / subject
        / "roadmap.md"
    ).read_text(encoding="utf-8")
    new_names = parse_new_rp_names(md)
    return {i + 1: name for i, name in enumerate(new_names)}


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)

    try:
        for subject in (
            "AQA A-Level Biology",
            "AQA A-Level Physics",
            "AQA A-Level Chemistry",
        ):
            mapping = build_old_num_to_new_name(subject)
            async with session_factory() as session:
                folder = await session.scalar(
                    select(Folder).where(
                        Folder.name == subject, Folder.user_id.is_(None)
                    )
                )
                if folder is None:
                    print(f"[{subject}] folder not found")
                    continue
                # Find RP nodes (name starts with "RP NN ")
                nodes = list(
                    (
                        await session.execute(
                            select(RoadmapNode).where(
                                RoadmapNode.folder_id == folder.id,
                                RoadmapNode.level == 3,
                                RoadmapNode.name.like("RP %"),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                renamed = 0
                for node in nodes:
                    m = re.match(r"^RP\s+(\d+)\s+", node.name)
                    if not m:
                        continue
                    n = int(m.group(1))
                    new_short = mapping.get(n)
                    if not new_short:
                        continue
                    new_full = f"RP {new_short}"
                    if node.name == new_full:
                        continue
                    print(f"  [{subject}] {node.name!r} → {new_full!r}")
                    node.name = new_full
                    if node.lesson_id is not None:
                        lesson = await session.get(Lesson, node.lesson_id)
                        if lesson is not None:
                            lesson.name = new_full
                    renamed += 1
                await session.commit()
                print(f"[{subject}] renamed {renamed} RP nodes")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
