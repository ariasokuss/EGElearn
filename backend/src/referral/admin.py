from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_admin_secret
from src.auth.models import User
from src.referral import service as ref_svc
from src.referral.models import ReferralSource

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_CODE_RE = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")

router = APIRouter(
    prefix="/admin/referrals",
    tags=["admin"],
    dependencies=[Depends(require_admin_secret)],
    include_in_schema=False,
)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def referral_admin_page(
    request: Request,
    db: DbDep,
    error: str | None = None,
    ok: str | None = None,
):
    rows = await ref_svc.list_all_sources_with_stats(db)
    return templates.TemplateResponse(
        request,
        "referral_dashboard.html",
        {
            "title": "Admin Referrals",
            "rows": rows,
            "error": error,
            "ok": ok,
            "generated_at": datetime.now(timezone.utc),
        },
    )


@router.post("")
async def create_source(
    db: DbDep,
    email: Annotated[str, Form()],
    code: Annotated[str, Form()],
    label: Annotated[str, Form()] = "",
):
    if not _CODE_RE.match(code):
        return RedirectResponse(
            "/admin/referrals?error=invalid-code", status_code=status.HTTP_303_SEE_OTHER
        )

    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        return RedirectResponse(
            "/admin/referrals?error=user-not-found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await ref_svc.create_source(db, user.id, code, label or None)
        await db.commit()
    except ref_svc.ReferralError:
        return RedirectResponse(
            "/admin/referrals?error=code-taken",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        "/admin/referrals?ok=created", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{source_id}")
async def referral_detail_page(
    request: Request,
    source_id: uuid.UUID,
    db: DbDep,
):
    detail = await ref_svc.get_source_detail(db, source_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        request,
        "referral_detail.html",
        {
            "title": f"Referral {detail.source.code}",
            "detail": detail,
            "generated_at": datetime.now(timezone.utc),
        },
    )


@router.post("/{source_id}/toggle")
async def toggle_source(source_id: uuid.UUID, db: DbDep):
    src = await db.scalar(
        select(ReferralSource).where(ReferralSource.id == source_id)
    )
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    src.is_active = not src.is_active
    await db.commit()
    return RedirectResponse(
        "/admin/referrals?ok=toggled", status_code=status.HTTP_303_SEE_OTHER
    )
