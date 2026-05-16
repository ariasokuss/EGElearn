"""Unit tests for _typed_question_from_raw — LLM response normaliser.

Covers the contract documented in PQG MCQ prompts (e.g.
docs/A-Level/AQA A-Level Chemistry/prompts/mcq.md):

- Stem only in `question`
- Choices in `options` (JSON array)
- Correct answer as `correct_option` (1-based int: A=1, B=2, C=3, D=4)
"""

from __future__ import annotations

from src.learning.tests.template_service import _typed_question_from_raw


def _raw_mcq(**overrides) -> dict:
    base = {
        "question": "Which statement about relative molecular mass is correct?",
        "model_answer": "B — explanation...",
        "options": [
            "It is measured in grams per mole.",
            "It is the mass of one molecule relative to 1/12 of carbon-12.",
            "It equals the molar mass divided by Avogadro's number.",
            "It depends on the state of the substance.",
        ],
        "correct_option": 2,
        "mark_scheme": "Award 1 mark for B.",
        "hint": "Recall the definition of relative molecular mass.",
        "context": None,
    }
    base.update(overrides)
    return base


class TestPqgFormat:
    """Prompts ship options in a separate array and use 1-based correct_option."""

    def test_pqg_mcq_preserves_separate_options_array(self):
        result = _typed_question_from_raw(_raw_mcq(), "mcq", 1, [])
        assert result["type"] == "mcq"
        assert result["options"] == [
            "It is measured in grams per mole.",
            "It is the mass of one molecule relative to 1/12 of carbon-12.",
            "It equals the molar mass divided by Avogadro's number.",
            "It depends on the state of the substance.",
        ]

    def test_pqg_mcq_converts_1_based_correct_option_to_0_based_index(self):
        result = _typed_question_from_raw(_raw_mcq(correct_option=2), "mcq", 1, [])
        assert result["correct_option_index"] == 1

    def test_pqg_mcq_keeps_question_stem_intact(self):
        result = _typed_question_from_raw(_raw_mcq(), "mcq", 1, [])
        assert result["question"] == (
            "Which statement about relative molecular mass is correct?"
        )

    def test_pqg_mcq_with_only_three_options_still_recognised(self):
        raw = _raw_mcq(options=["x", "y", "z"], correct_option=1)
        result = _typed_question_from_raw(raw, "mcq", 1, [])
        assert result["type"] == "mcq"
        assert result["options"] == ["x", "y", "z"]
        assert result["correct_option_index"] == 0


class TestEmbeddedFallback:
    """Older prompts that embed A./B./C./D. in the question text still work."""

    def test_embedded_options_extracted_when_no_array(self):
        raw = {
            "question": (
                "Which gas is most abundant in Earth's atmosphere?\n"
                "A. Oxygen\n"
                "B. Nitrogen\n"
                "C. Carbon dioxide\n"
                "D. Argon"
            ),
            "model_answer": "B",
        }
        result = _typed_question_from_raw(raw, "mcq", 1, [])
        assert result["type"] == "mcq"
        assert result["options"] == ["Oxygen", "Nitrogen", "Carbon dioxide", "Argon"]
        assert result["correct_option_index"] == 1
        assert result["question"] == "Which gas is most abundant in Earth's atmosphere?"


class TestDegenerateInputs:
    """When the LLM returns nothing useful, type degrades to open."""

    def test_no_options_anywhere_falls_back_to_open(self):
        raw = {"question": "Explain bonding.", "model_answer": "..."}
        result = _typed_question_from_raw(raw, "mcq", 1, [])
        assert result["type"] == "open"
        assert result["options"] is None

    def test_short_options_array_with_two_items_is_rejected(self):
        # MCQ requires at least 3 plausible options; 2 is treated as malformed.
        raw = _raw_mcq(options=["only one", "and another"], correct_option=1)
        result = _typed_question_from_raw(raw, "mcq", 1, [])
        assert result["type"] == "open"
        assert result["options"] is None

    def test_correct_option_out_of_range_falls_back_to_letter_parse(self):
        raw = _raw_mcq(correct_option=99, model_answer="C — because...")
        result = _typed_question_from_raw(raw, "mcq", 1, [])
        assert result["type"] == "mcq"
        # 99 is invalid; resolver reads "C" from model_answer → index 2.
        assert result["correct_option_index"] == 2

    def test_short_type_does_not_extract_options(self):
        raw = {
            "question": "A. Define oxidation.\nB. Define reduction.",
            "model_answer": "Loss/gain of electrons.",
        }
        result = _typed_question_from_raw(raw, "short", 5, [])
        assert result["type"] == "open"
        assert result["options"] is None
