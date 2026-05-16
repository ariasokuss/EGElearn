"""Lesson markdown parser — extracts custom directive blocks from lesson content."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class InlineQuestionParsed:
    """A mini-question extracted from a ::: question directive in lesson markdown."""

    inline_key: str  # "block_id:question_index"
    type: str  # "mcq" | "short"
    question: str
    options: list[str] | None
    correct_option_index: int | None
    model_answer: str
    mark_scheme: str | None
    points: int
    feedback: str | None


@dataclass
class FeynmanBlockParsed:
    scope: list[int]
    question: str
    points: list[str]


@dataclass
class ParsedLessonBlock:
    block_number: int
    content: str
    is_summary: bool
    block_id: str = ""  # from <part id="..."> or "intro" / "summary"
    title: str = ""  # from <part title="..."> or "Introduction" / "Quick Recap"


@dataclass
class LessonTheme:
    """A lesson part extracted from XML tags or <!-- PART N: Title --> markers."""

    number: int
    title: str
    content: str
    block_id: str = ""  # from <part id="..."> when using new XML format


# ---------------------------------------------------------------------------
# New XML-tag format:  <part id="slug" title="Human Title"> ... </part>
# ---------------------------------------------------------------------------
_XML_PART_RE = re.compile(
    r'<part\s+id="([^"]+)"\s+title="([^"]+)">(.*?)</part>',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Legacy comment format (physics):  <!-- PART N: Title --> ... <!-- /PART N -->
# ---------------------------------------------------------------------------
_PART_RE = re.compile(
    r"<!--\s*PART\s+(\d+):[^>]*-->\n(.*?)<!--\s*/PART\s+\1\s*-->",
    re.DOTALL,
)
_PART_TITLE_RE = re.compile(
    r"<!--\s*PART\s+(\d+):\s*([^>]*?)\s*-->\n(.*?)<!--\s*/PART\s+\1\s*-->",
    re.DOTALL,
)

# Matches the trailing content after the last --- (legacy summary section)
_SUMMARY_RE = re.compile(
    r"(?:^---\s*\n)((?!<!--\s*PART).*)\Z", re.MULTILINE | re.DOTALL
)

# Matches ::: question ... ::: fences (with optional subtype/label on the opening line)
_QUESTION_RE = re.compile(
    r"^:::\s*question([ \t][^\n]*)?\n(.*?)^:::\s*$",
    re.MULTILINE | re.DOTALL,
)

# Matches ::: feynman ... ::: fences
_FEYNMAN_RE = re.compile(
    r"^:::\s*feynman\s*\n(.*?)^:::\s*$",
    re.MULTILINE | re.DOTALL,
)

_SCOPE_RE = re.compile(r"^\s*scope\s*:\s*(.+)$", re.MULTILINE)


def parse_feynman_blocks(content: str) -> list[FeynmanBlockParsed]:
    """Extract all ::: feynman ... ::: blocks from lesson markdown content."""
    results: list[FeynmanBlockParsed] = []

    for match in _FEYNMAN_RE.finditer(content):
        body = match.group(1)
        scope = _parse_scope(body)
        question, points = _parse_question_and_points(body)
        if question and points:
            results.append(
                FeynmanBlockParsed(scope=scope, question=question, points=points)
            )

    return results


def parse_lesson_themes(content: str) -> list[LessonTheme]:
    """Extract all part sections from lesson markdown as themes.

    Supports both the new XML tag format (<part id="..." title="...">) and the
    legacy HTML comment format (<!-- PART N: Title -->).
    """
    # New XML format
    if "<part " in content:
        themes: list[LessonTheme] = []
        for i, match in enumerate(_XML_PART_RE.finditer(content), start=1):
            block_id = match.group(1).strip()
            title = match.group(2).strip()
            body = match.group(3).strip()
            themes.append(
                LessonTheme(number=i, title=title, content=body, block_id=block_id)
            )
        return themes

    # Legacy comment format
    themes = []
    for match in _PART_TITLE_RE.finditer(content):
        number = int(match.group(1))
        title = match.group(2).strip()
        body = match.group(3).strip()
        themes.append(LessonTheme(number=number, title=title, content=body))
    return themes


def parse_lesson_blocks(content: str) -> list[ParsedLessonBlock]:
    """Parse a lesson markdown file into numbered blocks + an optional summary block.

    New XML format (economics and future subjects):
        <part id="slug" title="Human Title"> ... </part>

        - Block 0: intro text before first <part> tag
        - Blocks 1…N: each <part> section
        - Last block: content after the final </part> tag (Quick Recap etc.), is_summary=True

    Legacy comment format (physics):
        <!-- PART N: Title -->  ...  <!-- /PART N -->

        - Block 0: intro text before first PART marker
        - Blocks 1…N: each PART section
        - Summary block: content after the last ``---`` separator
    """
    if "<part " in content:
        return _parse_xml_blocks(content)
    return _parse_comment_blocks(content)


# ---------------------------------------------------------------------------
# XML format parser
# ---------------------------------------------------------------------------


def _parse_xml_blocks(content: str) -> list[ParsedLessonBlock]:
    blocks: list[ParsedLessonBlock] = []
    all_parts = list(_XML_PART_RE.finditer(content))

    # Block 0 — intro text before the first <part> tag
    if all_parts:
        intro = content[: all_parts[0].start()].strip()
    else:
        intro = content.strip()
    if intro:
        blocks.append(
            ParsedLessonBlock(
                block_number=0,
                content=intro,
                is_summary=False,
                block_id="intro",
                title="Introduction",
            )
        )

    for i, match in enumerate(all_parts, start=1):
        block_id = match.group(1).strip()
        title = match.group(2).strip()
        body = match.group(3).strip()
        if body:
            blocks.append(
                ParsedLessonBlock(
                    block_number=i,
                    content=body,
                    is_summary=False,
                    block_id=block_id,
                    title=title,
                )
            )

    # Tail block — everything after the last </part> (Quick Recap etc.)
    if all_parts:
        tail = content[all_parts[-1].end() :].strip()
        if tail:
            blocks.append(
                ParsedLessonBlock(
                    block_number=len(all_parts) + 1,
                    content=tail,
                    is_summary=True,
                    block_id="summary",
                    title="Quick Recap",
                )
            )

    return blocks


# ---------------------------------------------------------------------------
# Legacy comment format parser (kept for backwards compatibility)
# ---------------------------------------------------------------------------


def _parse_comment_blocks(content: str) -> list[ParsedLessonBlock]:
    blocks: list[ParsedLessonBlock] = []
    all_parts = list(_PART_RE.finditer(content))

    # Block 0 — intro text before the first PART marker
    if all_parts:
        intro = content[: all_parts[0].start()].strip()
    else:
        intro = content.strip()
    if intro:
        blocks.append(
            ParsedLessonBlock(block_number=0, content=intro, is_summary=False)
        )

    for match in all_parts:
        number = int(match.group(1))
        body = match.group(2).strip()
        if body:
            blocks.append(
                ParsedLessonBlock(block_number=number, content=body, is_summary=False)
            )

    # Handle tail content after the last PART closer
    if all_parts:
        last_part = all_parts[-1]
        tail = content[last_part.end() :]
        last_part_number = int(last_part.group(1))
        summary_match = _SUMMARY_RE.search(tail)

        if summary_match:
            pre_summary = tail[: summary_match.start()].strip()
            if pre_summary and blocks:
                last_block = blocks[-1]
                blocks[-1] = ParsedLessonBlock(
                    block_number=last_block.block_number,
                    content=last_block.content + "\n\n" + pre_summary,
                    is_summary=False,
                )

            summary_content = summary_match.group(1).strip()
            if summary_content:
                blocks.append(
                    ParsedLessonBlock(
                        block_number=last_part_number + 1,
                        content=summary_content,
                        is_summary=True,
                    )
                )

    return blocks


# ---------------------------------------------------------------------------
# Feynman helpers
# ---------------------------------------------------------------------------


def _parse_scope(body: str) -> list[int]:
    """Parse 'scope: 1, 2, 4' into [1, 2, 4]."""
    scope_match = _SCOPE_RE.search(body)
    if not scope_match:
        return []
    raw = scope_match.group(1)
    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def _parse_question_and_points(body: str) -> tuple[str, list[str]]:
    """
    Separate the question text from the points list.

    Structure inside a feynman block:
        scope: ...
        <question text — may be multiple lines>
        points:
        - point one
        - point two
    """
    lines = body.splitlines()

    # Strip the scope line
    lines = [line for line in lines if not _SCOPE_RE.match(line)]

    # Find the 'points:' marker
    points_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*points\s*:\s*$", line):
            points_idx = i
            break

    if points_idx is None:
        return "", []

    question_lines = lines[:points_idx]
    point_lines = lines[points_idx + 1 :]

    question = "\n".join(question_lines).strip()

    points: list[str] = []
    for line in point_lines:
        stripped = re.sub(r"^\s*-\s*", "", line).strip()
        if stripped:
            points.append(stripped)

    return question, points


# ---------------------------------------------------------------------------
# Inline question parsing
# ---------------------------------------------------------------------------

_OPTION_KEY_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}


def _parse_directive_header(rest: str) -> tuple[str | None, str | None]:
    """Parse subtype and label from directive header text (e.g. 'mcq' or '[5 marks]')."""
    trimmed = rest.strip()
    if not trimmed:
        return None, None
    label_match = re.search(r"\[([^\]]+)\]", trimmed)
    subtype_match = re.match(r"(\w+)", trimmed) if not trimmed.startswith("[") else None
    return (
        subtype_match.group(1) if subtype_match else None,
        label_match.group(1) if label_match else None,
    )


def _parse_mcq_body(body: str) -> tuple[str, list[str], int | None, str]:
    """Parse MCQ question body → (question_text, options, correct_index, feedback)."""
    correct_match = re.search(r"^correct:\s*([A-D])", body, re.MULTILINE)
    feedback_match = re.search(r"^feedback:\s*(.+)$", body, re.MULTILINE)

    stripped = re.sub(r"^correct:.*$", "", body, flags=re.MULTILINE)
    stripped = re.sub(r"^feedback:.*$", "", stripped, flags=re.MULTILINE).strip()

    # Find options (A) ... B) ... etc.)
    option_re = re.compile(r"^(?:-\s+)?([A-D])[.)]\s+(.+)$", re.MULTILINE)
    options: list[str] = []
    first_option_match = re.search(r"^(?:-\s+)?[A-D][.)]\s", stripped, re.MULTILINE)
    first_option_idx = (
        first_option_match.start() if first_option_match else len(stripped)
    )

    for m in option_re.finditer(stripped):
        options.append(m.group(2).strip())

    question_text = stripped[:first_option_idx].strip()
    correct_key = correct_match.group(1) if correct_match else None
    correct_index = _OPTION_KEY_MAP.get(correct_key) if correct_key else None
    feedback = feedback_match.group(1).strip() if feedback_match else ""

    return question_text, options, correct_index, feedback


def _parse_open_body(
    body: str, marks_str: str | None
) -> tuple[str, str, str | None, int]:
    """Parse open question body → (question_text, model_answer, mark_scheme, points)."""
    markscheme_idx = -1
    model_answer_idx = -1
    for m in re.finditer(r"^mark_?scheme:", body, re.MULTILINE):
        markscheme_idx = m.start()
        break
    for m in re.finditer(r"^model_answer:", body, re.MULTILINE):
        model_answer_idx = m.start()
        break

    first_meta = min(
        markscheme_idx if markscheme_idx != -1 else len(body) + 1,
        model_answer_idx if model_answer_idx != -1 else len(body) + 1,
    )
    question_text = (
        body[:first_meta].strip() if first_meta <= len(body) else body.strip()
    )

    model_answer = ""
    if model_answer_idx != -1:
        key_match = re.match(r"model_answer:", body[model_answer_idx:])
        start = model_answer_idx + (
            len(key_match.group(0)) if key_match else len("model_answer:")
        )
        end = (
            markscheme_idx
            if markscheme_idx != -1 and markscheme_idx > model_answer_idx
            else len(body)
        )
        model_answer = body[start:end].strip().strip('"')

    mark_scheme = None
    if markscheme_idx != -1:
        key_match = re.match(r"mark_?scheme:", body[markscheme_idx:])
        key_len = len(key_match.group(0)) if key_match else len("markscheme:")
        start = markscheme_idx + key_len
        end = (
            model_answer_idx
            if model_answer_idx != -1 and model_answer_idx > markscheme_idx
            else len(body)
        )
        raw = body[start:end].strip()
        if raw:
            mark_scheme = raw

    marks = 0
    if marks_str:
        digits = re.search(r"\d+", marks_str)
        if digits:
            marks = int(digits.group(0))

    return question_text, model_answer, mark_scheme, marks or 1


def parse_inline_questions(content: str, block_id: str) -> list[InlineQuestionParsed]:
    """Extract all ::: question ... ::: blocks from a single lesson block's content.

    Returns a list of InlineQuestionParsed with inline_key = "{block_id}:{index}".
    Mirrors the frontend parseContent + parseMcq / parseOpenQuestion logic.
    """
    results: list[InlineQuestionParsed] = []
    idx = 0

    for match in _QUESTION_RE.finditer(content):
        header_rest = match.group(1) or ""
        body = match.group(2).strip()
        subtype, label = _parse_directive_header(header_rest)

        inline_key = f"{block_id}:{idx}"

        if subtype == "mcq":
            question_text, options, correct_index, feedback = _parse_mcq_body(body)
            results.append(
                InlineQuestionParsed(
                    inline_key=inline_key,
                    type="mcq",
                    question=question_text,
                    options=options if options else None,
                    correct_option_index=correct_index,
                    model_answer=feedback or "",
                    mark_scheme=None,
                    points=1,
                    feedback=feedback,
                )
            )
        else:
            question_text, model_answer, mark_scheme, points = _parse_open_body(
                body, label
            )
            results.append(
                InlineQuestionParsed(
                    inline_key=inline_key,
                    type="short",
                    question=question_text,
                    options=None,
                    correct_option_index=None,
                    model_answer=model_answer,
                    mark_scheme=mark_scheme,
                    points=points,
                    feedback=None,
                )
            )

        idx += 1

    return results


def extract_description(content: str) -> str | None:
    """Extract the first paragraph after the # heading as a description."""
    lines = content.split("\n")
    past_heading = False
    desc_lines: list[str] = []
    for line in lines:
        if line.startswith("# ") and not past_heading:
            past_heading = True
            continue
        if past_heading:
            stripped = line.strip()
            if not stripped and desc_lines:
                break  # end of first paragraph
            # Skip XML tags and HTML comments but keep regular text
            if (
                stripped
                and not stripped.startswith("<!--")
                and not stripped.startswith("<part")
            ):
                desc_lines.append(stripped)
    return " ".join(desc_lines) if desc_lines else None
