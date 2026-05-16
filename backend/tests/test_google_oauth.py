from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from src.auth.google_oauth import (
    build_google_authorization_url,
    decode_oauth_state_jwt,
    google_is_configured,
    normalize_google_oauth_prompt,
    oauth_state_jwt,
)
from src.auth.models import User
from src.auth.service import (
    AuthError,
    complete_google_login,
    create_desktop_login_token,
    exchange_desktop_login_token,
    login_user,
)
from src.config import AuthSettings, GoogleOAuthSettings


def _google_settings(**kwargs) -> AuthSettings:
    base = {
        "secret_key": "test-secret-key-at-least-32-chars-long!!",
        "algorithm": "HS256",
        "google": GoogleOAuthSettings(
            enabled=True,
            client_id="test-client-id.apps.googleusercontent.com",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080/api/v1/auth/google/callback",
            frontend_redirect_url="http://localhost:3000/auth/callback",
            **kwargs,
        ),
    }
    return AuthSettings(**base)


def test_oauth_state_roundtrip() -> None:
    settings = _google_settings()
    state = oauth_state_jwt(settings)
    decode_oauth_state_jwt(state, settings)


def test_desktop_login_token_roundtrip() -> None:
    settings = _google_settings()
    user_id = uuid.uuid4()

    token = create_desktop_login_token(user_id, settings)
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
    )

    assert payload["type"] == "desktop_login"
    assert payload["sub"] == str(user_id)


@pytest.mark.asyncio
async def test_exchange_desktop_login_token_issues_tokens_for_active_user() -> None:
    settings = _google_settings()
    user = User(
        id=uuid.uuid4(),
        email="desktop@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    token = create_desktop_login_token(user.id, settings)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=user)

    from src.auth.schemas import TokenPair

    pair = TokenPair(access_token="a", refresh_token="r", expires_in=3600)
    with patch(
        "src.auth.service._issue_token_pair",
        new_callable=AsyncMock,
        return_value=pair,
    ):
        tokens = await exchange_desktop_login_token(mock_db, token, settings)

    assert tokens is pair
    mock_db.get.assert_awaited_once_with(User, user.id)


@pytest.mark.asyncio
async def test_exchange_desktop_login_token_rejects_wrong_token_type() -> None:
    settings = _google_settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    with pytest.raises(AuthError, match="Invalid or expired desktop login link"):
        await exchange_desktop_login_token(AsyncMock(), token, settings)


def test_google_is_configured() -> None:
    assert not google_is_configured(AuthSettings())
    assert google_is_configured(_google_settings())


def test_build_authorization_url_contains_google() -> None:
    settings = _google_settings()
    url = build_google_authorization_url(settings)
    assert "accounts.google.com" in url
    assert "client_id=test-client-id" in url or "client_id=" in url
    assert "state=" in url
    assert "prompt=select_account" in url


def test_build_authorization_url_respects_prompt_query() -> None:
    settings = _google_settings()
    url = build_google_authorization_url(settings, prompt="consent")
    assert "prompt=consent" in url


def test_normalize_prompt_default() -> None:
    assert normalize_google_oauth_prompt(None) == "select_account"
    assert normalize_google_oauth_prompt("") == "select_account"
    assert normalize_google_oauth_prompt("  ") == "select_account"


def test_normalize_prompt_invalid_raises() -> None:
    with pytest.raises(ValueError):
        normalize_google_oauth_prompt("evil")


def test_google_oauth_start_passes_prompt_to_google_url() -> None:
    settings = _google_settings()
    client = _auth_only_client(settings)
    r = client.get(
        "/api/v1/auth/google",
        params={"format": "json", "prompt": "consent"},
    )
    assert r.status_code == 200
    assert "prompt=consent" in r.json()["authorization_url"]


def test_google_oauth_invalid_prompt_400() -> None:
    settings = _google_settings()
    client = _auth_only_client(settings)
    r = client.get("/api/v1/auth/google", params={"format": "json", "prompt": "bad"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_login_rejects_oauth_only_user() -> None:
    settings = _google_settings()
    user = User(
        id=uuid.uuid4(),
        email="oauth@example.com",
        hashed_password=None,
        google_sub="google-sub-123",
        is_active=True,
        is_verified=True,
    )
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=user)

    with pytest.raises(AuthError, match="Invalid credentials"):
        await login_user(mock_db, "oauth@example.com", "password123", settings)


@pytest.mark.asyncio
async def test_complete_google_login_success() -> None:
    settings = _google_settings()
    claims = {
        "sub": "google-sub-xyz",
        "email": "newuser@example.com",
        "email_verified": True,
        "aud": settings.google.client_id,
        "iss": "https://accounts.google.com",
    }

    mock_db = AsyncMock()
    created_user = User(
        id=uuid.uuid4(),
        email="newuser@example.com",
        hashed_password=None,
        google_sub="google-sub-xyz",
        is_active=True,
        is_verified=True,
    )
    from src.auth.schemas import TokenPair

    pair = TokenPair(
        access_token="a",
        refresh_token="r",
        expires_in=3600,
    )

    with patch(
        "src.auth.service.verify_google_id_token_async",
        new_callable=AsyncMock,
        return_value=claims,
    ):
        with patch(
            "src.auth.service.get_or_create_google_user",
            new_callable=AsyncMock,
            return_value=(created_user, True),
        ):
            with patch(
                "src.auth.service._issue_token_pair",
                new_callable=AsyncMock,
                return_value=pair,
            ):
                user, created, tokens = await complete_google_login(
                    mock_db, "fake.jwt.token", settings
                )
                assert created is True
                assert user is created_user
                assert tokens.access_token == "a"


def _auth_only_client(settings: AuthSettings) -> TestClient:
    """Minimal app (no startup lifespan) — only auth router."""
    from fastapi import FastAPI

    from src.api.deps import get_auth_settings
    from src.auth.router import router as auth_router

    mini = FastAPI()
    mini.include_router(auth_router, prefix="/api/v1")
    mini.dependency_overrides[get_auth_settings] = lambda: settings
    return TestClient(mini)


def test_google_oauth_start_json_format() -> None:
    settings = _google_settings()
    client = _auth_only_client(settings)
    r = client.get("/api/v1/auth/google", params={"format": "json"})
    assert r.status_code == 200
    data = r.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]
    assert "prompt=select_account" in data["authorization_url"]


def test_google_oauth_disabled_returns_503() -> None:
    client = _auth_only_client(AuthSettings())
    r = client.get("/api/v1/auth/google", params={"format": "json"})
    assert r.status_code == 503


def test_jwt_state_tampering_rejected() -> None:
    from jose import JWTError

    settings = _google_settings()
    bad = jwt.encode(
        {"typ": "other", "exp": 9999999999},
        "wrong-key",
        algorithm="HS256",
    )
    with pytest.raises(JWTError):
        decode_oauth_state_jwt(bad, settings)
