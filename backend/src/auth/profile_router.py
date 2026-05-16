"""User profile endpoints: display name, avatar, password change, email change."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db, get_s3, get_mail_client, get_settings
from src.auth.models import RefreshToken, User
from src.auth.schemas import (
    ChangePasswordRequest,
    ConfirmEmailChangeRequest,
    RequestEmailChangeRequest,
    UpdateProfileRequest,
)
from src.auth.service import hash_password, verify_password
from src.core.s3 import S3Client
from src.mail.client import MailClient, MailError
from src.mail.models import PendingEmailChange
from src.mail.renderer import render_email_change_code, render_email_change_notice
from src.config import Settings

router = APIRouter(prefix="/users/me", tags=["profile"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]
S3Dep = Annotated[S3Client, Depends(get_s3)]
MailDep = Annotated[MailClient, Depends(get_mail_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _hash_code(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
AVATAR_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.patch(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update profile (display name)",
)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> None:
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(display_name=body.display_name)
    )
    await db.commit()


@router.post(
    "/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Upload avatar (multipart)",
)
async def upload_avatar(
    current_user: CurrentUser,
    db: DbDep,
    s3: S3Dep,
    file: UploadFile = File(...),
) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type: {file.content_type}. Use JPEG, PNG, or WebP.",
        )

    data = await file.read()
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be under 5MB")

    ext = AVATAR_EXTENSIONS.get(file.content_type, ".jpg")
    s3_key = f"avatars/{current_user.id}/{uuid.uuid4()}{ext}"

    # Upload to S3
    await s3.upload_bytes(s3_key, data, content_type=file.content_type)

    # Delete old avatar if exists
    old_key = current_user.avatar_s3_key
    if old_key and old_key != s3_key:
        await s3.delete_object(old_key)

    # Save new key
    await db.execute(
        update(User).where(User.id == current_user.id).values(avatar_s3_key=s3_key)
    )
    await db.commit()


@router.get(
    "/avatar",
    summary="Proxy avatar image from S3",
    responses={
        200: {"content": {"image/*": {}}},
        404: {"description": "No avatar set"},
    },
)
async def get_avatar(
    current_user: CurrentUser,
    s3: S3Dep,
) -> Response:
    if not current_user.avatar_s3_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No avatar set")
    data = await s3.download_bytes(current_user.avatar_s3_key)
    # Infer content type from key extension
    key = current_user.avatar_s3_key
    if key.endswith(".png"):
        ct = "image/png"
    elif key.endswith(".webp"):
        ct = "image/webp"
    else:
        ct = "image/jpeg"
    return Response(
        content=data,
        media_type=ct,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete(
    "/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete avatar",
)
async def delete_avatar(
    current_user: CurrentUser,
    db: DbDep,
    s3: S3Dep,
) -> None:
    if current_user.avatar_s3_key:
        await s3.delete_object(current_user.avatar_s3_key)
    await db.execute(
        update(User).where(User.id == current_user.id).values(avatar_s3_key=None)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password (requires current password)",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbDep,
) -> None:
    if not current_user.hashed_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Password login not set up. Use Google sign-in.",
        )
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="New password must differ from current"
        )

    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(hashed_password=hash_password(body.new_password))
    )
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == current_user.id))
    await db.commit()


# ---------------------------------------------------------------------------
# Email change  (request code → verify code → swap email)
# ---------------------------------------------------------------------------


@router.post(
    "/email/request",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request email change — sends verification code to new email",
)
async def request_email_change(
    body: RequestEmailChangeRequest,
    current_user: CurrentUser,
    db: DbDep,
    mail: MailDep,
    settings: SettingsDep,
) -> None:
    # Verify current password
    if not current_user.hashed_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Password login not set up. Use Google sign-in.",
        )
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Password is incorrect")

    new_email = body.new_email.lower().strip()

    if new_email == current_user.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="That's already your email")

    # Check new email isn't taken
    existing = await db.scalar(select(User).where(User.email == new_email))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already in use")

    # Throttle
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent = await db.scalar(
        select(func.count(PendingEmailChange.id)).where(
            PendingEmailChange.user_id == current_user.id,
            PendingEmailChange.created_at >= one_hour_ago,
        )
    )
    if (recent or 0) >= settings.mail.max_sends_per_hour:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait before requesting another code.",
        )

    # Delete prior pending changes for this user
    await db.execute(
        delete(PendingEmailChange).where(PendingEmailChange.user_id == current_user.id)
    )

    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        PendingEmailChange(
            user_id=current_user.id,
            new_email=new_email,
            code_hash=_hash_code(raw_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            attempts=0,
        )
    )
    await db.commit()

    html_body = render_email_change_code(raw_code, new_email)
    try:
        await mail.send_security(
            to=new_email,
            subject="Confirm your new NovaLearn email",
            html_body=html_body,
        )
    except MailError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Mail service unavailable."
        ) from exc

    # Security notice to the current address — best-effort, never blocks the flow
    try:
        await mail.send_security(
            to=current_user.email,
            subject="Your NovaLearn email address is being changed",
            html_body=render_email_change_notice(new_email),
        )
    except MailError:
        logger.warning(
            "Failed to send email-change notice to old address %s for user %s",
            current_user.email,
            current_user.id,
        )

    logger.info("Email change code sent to %s for user %s", new_email, current_user.id)


@router.post(
    "/email/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm email change with verification code",
)
async def confirm_email_change(
    body: ConfirmEmailChangeRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    record = await db.scalar(
        select(PendingEmailChange).where(
            PendingEmailChange.user_id == current_user.id
        )
    )
    if not record:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No pending email change")

    # Lockout check
    if record.locked_until and record.locked_until.replace(tzinfo=UTC) > datetime.now(UTC):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again after {record.locked_until.strftime('%H:%M UTC')}.",
        )

    # Expiry check
    if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Code expired. Request a new one."
        )

    # Wrong code
    if record.code_hash != _hash_code(body.code):
        record.attempts += 1
        if record.attempts >= settings.mail.max_code_attempts:
            record.locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.mail.lockout_minutes
            )
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    # Check new email still not taken
    existing = await db.scalar(select(User).where(User.email == record.new_email))
    if existing:
        await db.delete(record)
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already in use")

    # Swap email
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(email=record.new_email)
    )
    await db.delete(record)
    await db.commit()
    logger.info("Email changed to %s for user %s", record.new_email, current_user.id)
