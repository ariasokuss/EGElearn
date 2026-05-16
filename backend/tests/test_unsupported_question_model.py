from src.learning.tests.models import TestQuestion


def test_test_question_has_is_unsupported_column():
    col = TestQuestion.__table__.columns["is_unsupported"]
    assert col is not None
    assert col.type.python_type is bool
    assert col.default.arg is False
