from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.learning import models as _learning_models  # noqa: F401 — register mappers
from src.learning.past_paper.admin import router as admin_router
from src.learning.past_paper.admin_library import ADMIN_LIBRARY_FOLDER_ID
from src.api.deps import get_db, get_container, require_admin_secret


def _auth_header(username: str = "admin", password: str = "secret") -> dict[str, str]:
    raw = f"{username}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


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


def test_static_css_served():
    app = _build_app(require_auth=False)
    with TestClient(app) as c:
        resp = c.get("/admin/past-papers/static/style.css")
    assert resp.status_code == 200
    assert "qrow" in resp.text
    assert resp.headers["content-type"].startswith("text/css")


def test_new_form_renders():
    app = _build_app(require_auth=False)
    with TestClient(app) as c:
        resp = c.get("/admin/past-papers/new")
    assert resp.status_code == 200
    assert 'name="file"' in resp.text
    assert 'name="mark_scheme_file"' in resp.text


def test_list_page_renders_with_papers():
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        name="Test Paper",
        status="ready",
        total_questions=3,
        is_canonical=True,
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
    )
    scalars_obj = MagicMock()
    scalars_obj.all = MagicMock(return_value=[paper])
    exec_result = MagicMock()
    exec_result.scalars = MagicMock(return_value=scalars_obj)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=exec_result)

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.get("/admin/past-papers")
    assert resp.status_code == 200
    assert "Test Paper" in resp.text
    assert "Hashed" in resp.text


def test_hash_route_404_for_missing():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.commit = AsyncMock()

    app = _build_app(db_session=db, require_auth=False)
    missing_id = "00000000-0000-0000-0000-000000000999"
    with TestClient(app) as c:
        resp = c.post(f"/admin/past-papers/{missing_id}/hash")
    assert resp.status_code == 404


def test_hash_toggle_flips_is_canonical():
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=None,
        folder_id=ADMIN_LIBRARY_FOLDER_ID,
        status="ready",
        is_canonical=False,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=paper)
    db.commit = AsyncMock()

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(f"/admin/past-papers/{paper.id}/hash", follow_redirects=False)
    assert resp.status_code == 303
    assert paper.is_canonical is True
    db.commit.assert_awaited()


def test_hash_route_409_when_not_ready():
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=None,
        folder_id=ADMIN_LIBRARY_FOLDER_ID,
        status="processing",
        is_canonical=False,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=paper)
    db.commit = AsyncMock()

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(f"/admin/past-papers/{paper.id}/hash", follow_redirects=False)
    assert resp.status_code == 409


def test_hash_route_404_for_paper_outside_admin_library():
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),  # belongs to a real user
        folder_id=uuid.uuid4(),
        status="ready",
        is_canonical=False,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=paper)
    db.commit = AsyncMock()

    app = _build_app(db_session=db, require_auth=False)
    with TestClient(app) as c:
        resp = c.post(f"/admin/past-papers/{paper.id}/hash", follow_redirects=False)
    assert resp.status_code == 404


def test_serve_asset_invalid_type_404():
    app = _build_app(require_auth=False)
    pid = uuid.uuid4()
    with TestClient(app) as c:
        resp = c.get(f"/admin/past-papers/{pid}/assets/bogus/x.png")
    assert resp.status_code == 404


def test_status_stream_emits_status_and_end_for_ready_paper():
    """When the paper is already 'ready', the stream emits one status event then end."""
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=None,
        folder_id=ADMIN_LIBRARY_FOLDER_ID,
        status="ready",
        processing_phase=None,
        total_questions=5,
        is_canonical=False,
    )
    sf_session = AsyncMock()
    sf_session.get = AsyncMock(return_value=paper)
    sf_cm = AsyncMock()
    sf_cm.__aenter__.return_value = sf_session
    sf_cm.__aexit__.return_value = False
    container = MagicMock()
    container.session_factory = MagicMock(return_value=sf_cm)

    app = _build_app(container=container, require_auth=False)
    with TestClient(app) as c:
        with c.stream("GET", f"/admin/past-papers/{paper.id}/status-stream") as resp:
            assert resp.status_code == 200
            chunks = b"".join(resp.iter_bytes())
    text = chunks.decode()
    assert "event: status" in text
    assert "event: end" in text
    assert '"status": "ready"' in text


def test_status_stream_emits_error_for_paper_outside_admin_library():
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),  # belongs to a real user
        folder_id=uuid.uuid4(),
        status="ready",
        processing_phase=None,
        total_questions=0,
        is_canonical=False,
    )
    sf_session = AsyncMock()
    sf_session.get = AsyncMock(return_value=paper)
    sf_cm = AsyncMock()
    sf_cm.__aenter__.return_value = sf_session
    sf_cm.__aexit__.return_value = False
    container = MagicMock()
    container.session_factory = MagicMock(return_value=sf_cm)

    app = _build_app(container=container, require_auth=False)
    with TestClient(app) as c:
        with c.stream("GET", f"/admin/past-papers/{paper.id}/status-stream") as resp:
            assert resp.status_code == 200
            chunks = b"".join(resp.iter_bytes())
    text = chunks.decode()
    assert "event: error" in text

