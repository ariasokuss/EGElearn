"""Tests for the POST /api/v1/mail/send-desktop-link endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from jose import jwt

from src.api.deps import get_current_user, get_mail_client, get_settings
from src.auth.models import User
from src.config import Settings
from src.mail.client import MailError
from src.mail.router import router as mail_router


def _settings() -> Settings:
    return Settings(
        auth={
            "secret_key": "test-secret-key-at-least-32-chars-long!!",
            "algorithm": "HS256",
        }
    )


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        display_name="Student User",
    )


def _build_client(
    *,
    user: User | None = None,
    mail_client: AsyncMock | None = None,
) -> tuple[TestClient, AsyncMock]:
    """Build a minimal FastAPI app with only the mail router and dep overrides.

    Returns the client and the mail mock (so the test can assert on calls).
    Pass `user=None` to leave auth unmocked → the real dep will return 401.
    """
    app = FastAPI()
    app.include_router(mail_router, prefix="/api/v1")

    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    else:
        def _unauth() -> User:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        app.dependency_overrides[get_current_user] = _unauth

    mock = mail_client or AsyncMock()
    app.dependency_overrides[get_mail_client] = lambda: mock
    app.dependency_overrides[get_settings] = _settings

    return TestClient(app), mock


def test_send_desktop_link_unauthenticated() -> None:
    client, _ = _build_client(user=None)
    r = client.post(
        "/api/v1/mail/send-desktop-link",
        json={"desktop_url": "https://novalearn.ai"},
    )
    assert r.status_code == 401


def test_send_desktop_link_success() -> None:
    user = _make_user()
    client, mail = _build_client(user=user)

    r = client.post(
        "/api/v1/mail/send-desktop-link",
        json={"desktop_url": "https://novalearn.ai"},
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"message": "Link sent."}

    mail.send.assert_awaited_once()
    kwargs = mail.send.await_args.kwargs
    assert kwargs["to"] == user.email
    assert kwargs["subject"] == "Link"
    assert "https://novalearn.ai/auth/callback?desktop_login_token=" in kwargs["html_body"]

    html = kwargs["html_body"]
    assert "<style" not in html
    assert "style=" not in html
    assert "Hey,<br>" in html
    assert "Student User" not in html
    assert "Here is the link you requested" in html
    assert ">https://novalearn.ai/</a>" in html
    assert "We built it for the bigger screen" not in html
    assert "If anything looks off" not in html
    assert "— Roman" in html
    assert "Co-founder, NovaLearn" in html
    assert html.count("desktop_login_token=") == 1
    assert "&gt;https://novalearn.ai/auth/callback?desktop_login_token=" not in html
    token = html.split("desktop_login_token=", 1)[1].split('"', 1)[0]
    settings = _settings().auth
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
    )
    assert payload["type"] == "desktop_login"
    assert payload["sub"] == str(user.id)


def test_send_desktop_link_invalid_url() -> None:
    user = _make_user()
    client, mail = _build_client(user=user)

    r = client.post(
        "/api/v1/mail/send-desktop-link",
        json={"desktop_url": "not-a-url"},
    )

    assert r.status_code == 422
    mail.send.assert_not_called()


def test_send_desktop_link_smtp_failure_returns_503() -> None:
    user = _make_user()
    failing_mail = AsyncMock()
    failing_mail.send.side_effect = MailError("smtp down")

    client, _ = _build_client(user=user, mail_client=failing_mail)

    r = client.post(
        "/api/v1/mail/send-desktop-link",
        json={"desktop_url": "https://novalearn.ai"},
    )

    assert r.status_code == 503
    failing_mail.send.assert_awaited_once()
