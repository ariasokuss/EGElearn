import uuid
from src.learning.tests.schemas import TestQuestionOut, QuestionWithAnswerOut


def _base():
    return dict(
        id=uuid.uuid4(),
        index=0,
        type="short",
        question="Draw a circuit.",
        options=None,
        hint=None,
        points=2,
    )


def test_test_question_out_exposes_is_unsupported():
    out = TestQuestionOut(**_base(), is_unsupported=True)
    assert out.is_unsupported is True


def test_test_question_out_is_unsupported_defaults_false():
    out = TestQuestionOut(**_base())
    assert out.is_unsupported is False


def test_test_question_out_exposes_mark_scheme():
    out = TestQuestionOut(**_base(), mark_scheme="Award 1 mark.")
    assert out.mark_scheme == "Award 1 mark."


def test_test_question_out_mark_scheme_defaults_none():
    out = TestQuestionOut(**_base())
    assert out.mark_scheme is None


def test_question_with_answer_out_exposes_is_unsupported():
    out = QuestionWithAnswerOut(**_base(), is_unsupported=True)
    assert out.is_unsupported is True
