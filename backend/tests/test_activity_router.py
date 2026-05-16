from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.activity.router import router
from src.api.deps import get_current_user


def _build_app(activity_service) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.activity_service = activity_service

    async def _current_user():
        return SimpleNamespace(id=uuid.uuid4(), is_active=True)

    app.dependency_overrides[get_current_user] = _current_user
    return app


def test_record_client_event_accepts_allowlisted_event_and_sanitizes_metadata():
    activity_service = SimpleNamespace(log_event=AsyncMock())
    app = _build_app(activity_service)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/activity/events",
            json={
                "event_type": "page_view",
                "route_label": "Folder",
                "metadata": {
                    "path": "/learning",
                    "message": "raw chat",
                    "answer_length": 10,
                },
            },
        )

    assert resp.status_code == 201
    sent = activity_service.log_event.await_args.args[0]
    assert sent.event_type == "page_view"
    assert sent.metadata == {"path": "/learning", "answer_length": 10}
    assert sent.replay_payload is None


def test_record_client_event_ignores_client_supplied_replay_payload():
    activity_service = SimpleNamespace(log_event=AsyncMock())
    app = _build_app(activity_service)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/activity/events",
            json={
                "event_type": "page_view",
                "metadata": {"path": "/learning"},
                "replay_payload": {
                    "items": [
                        {"kind": "user_message", "text": "client controlled raw text"}
                    ]
                },
            },
        )

    assert resp.status_code == 201
    sent = activity_service.log_event.await_args.args[0]
    assert sent.metadata == {"path": "/learning"}
    assert sent.replay_payload is None


def test_record_client_event_accepts_lesson_chat_opened_as_chat_event():
    activity_service = SimpleNamespace(log_event=AsyncMock())
    app = _build_app(activity_service)
    folder_id = str(uuid.uuid4())
    lesson_id = str(uuid.uuid4())

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/activity/events",
            json={
                "event_type": "chat_opened",
                "route_label": "Opened lesson chat",
                "entity_type": "lesson",
                "entity_id": lesson_id,
                "folder_id": folder_id,
                "lesson_id": lesson_id,
                "metadata": {
                    "surface": "lesson_panel",
                    "message": "raw chat text",
                },
            },
        )

    assert resp.status_code == 201
    sent = activity_service.log_event.await_args.args[0]
    assert sent.event_type == "chat_opened"
    assert sent.event_group == "chat"
    assert str(sent.folder_id) == folder_id
    assert str(sent.lesson_id) == lesson_id
    assert sent.metadata == {"surface": "lesson_panel"}


def test_record_client_event_rejects_unknown_event_type():
    activity_service = SimpleNamespace(log_event=AsyncMock())
    app = _build_app(activity_service)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/activity/events",
            json={"event_type": "raw_request_body", "metadata": {}},
        )

    assert resp.status_code == 422
    activity_service.log_event.assert_not_called()
