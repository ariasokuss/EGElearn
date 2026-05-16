from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_container, get_db, require_admin_secret
from src.runtime import AppContainer
from src.usage.schemas import (
    AdminUsageOverviewResponse,
    AdminUserUsageDetailResponse,
)
from src.usage.service import UsageService

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(
    prefix="/admin/usage",
    tags=["admin"],
    dependencies=[Depends(require_admin_secret)],
    include_in_schema=False,
)


@router.get("/static/style.css", include_in_schema=False)
async def usage_admin_style() -> FileResponse:
    return FileResponse(
        _TEMPLATES_DIR / "usage.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/data", response_model=AdminUsageOverviewResponse)
async def usage_admin_data(
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    limit: int = Query(50, ge=1, le=500),
    email: str | None = Query(None, max_length=255),
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> AdminUsageOverviewResponse:
    svc = UsageService(container.session_factory)
    data = await svc.get_admin_usage_overview(
        db,
        period=period,
        limit=limit,
        email=email,
        month=month,
    )
    return AdminUsageOverviewResponse(**data)


@router.get("", include_in_schema=False)
async def usage_admin_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    limit: int = Query(50, ge=1, le=500),
    email: str | None = Query(None, max_length=255),
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    svc = UsageService(container.session_factory)
    overview = await svc.get_admin_usage_overview(
        db,
        period=period,
        limit=limit,
        email=email,
        month=month,
    )
    current_month = overview.get("activity_chart", {}).get("selected_month")

    return templates.TemplateResponse(
        request,
        "usage_dashboard.html",
        {
            "title": "Admin Usage",
            "overview": overview,
            "current_period": period,
            "current_limit": limit,
            "current_email": email or "",
            "current_month": current_month,
            "period_options": ["day", "week", "month", "all"],
            "generated_at": datetime.now(timezone.utc),
        },
    )


@router.get("/users/{user_id}/data", response_model=AdminUserUsageDetailResponse)
async def usage_admin_user_data(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("week", pattern="^(day|week|month|all)$"),
    limit: int = Query(200, ge=1, le=5000),
) -> AdminUserUsageDetailResponse:
    svc = UsageService(container.session_factory)
    data = await svc.get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period=period,
        limit=limit,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserUsageDetailResponse(**data)


@router.get("/users/{user_id}", include_in_schema=False)
async def usage_admin_user_page(
    request: Request,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("week", pattern="^(day|week|month|all)$"),
    limit: int = Query(200, ge=1, le=5000),
):
    svc = UsageService(container.session_factory)
    detail = await svc.get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period=period,
        limit=limit,
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return templates.TemplateResponse(
        request,
        "usage_user_detail.html",
        {
            "title": "User Usage",
            "detail": detail,
            "current_period": period,
            "current_limit": limit,
            "period_options": ["day", "week", "month", "all"],
            "generated_at": datetime.now(timezone.utc),
        },
    )
