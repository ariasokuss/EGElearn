from __future__ import annotations

import inspect

from src.learning.past_paper import service as pp_svc


def test_clone_sets_is_canonical_false():
    src = inspect.getsource(pp_svc._clone_cached_past_paper)
    assert "is_canonical=False" in src, (
        "Cloned templates must not inherit canonical status"
    )
