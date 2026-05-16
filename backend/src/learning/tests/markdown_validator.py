"""Markdown structure validation for questions, model answers, hints, context, and options."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MarkdownIssue:
    """A single validation issue in a markdown field."""
    field: str
    issue: str


def validate_question_markdown(question: dict) -> list[MarkdownIssue]:
    """
    Validate markdown structure in a question dict.

    Checks:
    - Balanced $...$ and $$...$$ (LaTeX)
    - Balanced ```...``` (code fences)
    - Proper table structure (header + separator + data rows)

    Args:
        question: Dict with keys question, model_answer, mark_scheme, hint, context, options

    Returns:
        List of MarkdownIssue objects (empty if valid).
    """
    issues = []

    for field_name in ("question", "model_answer", "mark_scheme", "hint", "context"):
        value = question.get(field_name)
        if isinstance(value, str):
            issues.extend(_validate_field(field_name, value))

    options = question.get("options")
    if isinstance(options, list):
        for idx, opt in enumerate(options):
            if isinstance(opt, str):
                issues.extend(_validate_field(f"options[{idx}]", opt))

    return issues


def _validate_field(field_name: str, text: str) -> list[MarkdownIssue]:
    """Validate a single field for markdown issues."""
    issues = []

    latex_issues = _check_latex(text)
    if latex_issues:
        issues.append(MarkdownIssue(field_name, latex_issues[0]))

    fence_issues = _check_code_fences(text)
    if fence_issues:
        issues.append(MarkdownIssue(field_name, fence_issues[0]))

    table_issues = _check_tables(text)
    if table_issues:
        issues.append(MarkdownIssue(field_name, table_issues[0]))

    return issues


def _check_latex(text: str) -> list[str]:
    """Check for balanced $ and $$ delimiters, ignoring escaped ones."""
    cleaned = text.replace(r"\$", "")

    single = cleaned.count("$") - 2 * cleaned.count("$$")
    if single % 2 != 0:
        return ["unbalanced single dollar ($) — LaTeX must use $...$ pairs"]

    double = cleaned.count("$$")
    if double % 2 != 0:
        return ["unbalanced double dollar ($$) — LaTeX block must use $$...$$ pairs"]

    return []


def _check_code_fences(text: str) -> list[str]:
    """Check for balanced code fence markers (```)."""
    count = text.count("```")
    if count % 2 != 0:
        return ["unbalanced code fence (```) — must have opening and closing fences"]
    return []


def _check_tables(text: str) -> list[str]:
    """Check for proper markdown table structure (header + separator + optional data rows)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if re.match(r"^\|[-| :]+\|$", stripped):
            continue  # separator row, skip
        # Only flag a header row (no preceding pipe row in current block).
        prev_line = lines[i - 1].strip() if i > 0 else ""
        prev_is_pipe = prev_line.startswith("|") and prev_line.endswith("|")
        if not prev_is_pipe:
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if not re.match(r"^\|[-| :]+\|$", next_line):
                return ["table header missing separator row"]
    return []
