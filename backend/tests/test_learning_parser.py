"""Tests for src.learning.parser — feynman block extraction."""

from __future__ import annotations

import textwrap


from src.learning.parser import (
    FeynmanBlockParsed,
    _parse_scope,
    _parse_question_and_points,
    parse_feynman_blocks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def feynman_block(
    *,
    scope: str = "scope: 1, 2",
    question: str = "Explain this concept.",
    points: str = "- Point A\n- Point B",
) -> str:
    """Build a minimal ::: feynman ::: fence string."""
    return f"::: feynman\n{scope}\n{question}\npoints:\n{points}\n:::\n"


# ---------------------------------------------------------------------------
# _parse_scope
# ---------------------------------------------------------------------------


class TestParseScope:
    def test_single_block(self):
        assert _parse_scope("scope: 1") == [1]

    def test_multiple_blocks(self):
        assert _parse_scope("scope: 1, 2, 4") == [1, 2, 4]

    def test_whitespace_around_numbers(self):
        assert _parse_scope("scope:  3 ,  5 ,  7 ") == [3, 5, 7]

    def test_no_scope_line_returns_empty(self):
        assert _parse_scope("question text\npoints:\n- A") == []

    def test_non_numeric_values_skipped(self):
        assert _parse_scope("scope: 1, two, 3") == [1, 3]

    def test_scope_with_extra_whitespace_before_colon(self):
        assert _parse_scope("scope : 2, 3") == [2, 3]


# ---------------------------------------------------------------------------
# _parse_question_and_points
# ---------------------------------------------------------------------------


class TestParseQuestionAndPoints:
    def test_simple_single_line_question(self):
        body = "scope: 1\nWhat is this?\npoints:\n- A\n- B\n"
        q, pts = _parse_question_and_points(body)
        assert q == "What is this?"
        assert pts == ["A", "B"]

    def test_multi_line_question(self):
        body = "scope: 1\nLine one.\nLine two.\npoints:\n- A\n"
        q, pts = _parse_question_and_points(body)
        assert q == "Line one.\nLine two."
        assert pts == ["A"]

    def test_points_with_italic_markdown(self):
        body = "scope: 1\nQuestion.\npoints:\n- *Positive* analysis tells us what *will* happen.\n- Normative judgements depend on values.\n"
        q, pts = _parse_question_and_points(body)
        assert pts[0] == "*Positive* analysis tells us what *will* happen."
        assert pts[1] == "Normative judgements depend on values."

    def test_blank_lines_in_points_skipped(self):
        body = "scope: 1\nQ.\npoints:\n- A\n\n- B\n"
        q, pts = _parse_question_and_points(body)
        assert pts == ["A", "B"]

    def test_no_points_marker_returns_empty(self):
        body = "scope: 1\nNo points here.\n"
        q, pts = _parse_question_and_points(body)
        assert q == ""
        assert pts == []

    def test_empty_question_after_scope_strip(self):
        body = "scope: 1\npoints:\n- A\n"
        q, pts = _parse_question_and_points(body)
        assert q == ""

    def test_points_with_varied_indentation(self):
        body = "scope: 1\nQ.\npoints:\n  - Indented A\n\t- Tabbed B\n"
        q, pts = _parse_question_and_points(body)
        assert "Indented A" in pts
        assert "Tabbed B" in pts


# ---------------------------------------------------------------------------
# parse_feynman_blocks — main public function
# ---------------------------------------------------------------------------


class TestParseFeynmanBlocks:
    # ── basic happy paths ──────────────────────────────────────────────

    def test_returns_empty_for_no_blocks(self):
        assert parse_feynman_blocks("# Lesson\n\nJust plain text.") == []

    def test_single_block_parsed_correctly(self):
        content = feynman_block(
            scope="scope: 1, 2, 4",
            question="Can you explain why two economists may disagree?",
            points="- Positive analysis tells us facts.\n- Normative judgements involve values.",
        )
        result = parse_feynman_blocks(content)
        assert len(result) == 1
        fb = result[0]
        assert fb.scope == [1, 2, 4]
        assert fb.question == "Can you explain why two economists may disagree?"
        assert fb.points == [
            "Positive analysis tells us facts.",
            "Normative judgements involve values.",
        ]

    def test_multiple_blocks_all_parsed(self):
        content = (
            feynman_block(scope="scope: 1", question="Q1?", points="- A\n")
            + "\nSome text in between.\n\n"
            + feynman_block(scope="scope: 2, 3", question="Q2?", points="- B\n- C\n")
        )
        result = parse_feynman_blocks(content)
        assert len(result) == 2
        assert result[0].scope == [1]
        assert result[1].scope == [2, 3]

    def test_returns_feynman_block_parsed_instances(self):
        content = feynman_block()
        result = parse_feynman_blocks(content)
        assert all(isinstance(fb, FeynmanBlockParsed) for fb in result)

    # ── content embedding ──────────────────────────────────────────────

    def test_block_surrounded_by_markdown_is_found(self):
        content = textwrap.dedent("""\
            # Lesson Title

            Some introductory content here.

            ::: feynman
            scope: 1, 3
            What is the key difference?
            points:
            - Fact vs opinion.
            :::

            ## Summary

            More text after the block.
        """)
        result = parse_feynman_blocks(content)
        assert len(result) == 1
        assert result[0].scope == [1, 3]

    def test_block_with_other_directives_nearby(self):
        content = textwrap.dedent("""\
            ::: definition [Term]
            A definition block.
            :::

            ::: feynman
            scope: 2
            Explain the term.
            points:
            - It means X.
            - It implies Y.
            :::

            ::: question mcq
            A question block.
            :::
        """)
        result = parse_feynman_blocks(content)
        assert len(result) == 1
        assert result[0].points == ["It means X.", "It implies Y."]

    # ── scope edge cases ───────────────────────────────────────────────

    def test_missing_scope_line_yields_empty_scope(self):
        content = "::: feynman\nQuestion without scope.\npoints:\n- A\n:::\n"
        result = parse_feynman_blocks(content)
        assert len(result) == 1
        assert result[0].scope == []

    def test_scope_with_non_numeric_entries_filtered(self):
        content = feynman_block(scope="scope: 1, two, 3", question="Q?", points="- A\n")
        result = parse_feynman_blocks(content)
        assert result[0].scope == [1, 3]

    # ── filtering ─────────────────────────────────────────────────────

    def test_block_without_question_is_skipped(self):
        # scope line only, then immediately points:
        content = "::: feynman\nscope: 1\npoints:\n- A\n:::\n"
        result = parse_feynman_blocks(content)
        assert result == []

    def test_block_without_points_is_skipped(self):
        content = "::: feynman\nscope: 1\nJust a question.\n:::\n"
        result = parse_feynman_blocks(content)
        assert result == []

    def test_block_with_empty_points_list_is_skipped(self):
        # points: marker present but no bullet items
        content = "::: feynman\nscope: 1\nQuestion.\npoints:\n:::\n"
        result = parse_feynman_blocks(content)
        assert result == []

    # ── real-world fixture ─────────────────────────────────────────────

    LESSON_1_1_2 = textwrap.dedent("""\
        # Lesson 1.1.2: Positive and Normative Economic Statements

        Some introductory text.

        ---

        ## Positive Statements

        A **positive statement** is a statement about what *is*.

        ::: definition [Positive statement]
        A statement about what *is*; it makes a factual claim about the world.
        :::

        ## Normative Statements

        A **normative statement** is a statement about what *ought to be*.

        ---

        ::: feynman
        scope: 1, 2, 4
        Pause. Can you explain — in 2–3 sentences, as if telling a friend who has never studied economics — why two people can agree on all the facts about a policy yet still disagree on whether it should be introduced?
        points:
        - Positive analysis tells us *what will happen* if a policy is adopted — these are the testable facts economists can, in principle, agree on.
        - Normative judgements are about *what should happen*, and these depend on personal values such as fairness, freedom, or equality.
        - Different values lead to different policy conclusions even when the underlying economic analysis is identical, because no amount of evidence can tell us which value to prioritise.
        :::

        ---

        ## Summary
    """)

    def test_real_lesson_block_parsed(self):
        result = parse_feynman_blocks(self.LESSON_1_1_2)
        assert len(result) == 1
        fb = result[0]
        assert fb.scope == [1, 2, 4]
        assert "two people can agree on all the facts" in fb.question
        assert len(fb.points) == 3
        assert "Positive analysis" in fb.points[0]
        assert "Normative judgements" in fb.points[1]
        assert "Different values" in fb.points[2]

    def test_real_lesson_no_extra_blocks(self):
        # The definition block must NOT be parsed as a feynman block
        result = parse_feynman_blocks(self.LESSON_1_1_2)
        assert len(result) == 1
