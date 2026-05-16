from __future__ import annotations

import hashlib
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
    RefreshToken,
    RevokedAccessToken,
    User,
)
from src.auth.google_oauth import verify_google_id_token_async
from src.auth.schemas import TokenPair
from src.config import AuthSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password helpers  (bcrypt directly — avoids passlib/bcrypt 4.x compat bug)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _make_access_token(user_id: uuid.UUID, jti: str, settings: AuthSettings) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_desktop_login_token(
    user_id: uuid.UUID,
    settings: AuthSettings,
    *,
    expires_minutes: int = 10,
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "desktop_login",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str, settings: AuthSettings) -> tuple[uuid.UUID, str]:
    """
    Validate and decode an access token.
    Returns (user_id, jti).
    Raises jose.JWTError on any failure.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    jti = payload.get("jti")
    if not jti:
        raise JWTError("Missing jti")
    return uuid.UUID(payload["sub"]), jti


async def is_jti_revoked(db: AsyncSession, jti: str) -> bool:
    row = await db.scalar(
        select(RevokedAccessToken).where(RevokedAccessToken.jti == jti)
    )
    return row is not None


async def revoke_access_token(
    db: AsyncSession,
    jti: str,
    expires_at: datetime,
) -> None:
    db.add(RevokedAccessToken(jti=jti, expires_at=expires_at))
    await db.commit()


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_raw_token() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# High-level auth operations (all take an AsyncSession)
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised for credential / business-logic failures (map to 401/409)."""


async def get_or_create_dev_user(
    db: AsyncSession,
    email: str,
) -> User:
    """Return the configured dev user, creating it on first use."""
    email = _normalize_email(email)
    user = await db.scalar(select(User).where(User.email == email))
    if user:
        if user.is_active:
            return user
        user.is_active = True
        await db.commit()
        await db.refresh(user)
        return user

    user = User(email=email, hashed_password=hash_password(str(uuid.uuid4())))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Provisioned dev bypass user %s", user.id)
    return user


def _normalize_email(email: str) -> str:
    """Normalize an email for storage and lookup: trim + lowercase."""
    return email.strip().lower()


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    ref_code: str | None = None,
    visitor_id: str | None = None,
) -> User:
    email = _normalize_email(email)
    # duplicate check
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        raise AuthError("Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        pending_ref_code=ref_code,
        pending_visitor_id=visitor_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Registered user %s", user.id)
    return user


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    settings: AuthSettings,
) -> TokenPair:
    email = _normalize_email(email)
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        raise AuthError("Invalid credentials")
    if user.hashed_password is None:
        raise AuthError("Invalid credentials")
    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid credentials")
    if not user.is_active:
        raise AuthError("Account disabled")

    return await _issue_token_pair(db, user, settings)


async def get_or_create_google_user(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
    email_verified: bool,
) -> tuple[User, bool]:
    email_norm = email.strip().lower()

    by_sub = await db.scalar(select(User).where(User.google_sub == google_sub))
    if by_sub:
        if not by_sub.is_active:
            raise AuthError("Account disabled")
        return by_sub, False

    by_email = await db.scalar(select(User).where(User.email == email_norm))
    if by_email:
        if by_email.google_sub is not None and by_email.google_sub != google_sub:
            raise AuthError("Google account conflict for this email")
        if not by_email.is_active:
            raise AuthError("Account disabled")
        # Link Google to existing password account
        by_email.google_sub = google_sub
        if email_verified:
            by_email.is_verified = True
        await db.commit()
        await db.refresh(by_email)
        logger.info("Linked Google identity to user %s", by_email.id)
        return by_email, False

    user = User(
        email=email_norm,
        hashed_password=None,
        google_sub=google_sub,
        is_verified=email_verified,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Registered user via Google %s", user.id)
    return user, True


async def complete_google_login(
    db: AsyncSession,
    id_token_str: str,
    settings: AuthSettings,
) -> tuple[User, bool, TokenPair]:
    claims = await verify_google_id_token_async(id_token_str, settings.google.client_id)
    google_sub = claims.get("sub")
    email = claims.get("email")
    email_verified = bool(claims.get("email_verified", False))
    if not google_sub or not email:
        raise AuthError("Google token missing required claims")

    user, created = await get_or_create_google_user(
        db,
        google_sub=str(google_sub),
        email=str(email),
        email_verified=email_verified,
    )
    tokens = await _issue_token_pair(db, user, settings)
    return user, created, tokens


async def cleanup_expired_revocations(db: AsyncSession) -> int:
    """Delete revoked access token entries whose JWT has already expired."""
    result = await db.execute(
        delete(RevokedAccessToken).where(
            RevokedAccessToken.expires_at < datetime.now(UTC)
        )
    )
    await db.commit()
    return result.rowcount  # type: ignore[return-value]


async def refresh_tokens(
    db: AsyncSession,
    raw_refresh_token: str,
    settings: AuthSettings,
) -> TokenPair:
    token_hash = _hash_token(raw_refresh_token)
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if not row or row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise AuthError("Invalid or expired refresh token")

    user_id = row.user_id
    if row.access_jti and row.access_token_expires_at:
        await revoke_access_token(db, row.access_jti, row.access_token_expires_at)
    await db.delete(row)
    await db.commit()

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise AuthError("Account not found or disabled")

    # Opportunistic cleanup: ~1 in 50 refreshes, purge expired revocations
    if random.randint(1, 50) == 1:
        try:
            await cleanup_expired_revocations(db)
        except Exception:
            logger.debug("Revocation cleanup skipped (non-critical)")

    return await _issue_token_pair(db, user, settings)


async def exchange_desktop_login_token(
    db: AsyncSession,
    token: str,
    settings: AuthSettings,
) -> TokenPair:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "desktop_login":
            raise JWTError("Not a desktop login token")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError) as exc:
        raise AuthError("Invalid or expired desktop login link") from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise AuthError("Invalid or expired desktop login link")

    return await _issue_token_pair(db, user, settings)


async def logout_user(db: AsyncSession, raw_refresh_token: str) -> uuid.UUID | None:
    token_hash = _hash_token(raw_refresh_token)
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if row:
        user_id = row.user_id
        if row.access_jti and row.access_token_expires_at:
            await revoke_access_token(db, row.access_jti, row.access_token_expires_at)
        await db.delete(row)
        await db.commit()
        return user_id
    return None


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


async def _issue_token_pair(
    db: AsyncSession,
    user: User,
    settings: AuthSettings,
) -> TokenPair:
    raw = _new_raw_token()
    jti = _new_raw_token()
    refresh_expires_at = datetime.now(UTC) + timedelta(
        days=settings.refresh_token_expire_days
    )
    access_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            access_jti=jti,
            access_token_expires_at=access_expires_at,
            expires_at=refresh_expires_at,
        )
    )
    await db.commit()

    access_token = _make_access_token(user.id, jti, settings)
    return TokenPair(
        access_token=access_token,
        refresh_token=raw,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_user_if_jti_valid(
    db: AsyncSession, user_id: uuid.UUID, jti: str
) -> User | None:
    """Fetch user and check JTI revocation in a single query.

    Returns the User if found AND the JTI is not revoked, else None.
    """
    return await db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            ~exists(
                select(RevokedAccessToken.jti).where(RevokedAccessToken.jti == jti)
            ),
        )
    )
