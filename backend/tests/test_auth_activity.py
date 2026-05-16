from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.auth import router as auth_router
from src.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from src.config import AuthSettings


def _activity_service() -> SimpleNamespace:
    return SimpleNamespace(log_event_fire_and_forget=Mock())


def _request(activity_service: object | None = None, *, path: str = "/auth/login") -> SimpleNamespace:
    state = SimpleNamespace(container=SimpleNamespace(session_factory=object()))
    if activity_service is not None:
        state.activity_service = activity_service
    return SimpleNamespace(app=SimpleNamespace(state=state), url=SimpleNamespace(path=path), method="POST")


def _events(activity_service: SimpleNamespace) -> list:
    return [call.args[0] for call in activity_service.log_event_fire_and_forget.call_args_list]


def _assert_no_sensitive_payload(event, *raw_values: str) -> None:
    dumped = json.dumps(
        {
            "metadata": event.metadata or {},
            "replay_payload": event.replay_payload or {},
        },
        default=str,
    )
    for raw_value in raw_values:
        assert raw_value not in dumped


@pytest.mark.asyncio
async def test_register_logs_user_registered_activity_without_sensitive_metadata() -> None:
    activity = _activity_service()
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)

    with patch(
        "src.auth.router.auth_svc.register_user",
        new_callable=AsyncMock,
        return_value=user,
    ):
        await auth_router.register(
            body=RegisterRequest(
                email="student@example.com",
                password="secret-password",
                ref_code="REF123",
                visitor_id="visitor-1",
            ),
            db=AsyncMock(),
            request=_request(activity, path="/auth/register"),
            background_tasks=BackgroundTasks(),
        )

    event = _events(activity)[0]
    assert event.user_id == user_id
    assert event.event_type == "user_registered"
    assert event.event_group == "auth"
    assert event.entity_type == "user"
    assert event.entity_id == user_id
    assert event.metadata == {"auth_method": "password", "has_referral": True}
    _assert_no_sensitive_payload(event, "student@example.com", "secret-password", "REF123", "visitor-1")


@pytest.mark.asyncio
async def test_login_logs_user_logged_in_activity_without_sensitive_metadata() -> None:
    activity = _activity_service()
    user_id = uuid.uuid4()
    settings = AuthSettings(secret_key="secret-key-at-least-32-characters!!")
    tokens = TokenPair(
        access_token="raw-access-token",
        refresh_token="raw-refresh-token",
        expires_in=3600,
    )

    with patch(
        "src.auth.router.auth_svc.login_user",
        new_callable=AsyncMock,
        return_value=tokens,
    ), patch(
        "src.auth.router.auth_svc.decode_access_token",
        return_value=(user_id, "access-jti"),
    ):
        result = await auth_router.login(
            body=LoginRequest(email="student@example.com", password="secret-password"),
            db=AsyncMock(),
            settings=settings,
            request=_request(activity, path="/auth/login"),
        )

    assert result is tokens
    event = _events(activity)[0]
    assert event.user_id == user_id
    assert event.event_type == "user_logged_in"
    assert event.event_group == "auth"
    assert event.metadata == {"auth_method": "password"}
    _assert_no_sensitive_payload(
        event,
        "student@example.com",
        "secret-password",
        "raw-access-token",
        "raw-refresh-token",
    )


@pytest.mark.asyncio
async def test_login_failure_does_not_log_activity() -> None:
    activity = _activity_service()

    with patch(
        "src.auth.router.auth_svc.login_user",
        new_callable=AsyncMock,
        side_effect=auth_router.auth_svc.AuthError("Invalid credentials"),
    ):
        with pytest.raises(HTTPException):
            await auth_router.login(
                body=LoginRequest(email="student@example.com", password="wrong-password"),
                db=AsyncMock(),
                settings=AuthSettings(secret_key="secret-key-at-least-32-characters!!"),
                request=_request(activity, path="/auth/login"),
            )

    assert _events(activity) == []


@pytest.mark.asyncio
async def test_logout_logs_user_logged_out_when_token_is_revoked() -> None:
    activity = _activity_service()
    user_id = uuid.uuid4()

    with patch(
        "src.auth.router.auth_svc.logout_user",
        new_callable=AsyncMock,
        return_value=user_id,
    ):
        await auth_router.logout(
            body=RefreshRequest(refresh_token="raw-refresh-token"),
            db=AsyncMock(),
            request=_request(activity, path="/auth/logout"),
        )

    event = _events(activity)[0]
    assert event.user_id == user_id
    assert event.event_type == "user_logged_out"
    assert event.event_group == "auth"
    assert event.metadata == {"auth_method": "refresh_token"}
    _assert_no_sensitive_payload(event, "raw-refresh-token")
