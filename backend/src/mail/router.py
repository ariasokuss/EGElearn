from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db, get_mail_client, get_settings
from src.config import Settings
from src.mail.client import MailClient, MailError
from src.mail.schemas import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    SendDesktopLinkRequest,
    SendVerificationRequest,
    VerifyEmailRequest,
)
from src.mail.service import MailServiceError
from src.mail import service as mail_svc

router = APIRouter(prefix="/mail", tags=["mail"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
MailDep = Annotated[MailClient, Depends(get_mail_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _mail_error_to_http(exc: MailServiceError) -> HTTPException:
    """Map MailServiceError to 429 (lockout/throttle) or 400 (everything else)."""
    msg = str(exc)
    code = (
        status.HTTP_429_TOO_MANY_REQUESTS
        if msg.startswith("Too many")
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=msg)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@router.post(
    "/send-verification",
    response_model=MessageResponse,
    summary="Send a 6-digit email verification code",
)
async def send_verification(
    body: SendVerificationRequest,
    db: DbDep,
    mail: MailDep,
    settings: SettingsDep,
) -> MessageResponse:
    try:
        await mail_svc.send_verification_code(db, body.email, settings.mail, mail)
    except MailServiceError as exc:
        raise _mail_error_to_http(exc) from exc
    except MailError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Mail service unavailable."
        ) from exc
    return MessageResponse(message="Verification code sent.")


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify email address with the 6-digit code",
)
async def verify_email(
    body: VerifyEmailRequest,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    try:
        await mail_svc.verify_email(db, body.email, body.code, settings.mail)
    except MailServiceError as exc:
        raise _mail_error_to_http(exc) from exc
    return MessageResponse(message="Email verified successfully.")


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Send a password reset link to the given email",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: DbDep,
    mail: MailDep,
    settings: SettingsDep,
) -> MessageResponse:
    try:
        await mail_svc.send_password_reset(
            db, body.email, settings.mail, mail, body.redirect_url
        )
    except MailServiceError as exc:
        raise _mail_error_to_http(exc) from exc
    except MailError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Mail service unavailable."
        ) from exc
    # Always return the same message — prevents user enumeration
    return MessageResponse(
        message="If that email is registered, a reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Set a new password using a reset token",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    try:
        await mail_svc.reset_password(db, body.token, body.new_password, settings.mail)
    except MailServiceError as exc:
        raise _mail_error_to_http(exc) from exc
    return MessageResponse(message="Password reset successfully.")


# ---------------------------------------------------------------------------
# Desktop link (sent to authenticated user from mobile stub)
# ---------------------------------------------------------------------------


@router.post(
    "/send-desktop-link",
    response_model=MessageResponse,
    summary="Email the current user a link to open NovaLearn on desktop",
)
async def send_desktop_link(
    body: SendDesktopLinkRequest,
    user: CurrentUser,
    mail: MailDep,
    settings: SettingsDep,
) -> MessageResponse:
    try:
        await mail_svc.send_desktop_link(user, str(body.desktop_url), mail, settings.auth)
    except MailError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Mail service unavailable."
        ) from exc
    return MessageResponse(message="Link sent.")
