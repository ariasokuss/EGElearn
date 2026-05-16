import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db
from src.referral import service as ref_svc
from src.referral.schemas import (
    CreateSourceRequest,
    DashboardOut,
    SourceOut,
    SourceStats,
    TrackVisitRequest,
    UpdateSourceRequest,
)

router = APIRouter(prefix="/referral", tags=["referral"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Source CRUD (authenticated — creator manages their links)
# ---------------------------------------------------------------------------


@router.post(
    "/sources",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    body: CreateSourceRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> SourceOut:
    try:
        source = await ref_svc.create_source(db, current_user.id, body.code, body.label)
        await db.commit()
        return SourceOut.model_validate(source)
    except ref_svc.ReferralError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    db: DbDep,
    current_user: CurrentUser,
) -> list[SourceOut]:
    sources = await ref_svc.list_sources(db, current_user.id)
    return [SourceOut.model_validate(s) for s in sources]


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: uuid.UUID,
    body: UpdateSourceRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> SourceOut:
    try:
        kwargs: dict = {}
        if body.label is not None:
            kwargs["label"] = body.label
        if body.is_active is not None:
            kwargs["is_active"] = body.is_active
        source = await ref_svc.update_source(db, source_id, current_user.id, **kwargs)
        await db.commit()
        return SourceOut.model_validate(source)
    except ref_svc.ReferralError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source(
    source_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> None:
    try:
        await ref_svc.update_source(db, source_id, current_user.id, is_active=False)
        await db.commit()
    except ref_svc.ReferralError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Tracking (public)
# ---------------------------------------------------------------------------


@router.post(
    "/track/visit",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def track_visit(
    body: TrackVisitRequest,
    request: Request,
    db: DbDep,
) -> None:
    ip = request.client.host if request.client else None
    await ref_svc.track_visit(db, body.code, body.visitor_id, body.landing_page, ip)
    await db.commit()


# ---------------------------------------------------------------------------
# Dashboard (authenticated)
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: DbDep,
    current_user: CurrentUser,
) -> DashboardOut:
    stats = await ref_svc.get_dashboard(db, current_user.id)
    totals = None
    if stats:
        totals = SourceStats(
            source_id=uuid.UUID(int=0),
            code="__total__",
            label=None,
            visits_count=sum(s.visits_count for s in stats),
            unique_visitors=sum(s.unique_visitors for s in stats),
            registrations=sum(s.registrations for s in stats),
            purchases=sum(s.purchases for s in stats),
        )
    return DashboardOut(sources=stats, totals=totals)


@router.get("/dashboard/{source_id}", response_model=SourceStats)
async def dashboard_source(
    source_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> SourceStats:
    from sqlalchemy import select
    from src.referral.models import ReferralSource

    source = await db.scalar(
        select(ReferralSource).where(
            ReferralSource.id == source_id,
            ReferralSource.user_id == current_user.id,
        )
    )
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source not found")
    return await ref_svc.get_source_stats(db, source)
