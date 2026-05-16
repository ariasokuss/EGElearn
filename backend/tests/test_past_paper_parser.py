from __future__ import annotations

from types import SimpleNamespace

from src.learning.past_paper.parser import _parse_mark_scheme_assignment


def _q(index: int):
    return SimpleNamespace(index=index, question=f"Question {index}")


def test_parse_mark_scheme_assignment_accepts_zero_based_keys():
    raw = """```json
{"0": "Award 1 mark", "1": "Award 2 marks"}
```"""
    questions = [_q(0), _q(1)]

    result = _parse_mark_scheme_assignment(raw, questions)

    assert result == {0: "Award 1 mark", 1: "Award 2 marks"}


def test_parse_mark_scheme_assignment_accepts_question_prefixed_keys():
    raw = """```json
{"q0": "Point A", "question_2": "Point C"}
```"""
    questions = [_q(0), _q(1), _q(2)]

    result = _parse_mark_scheme_assignment(raw, questions)

    assert result == {0: "Point A", 1: None, 2: "Point C"}


from src.learning.past_paper.schemas import ParsedQuestion


def test_parsed_question_accepts_requires_diagram_true():
    q = ParsedQuestion.model_validate({
        "question": "Draw a circuit diagram.",
        "model_answer": "See diagram.",
        "type": "short",
        "requires_diagram": True,
    })
    assert q.requires_diagram is True


def test_parsed_question_requires_diagram_defaults_false():
    q = ParsedQuestion.model_validate({
        "question": "What is osmosis?",
        "model_answer": "Movement of water.",
        "type": "short",
    })
    assert q.requires_diagram is False


def test_parsed_question_has_is_unsupported_field():
    q = ParsedQuestion.model_validate({
        "question": "What is osmosis?",
        "model_answer": "Movement of water.",
        "type": "short",
    })
    assert q.is_unsupported is False


import json as _json
from src.learning.past_paper.parser import _parse_llm_output as _plo


def _raw(questions: list[dict]) -> str:
    return f"```json\n{_json.dumps(questions)}\n```"


def test_parse_llm_output_marks_graphical_question_as_unsupported():
    """Non-MCQ matching the graphical regex gets is_unsupported=True, not dropped."""
    raw = _raw([{
        "question": "Draw a ray diagram to show how a converging lens forms an image.",
        "model_answer": "See diagram.",
        "type": "short",
        "requires_diagram": False,
    }])
    result = _plo(raw)
    assert len(result) == 1
    assert result[0].is_unsupported is True


def test_parse_llm_output_marks_requires_diagram_flag_as_unsupported():
    """requires_diagram=True from the LLM sets is_unsupported=True."""
    raw = _raw([{
        "question": "Sketch the velocity-time graph for the motion.",
        "model_answer": "See graph.",
        "type": "short",
        "requires_diagram": True,
    }])
    result = _plo(raw)
    assert len(result) == 1
    assert result[0].is_unsupported is True


def test_parse_llm_output_normal_question_not_marked_unsupported():
    """A regular short-answer question is not marked as unsupported."""
    raw = _raw([{
        "question": "Explain what osmosis is.",
        "model_answer": "Movement of water molecules.",
        "type": "short",
        "requires_diagram": False,
    }])
    result = _plo(raw)
    assert len(result) == 1
    assert result[0].is_unsupported is False


def test_parse_llm_output_mcq_with_graphical_text_not_marked_unsupported():
    """MCQ questions are never marked unsupported even if they mention diagrams."""
    raw = _raw([{
        "question": "Which diagram shows the correct ray path?",
        "model_answer": "B",
        "type": "mcq",
        "options": ["A", "B", "C", "D"],
        "correct_option_index": 1,
        "requires_diagram": False,
    }])
    result = _plo(raw)
    assert len(result) == 1
    assert result[0].is_unsupported is False
