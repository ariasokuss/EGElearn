"""Pure helper tests for AI hint advisory lock key."""

from __future__ import annotations

import uuid

from src.learning.tests.session_service import hint_advisory_lock_key


def test_hint_advisory_lock_key_stable() -> None:
    s = uuid.UUID("11111111-1111-1111-1111-111111111111")
    q = uuid.UUID("22222222-2222-2222-2222-222222222222")
    assert hint_advisory_lock_key(s, q) == hint_advisory_lock_key(s, q)


def test_hint_advisory_lock_key_differs_for_different_pairs() -> None:
    s = uuid.UUID("11111111-1111-1111-1111-111111111111")
    q1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    q2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
    assert hint_advisory_lock_key(s, q1) != hint_advisory_lock_key(s, q2)
