from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.config import AuthSettings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "openid email profile"

# https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest
_GOOGLE_PROMPT_ALLOWED = frozenset({"none", "login", "consent", "select_account"})


def normalize_google_oauth_prompt(prompt: str | None) -> str:
    """
    Return a valid Google `prompt` parameter value.

    If `prompt` is None or empty, defaults to ``select_account`` so users always
    see the account chooser unless they override via query (e.g. ``?prompt=none``).
    """
    if prompt is None:
        return "select_account"
    stripped = prompt.strip()
    if not stripped:
        return "select_account"
    if len(stripped) > 128:
        raise ValueError("prompt is too long")
    parts = stripped.split()
    if not all(p in _GOOGLE_PROMPT_ALLOWED for p in parts):
        raise ValueError(
            "Invalid prompt: use space-separated tokens from "
            f"{sorted(_GOOGLE_PROMPT_ALLOWED)}"
        )
    return " ".join(parts)


def oauth_state_jwt(
    settings: AuthSettings,
    *,
    ref_code: str | None = None,
    visitor_id: str | None = None,
) -> str:
    payload: dict = {
        "typ": "google_oauth_state",
        "nonce": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    if ref_code:
        payload["ref_code"] = ref_code
    if visitor_id:
        payload["visitor_id"] = visitor_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_oauth_state_jwt(state: str, settings: AuthSettings) -> dict:
    """Decode and validate the OAuth state JWT. Returns the full payload."""
    payload = jwt.decode(state, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("typ") != "google_oauth_state":
        raise JWTError("Wrong token type")
    return payload


def google_is_configured(settings: AuthSettings) -> bool:
    g = settings.google
    return bool(
        g.enabled
        and g.client_id
        and g.client_secret
        and g.redirect_uri
        and g.frontend_redirect_url
    )


def build_google_authorization_url(
    settings: AuthSettings,
    *,
    prompt: str | None = None,
    ref_code: str | None = None,
    visitor_id: str | None = None,
) -> str:
    if not google_is_configured(settings):
        raise ValueError("Google OAuth is not fully configured")
    prompt_value = normalize_google_oauth_prompt(prompt)
    state = oauth_state_jwt(settings, ref_code=ref_code, visitor_id=visitor_id)
    params = {
        "client_id": settings.google.client_id,
        "redirect_uri": settings.google.redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": prompt_value,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_authorization_code(code: str, settings: AuthSettings) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google.client_id,
                "client_secret": settings.google.client_secret,
                "redirect_uri": settings.google.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if r.status_code >= 400:
        logger.warning("Google token exchange failed: %s %s", r.status_code, r.text)
        r.raise_for_status()
    return r.json()


def verify_google_id_token(id_token_str: str, client_id: str) -> dict:
    request = google_requests.Request()
    return google_id_token.verify_oauth2_token(id_token_str, request, client_id)


async def verify_google_id_token_async(id_token_str: str, client_id: str) -> dict:
    return await asyncio.to_thread(verify_google_id_token, id_token_str, client_id)
