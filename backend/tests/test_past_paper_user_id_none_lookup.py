from __future__ import annotations

import inspect

from src.learning.past_paper import service as pp_svc


def test_get_past_paper_signature_allows_none():
    sig = inspect.signature(pp_svc.get_past_paper)
    assert str(sig.parameters["user_id"].annotation) in {
        "uuid.UUID | None",
        "Optional[uuid.UUID]",
    }


def test_delete_past_paper_signature_allows_none():
    sig = inspect.signature(pp_svc.delete_past_paper)
    assert str(sig.parameters["user_id"].annotation) in {
        "uuid.UUID | None",
        "Optional[uuid.UUID]",
    }


def test_get_past_paper_uses_is_none_branch():
    src = inspect.getsource(pp_svc.get_past_paper)
    assert ".is_(None)" in src


def test_delete_past_paper_uses_is_none_branch():
    src = inspect.getsource(pp_svc.delete_past_paper)
    assert ".is_(None)" in src
