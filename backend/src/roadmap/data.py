"""Parse docs/physics_roadmap.md into structured roadmap data for seeding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent / "roadmaps"


@dataclass
class LessonData:
    """A level-3 leaf node (lesson/topic)."""

    name: str
    position: int
    id_str: str = ""  # e.g., "1.1", "2.1.3", "RP 1"


@dataclass
class SubsectionData:
    """A level-2 node (subsection within a section)."""

    name: str
    position: int
    lessons: list[LessonData] = field(default_factory=list)


@dataclass
class SectionData:
    """A level-1 node (top-level section)."""

    name: str
    position: int
    subsections: list[SubsectionData] = field(default_factory=list)
    lessons: list[LessonData] = field(
        default_factory=list
    )  # direct lessons (no subsection)


_THEME_RE = re.compile(r"^##\s+(.+)$")  # ## Theme … → level 1
_SECTION_RE = re.compile(r"^###\s+(.+)$")  # ### 1.1 … → level 2
_SUBSECTION_RE = re.compile(r"^####\s+(.+)$")  # #### 2.1 … → level 2
_TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s\-|]+\|$")
_TABLE_HEADER_RE = re.compile(r"^\|\s*ID\s*\|", re.IGNORECASE)

# Strips leading numeric ID prefixes from section/subsection headings.
# Matches patterns like "1.1: ", "2.3.1: ", "RP 1. " etc.
_HEADING_ID_RE = re.compile(r"^[\d]+(\.\d+)*[.:]\s*")

# ## headings to skip (non-content metadata sections)
_SKIP_THEMES = {"overview"}


def parse_roadmap(subject: str, md: str | None = None) -> list[SectionData]:
    """Parse a roadmap markdown into structured section data.

    *subject* selects the file inside ``roadmaps/{subject}.md``.
    If *md* is provided directly, it is used instead.
    """
    if md is None:
        md = (_DOCS_DIR / f"{subject}.md").read_text(encoding="utf-8")

    sections: list[SectionData] = []
    current_section: SectionData | None = None
    current_subsection: SubsectionData | None = None
    lesson_pos = 0

    for raw_line in md.splitlines():
        line = raw_line.strip()

        # Skip empty lines and horizontal rules
        if not line or line.startswith("---"):
            continue

        # Level 1: ## Theme / Top-level grouping
        theme_match = _THEME_RE.match(line)
        if theme_match and not line.startswith("###"):
            raw_name = theme_match.group(1).strip()
            # Skip non-content headings like "## Overview"
            if raw_name.lower().rstrip(":") in _SKIP_THEMES:
                continue
            name = _HEADING_ID_RE.sub("", raw_name)
            current_section = SectionData(
                name=name,
                position=len(sections),
            )
            sections.append(current_section)
            current_subsection = None
            lesson_pos = 0
            continue

        # Level 2: ### Section or #### Subsection
        subsection_match = _SUBSECTION_RE.match(line)
        section_match = _SECTION_RE.match(line) if not subsection_match else None
        if (section_match or subsection_match) and current_section is not None:
            match = subsection_match or section_match
            name = match.group(1).strip()
            current_subsection = SubsectionData(
                name=name,
                position=len(current_section.subsections),
            )
            current_section.subsections.append(current_subsection)
            lesson_pos = 0
            continue

        # Table header or separator — skip but mark we're in a table
        if _TABLE_HEADER_RE.match(line) or _TABLE_SEPARATOR_RE.match(line):
            continue

        # Table row — level 3 lesson
        row_match = _TABLE_ROW_RE.match(line)
        if row_match and current_section is not None:
            _id_col = row_match.group(1).strip()
            lesson_name = row_match.group(2).strip()

            lesson = LessonData(name=lesson_name, position=lesson_pos, id_str=_id_col)
            lesson_pos += 1

            if current_subsection is not None:
                current_subsection.lessons.append(lesson)
            else:
                current_section.lessons.append(lesson)

    return sections


def parse_physics_roadmap(md: str | None = None) -> list[SectionData]:
    """Convenience wrapper — parse the physics roadmap."""
    return parse_roadmap("physics", md)


def parse_economics_roadmap(md: str | None = None) -> list[SectionData]:
    """Convenience wrapper — parse the economics roadmap."""
    return parse_roadmap("economics", md)
