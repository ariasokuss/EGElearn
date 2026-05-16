"""Unit tests for markdown structure validation."""

from __future__ import annotations

from src.learning.tests.markdown_validator import MarkdownIssue, validate_question_markdown


def _q(**kwargs) -> dict:
    """Minimal valid question dict — override fields via kwargs."""
    base = {
        "question": "What is Newton's second law?",
        "model_answer": "F = ma",
        "mark_scheme": None,
        "hint": None,
        "context": None,
        "options": None,
    }
    base.update(kwargs)
    return base


class TestCleanMarkdown:
    def test_clean_question_returns_empty(self):
        assert validate_question_markdown(_q()) == []

    def test_valid_latex_even_dollars(self):
        assert validate_question_markdown(_q(question="Find $x$ where $x^2 = 4$.")) == []

    def test_valid_double_dollar_block(self):
        assert validate_question_markdown(_q(model_answer="$$E = mc^2$$")) == []

    def test_valid_code_fence(self):
        assert validate_question_markdown(_q(question="```python\nprint(1)\n```")) == []

    def test_valid_table(self):
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert validate_question_markdown(_q(context=table)) == []

    def test_return_type_is_list_of_markdown_issues(self):
        issues = validate_question_markdown(_q(question="Find $x where x > 0."))
        assert len(issues) >= 1
        assert isinstance(issues[0], MarkdownIssue)
        assert isinstance(issues[0].field, str)
        assert isinstance(issues[0].issue, str)


class TestLatexValidation:
    def test_odd_single_dollar_reports_issue(self):
        issues = validate_question_markdown(_q(question="Find $x where x > 0."))
        assert len(issues) >= 1
        assert issues[0].field == "question"
        assert "dollar" in issues[0].issue.lower() or "$" in issues[0].issue

    def test_unclosed_double_dollar_reports_issue(self):
        issues = validate_question_markdown(_q(model_answer="$$E = mc^2"))
        assert len(issues) >= 1
        assert issues[0].field == "model_answer"
        assert "$$" in issues[0].issue

    def test_multiple_fields_with_latex_errors(self):
        issues = validate_question_markdown(_q(
            question="Find $x.",
            model_answer="$$E = mc^2",
        ))
        fields = {i.field for i in issues}
        assert "question" in fields
        assert "model_answer" in fields

    def test_escaped_dollar_not_counted(self):
        assert validate_question_markdown(_q(question=r"Cost is \$5.")) == []


class TestCodeFenceValidation:
    def test_unclosed_fence_reports_issue(self):
        issues = validate_question_markdown(_q(question="```python\nprint(1)"))
        assert len(issues) >= 1
        assert issues[0].field == "question"
        assert "fence" in issues[0].issue.lower() or "```" in issues[0].issue

    def test_two_fences_are_valid(self):
        assert validate_question_markdown(_q(question="```python\nprint(1)\n```")) == []

    def test_four_fences_are_valid(self):
        q = "```python\nfoo()\n```\n\n```python\nbar()\n```"
        assert validate_question_markdown(_q(question=q)) == []


class TestTableValidation:
    def test_table_missing_separator_reports_issue(self):
        table = "| A | B |\n| 1 | 2 |"
        issues = validate_question_markdown(_q(context=table))
        assert len(issues) >= 1
        assert issues[0].field == "context"
        assert "table" in issues[0].issue.lower() or "separator" in issues[0].issue.lower()

    def test_table_with_separator_is_valid(self):
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert validate_question_markdown(_q(context=table)) == []

    def test_table_with_multiple_data_rows_is_valid(self):
        table = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        assert validate_question_markdown(_q(context=table)) == []


class TestOptionsValidation:
    def test_broken_latex_in_option(self):
        issues = validate_question_markdown(_q(options=["$x", "$y$", "$z$", "$w$"]))
        assert any(i.field == "options[0]" for i in issues)

    def test_clean_options_no_issues(self):
        assert validate_question_markdown(_q(options=["$x$", "$y$", "plain", "also plain"])) == []

    def test_non_string_options_ignored(self):
        assert validate_question_markdown(_q(options=[1, 2, 3, 4])) == []
