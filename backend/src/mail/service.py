from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RefreshToken, User
from src.auth.service import create_desktop_login_token, hash_password
from src.config import AuthSettings, MailSettings
from src.mail.models import EmailVerificationCode, PasswordResetToken
from src.mail.renderer import (
    render_desktop_link_email,
    render_password_reset_email,
    render_verification_email,
)

if TYPE_CHECKING:
    from src.mail.client import MailClient

logger = logging.getLogger(__name__)


class MailServiceError(Exception):
    """Raised for mail-related business-logic failures (throttle, lockout, invalid code/token)."""


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_verification_code() -> str:
    """Return a cryptographically random 6-digit string (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


async def send_verification_code(
    db: AsyncSession,
    email: str,
    mail_settings: MailSettings,
    mail_client: "MailClient",
) -> None:
    """Generate a 6-digit code, persist its hash, and send the HTML email."""
    email = _normalize_email(email)
    # Per-email send throttle: count codes created for this email in the last hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent_count = await db.scalar(
        select(func.count(EmailVerificationCode.id)).where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.created_at >= one_hour_ago,
        )
    )
    if (recent_count or 0) >= mail_settings.max_sends_per_hour:
        raise MailServiceError(
            "Too many attempts. Please wait before requesting another code."
        )

    # Delete any existing code for this email before creating a new one
    await db.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.email == email)
    )

    raw_code = _new_verification_code()
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    db.add(
        EmailVerificationCode(
            email=email,
            code_hash=_hash_token(raw_code),
            expires_at=expires_at,
            attempts=0,
            locked_until=None,
        )
    )
    await db.commit()

    html_body = render_verification_email(raw_code)
    await mail_client.send_security(
        to=email,
        subject="Your NovaLearn verification code",
        html_body=html_body,
    )
    logger.info("Verification code sent to %s", email)


async def verify_email(
    db: AsyncSession,
    email: str,
    code: str,
    mail_settings: MailSettings,
) -> None:
    """Validate the submitted code, mark user verified, and delete the code row."""
    email = _normalize_email(email)
    record = await db.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.email == email)
    )
    if not record:
        raise MailServiceError("No verification code found for this email.")

    # Lockout check
    if record.locked_until and record.locked_until.replace(tzinfo=UTC) > datetime.now(
        UTC
    ):
        raise MailServiceError(
            f"Too many attempts. Try again after "
            f"{record.locked_until.strftime('%H:%M UTC')}."
        )

    # Expiry check
    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await db.delete(record)
        await db.commit()
        raise MailServiceError("Verification code has expired. Request a new one.")

    # Wrong code — increment attempt counter
    if record.code_hash != _hash_token(code):
        record.attempts += 1
        if record.attempts >= mail_settings.max_code_attempts:
            record.locked_until = datetime.now(UTC) + timedelta(
                minutes=mail_settings.lockout_minutes
            )
        await db.commit()
        raise MailServiceError("Invalid verification code.")

    # Success — mark user verified and clean up
    user = await db.scalar(select(User).where(User.email == email))
    pending_ref_code: str | None = None
    pending_visitor_id: str | None = None
    if user:
        user.is_verified = True
        # Drain any pending referral attribution stashed at registration.
        pending_ref_code = user.pending_ref_code
        pending_visitor_id = user.pending_visitor_id
        user.pending_ref_code = None
        user.pending_visitor_id = None
    await db.delete(record)
    await db.commit()
    logger.info("Email verified for %s", email)

    # Attribute the referral now that the address is proven. Failures must not
    # block verification — log and move on.
    if user and pending_ref_code:
        try:
            from src.referral.service import create_attribution

            await create_attribution(
                db, pending_ref_code, user.id, pending_visitor_id
            )
            await db.commit()
            logger.info(
                "Referral %s attributed for user %s on email verification",
                pending_ref_code,
                user.id,
            )
        except Exception:
            logger.exception(
                "Deferred referral attribution failed for user %s ref=%s",
                user.id,
                pending_ref_code,
            )


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


async def send_password_reset(
    db: AsyncSession,
    email: str,
    mail_settings: MailSettings,
    mail_client: "MailClient",
    redirect_url: str | None = None,
) -> None:
    """
    Generate a reset token and send the HTML email.

    Silently no-ops when the email is not registered to prevent user enumeration.
    """
    email = _normalize_email(email)
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        # Logged at INFO so the request is debuggable in dev without leaking
        # the result back to the client (HTTP response stays uniform).
        logger.info("Password reset requested for unknown email=%r", email)
        return  # deliberate silent no-op
    logger.info("Password reset requested for user %s (%s)", user.id, email)

    # Per-email send throttle: count tokens created for this user in the last hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent_count = await db.scalar(
        select(func.count(PasswordResetToken.id)).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= one_hour_ago,
        )
    )
    if (recent_count or 0) >= mail_settings.max_sends_per_hour:
        raise MailServiceError(
            "Too many attempts. Please wait before requesting another reset."
        )

    # Invalidate any prior tokens for this user
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )

    raw_token = secrets.token_hex(32)  # 64-char hex string
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=expires_at,
            attempts=0,
            locked_until=None,
        )
    )
    await db.commit()

    # Encode expiry as base64url of the UTC ISO timestamp.
    # Decode anytime with: base64.urlsafe_b64decode(exp + "==").decode()
    exp_encoded = (
        base64.urlsafe_b64encode(expires_at.isoformat().encode()).rstrip(b"=").decode()
    )
    reset_link = (
        f"{redirect_url}?token={raw_token}&exp={exp_encoded}" if redirect_url else None
    )
    html_body = render_password_reset_email(
        raw_token, expires_at=expires_at, reset_link=reset_link
    )
    await mail_client.send_security(
        to=email,
        subject="Reset your NovaLearn password",
        html_body=html_body,
    )
    logger.info("Password reset email sent to %s", email)


async def reset_password(
    db: AsyncSession,
    raw_token: str,
    new_password: str,
    mail_settings: MailSettings,
) -> None:
    """Verify the reset token, update the password, and mark the token used."""
    token_hash = _hash_token(raw_token)
    record = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if not record:
        raise MailServiceError("Invalid or expired reset token.")

    # Lockout check
    if record.locked_until and record.locked_until.replace(tzinfo=UTC) > datetime.now(
        UTC
    ):
        raise MailServiceError(
            f"Too many attempts. Try again after "
            f"{record.locked_until.strftime('%H:%M UTC')}."
        )

    if record.used_at is not None:
        raise MailServiceError("This reset link has already been used.")

    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise MailServiceError("Reset link has expired. Request a new one.")

    user = await db.get(User, record.user_id)
    if not user or not user.is_active:
        raise MailServiceError("User not found or account disabled.")

    user.hashed_password = hash_password(new_password)
    record.used_at = datetime.now(UTC)
    # Revoke all active sessions — compromised accounts get a clean slate after reset
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.commit()
    logger.info("Password reset for user %s", user.id)


# ---------------------------------------------------------------------------
# Desktop link (mobile stub: "email me the link to open on desktop")
# ---------------------------------------------------------------------------


async def send_desktop_link(
    user: User,
    desktop_url: str,
    mail_client: "MailClient",
    auth_settings: AuthSettings,
) -> None:
    """Send the authenticated user an email with a link to open NovaLearn on desktop."""
    login_token = create_desktop_login_token(user.id, auth_settings)
    login_url = _build_desktop_login_url(desktop_url, login_token)
    html_body = render_desktop_link_email(
        login_url,
        display_url=desktop_url,
    )
    await mail_client.send(
        to=user.email,
        subject="Link",
        html_body=html_body,
    )
    logger.info("Desktop link email sent to user %s", user.id)


def _build_desktop_login_url(desktop_url: str, token: str) -> str:
    parsed = urlsplit(desktop_url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/auth/callback",
            f"desktop_login_token={token}",
            "",
        )
    )
