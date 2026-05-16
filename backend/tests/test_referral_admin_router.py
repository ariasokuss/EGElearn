from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_db, get_container, require_admin_secret
from src.referral.admin import router as admin_router
from src.referral.admin_schemas import (
    AdminAttributionRow,
    AdminSourceDetail,
    AdminSourceRow,
    AdminVisitRow,
)


def _auth_header(username: str = "admin", password: str = "secret") -> dict[str, str]:
    raw = f"{username}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def _make_container(*, admin_secret: str = "secret", admin_username: str = "admin"):
    """Build a minimal mock container for auth tests."""
    auth_settings = SimpleNamespace(
        admin_secret=admin_secret,
        admin_username=admin_username,
        admin_max_failed_attempts=5,
    )
    settings = SimpleNamespace(auth=auth_settings)
    container = MagicMock()
    container.settings = settings
    return container


def _build_app(*, db_session=None, container=None, require_auth: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router)
    if not require_auth:
        app.dependency_overrides[require_admin_secret] = lambda: None
    if db_session is not None:
        async def _override_db():
            yield db_session
        app.dependency_overrides[get_db] = _override_db
    if container is not None:
        app.dependency_overrides[get_container] = lambda: container
    return app


def _row(**overrides) -> AdminSourceRow:
    base = dict(
        source_id=uuid.uuid4(),
        code="alpha",
        label="Alpha",
        is_active=True,
        owner_user_id=uuid.uuid4(),
        owner_email="creator@example.com",
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
        visits_count=10,
        unique_visitors=8,
        registrations=4,
        purchases=2,
    )
    base.update(overrides)
    return AdminSourceRow(**base)


def test_dashboard_requires_auth():
    from src.api.admin_blacklist import AdminBruteForceGuard

    container = _make_container()
    app = _build_app(container=container)

    # Stub the brute-force guard so it doesn't need a real DB
    guard = MagicMock(spec=AdminBruteForceGuard)
    guard.is_blacklisted = AsyncMock(return_value=False)
    guard.record_failure = AsyncMock(return_value=False)
    guard.record_success = MagicMock()
    app.state.admin_brute_force = guard

    with TestClient(app) as c:
        resp = c.get("/admin/referrals")
    assert resp.status_code == 401


def test_dashboard_renders_rows(monkeypatch):
    rows = [_row(code="alpha"), _row(code="beta", visits_count=0, registrations=0)]

    async def fake_list(db):
        return rows

    monkeypatch.setattr(
        "src.referral.admin.ref_svc.list_all_sources_with_stats", fake_list
    )
    db = AsyncMock()
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.get("/admin/referrals")
    assert resp.status_code == 200
    assert "alpha" in resp.text
    assert "beta" in resp.text
    assert "creator@example.com" in resp.text
    assert 'name="email"' in resp.text


def test_dashboard_empty_state(monkeypatch):
    async def fake_list(db):
        return []

    monkeypatch.setattr(
        "src.referral.admin.ref_svc.list_all_sources_with_stats", fake_list
    )
    db = AsyncMock()
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.get("/admin/referrals")
    assert resp.status_code == 200
    assert "No referral sources yet" in resp.text


def _user_lookup_db(user=None):
    """AsyncMock db where db.scalar(select(User)...) returns `user`."""
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=user)
    db.add = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def test_create_redirects_with_user_not_found():
    db = _user_lookup_db(user=None)
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            "/admin/referrals",
            data={"email": "missing@example.com", "code": "newcode", "label": ""},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/referrals?error=user-not-found"


def test_create_rejects_invalid_code():
    db = _user_lookup_db(user=SimpleNamespace(id=uuid.uuid4()))
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            "/admin/referrals",
            data={"email": "c@example.com", "code": "bad code!", "label": ""},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/referrals?error=invalid-code"


def test_create_calls_service_and_redirects_ok(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    db = _user_lookup_db(user=user)

    created = {}

    async def fake_create_source(db_, user_id, code, label):
        created["user_id"] = user_id
        created["code"] = code
        created["label"] = label
        return SimpleNamespace(id=uuid.uuid4(), code=code, label=label, is_active=True)

    monkeypatch.setattr("src.referral.admin.ref_svc.create_source", fake_create_source)
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            "/admin/referrals",
            data={"email": "c@example.com", "code": "good-code", "label": "YouTube"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/referrals?ok=created"
    assert created == {"user_id": user.id, "code": "good-code", "label": "YouTube"}


def test_create_handles_code_taken(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    db = _user_lookup_db(user=user)

    async def fake_create_source(db_, user_id, code, label):
        from src.referral.service import ReferralError
        raise ReferralError("Code 'x' is already taken")

    monkeypatch.setattr("src.referral.admin.ref_svc.create_source", fake_create_source)
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            "/admin/referrals",
            data={"email": "c@example.com", "code": "taken", "label": ""},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/referrals?error=code-taken"


def test_toggle_flips_active():
    src = SimpleNamespace(id=uuid.uuid4(), is_active=True)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=src)
    db.commit = AsyncMock()
    db.flush = AsyncMock()

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            f"/admin/referrals/{src.id}/toggle", follow_redirects=False
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/referrals?ok=toggled"
    assert src.is_active is False


def test_toggle_404_when_missing():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(
            f"/admin/referrals/{uuid.uuid4()}/toggle", follow_redirects=False
        )
    assert resp.status_code == 404


def test_detail_renders(monkeypatch):
    sid = uuid.uuid4()
    detail = AdminSourceDetail(
        source=_row(source_id=sid, code="gamma"),
        attributions=[
            AdminAttributionRow(
                user_id=uuid.uuid4(),
                email="buyer@example.com",
                registered_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                purchased_at=None,
            )
        ],
        recent_visits=[
            AdminVisitRow(
                visited_at=datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
                landing_page="/pricing",
                visitor_id="abcd1234efgh",
                visitor_email="buyer@example.com",
            ),
            AdminVisitRow(
                visited_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
                landing_page="/",
                visitor_id="anon0000",
                visitor_email=None,
            ),
        ],
    )

    async def fake_detail(db, source_id):
        assert source_id == sid
        return detail

    monkeypatch.setattr("src.referral.admin.ref_svc.get_source_detail", fake_detail)
    db = AsyncMock()
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.get(f"/admin/referrals/{sid}")
    assert resp.status_code == 200
    assert "gamma" in resp.text
    assert "buyer@example.com" in resp.text
    assert "/pricing" in resp.text
    assert "anonymous" in resp.text  # un-attributed visit shows anonymous


def test_detail_404_when_missing(monkeypatch):
    async def fake_detail(db, source_id):
        return None

    monkeypatch.setattr("src.referral.admin.ref_svc.get_source_detail", fake_detail)
    db = AsyncMock()
    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.get(f"/admin/referrals/{uuid.uuid4()}")
    assert resp.status_code == 404
