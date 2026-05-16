from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_container,
    get_db,
    require_admin_secret,
)
from src.runtime import AppContainer
from src.usage.schemas import (
    AdminUsageOverviewResponse,
    AdminUserUsageDetailResponse,
    UsageStatsResponse,
)
from src.usage.service import UsageService

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("month", pattern="^(day|week|month|all)$"),
) -> UsageStatsResponse:
    svc = UsageService(container.session_factory)
    stats = await svc.get_user_stats(db, current_user.id, period=period)
    return UsageStatsResponse(**stats)


@router.get(
    "/admin/overview",
    response_model=AdminUsageOverviewResponse,
    dependencies=[Depends(require_admin_secret)],
)
async def get_admin_usage_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    limit: int = Query(100, ge=1, le=500),
    email: str | None = Query(None, max_length=255),
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> AdminUsageOverviewResponse:
    svc = UsageService(container.session_factory)
    overview = await svc.get_admin_usage_overview(
        db,
        period=period,
        limit=limit,
        email=email,
        month=month,
    )
    return AdminUsageOverviewResponse(**overview)


@router.get(
    "/admin/users/{user_id}/detail",
    response_model=AdminUserUsageDetailResponse,
    dependencies=[Depends(require_admin_secret)],
)
async def get_admin_user_usage_detail(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[AppContainer, Depends(get_container)],
    period: str = Query("month", pattern="^(day|week|month|all)$"),
    limit: int = Query(200, ge=1, le=5000),
) -> AdminUserUsageDetailResponse:
    svc = UsageService(container.session_factory)
    detail = await svc.get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period=period,
        limit=limit,
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserUsageDetailResponse(**detail)
