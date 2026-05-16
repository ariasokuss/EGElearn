"""Question-type helpers for session grading."""

from src.learning.tests.session_service import TestSessionService as SessionService


def test_requires_llm_grading_includes_open() -> None:
    assert SessionService._requires_llm_grading("short") is True
    assert SessionService._requires_llm_grading("open") is True


def test_requires_llm_grading_excludes_mcq() -> None:
    assert SessionService._requires_llm_grading("mcq") is False
    assert SessionService._requires_llm_grading(None) is False
