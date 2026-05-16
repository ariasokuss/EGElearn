from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.referral.admin_schemas import (
    AdminAttributionRow,
    AdminSourceDetail,
    AdminSourceRow,
    AdminVisitRow,
)
from src.referral.models import ReferralAttribution, ReferralSource, ReferralVisit
from src.referral.schemas import SourceStats


class ReferralError(Exception):
    pass


async def create_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    code: str,
    label: str | None = None,
) -> ReferralSource:
    existing = await db.scalar(
        select(ReferralSource).where(ReferralSource.code == code)
    )
    if existing:
        raise ReferralError(f"Code '{code}' is already taken")

    source = ReferralSource(user_id=user_id, code=code, label=label)
    db.add(source)
    await db.flush()
    return source


async def list_sources(db: AsyncSession, user_id: uuid.UUID) -> list[ReferralSource]:
    result = await db.scalars(
        select(ReferralSource)
        .where(ReferralSource.user_id == user_id)
        .order_by(ReferralSource.created_at.desc())
    )
    return list(result.all())


async def update_source(
    db: AsyncSession,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    label: str | None = ...,
    is_active: bool | None = None,
) -> ReferralSource:
    source = await db.scalar(
        select(ReferralSource).where(
            ReferralSource.id == source_id,
            ReferralSource.user_id == user_id,
        )
    )
    if not source:
        raise ReferralError("Source not found")
    if label is not ...:
        source.label = label
    if is_active is not None:
        source.is_active = is_active
    await db.flush()
    return source


async def track_visit(
    db: AsyncSession,
    code: str,
    visitor_id: str,
    landing_page: str | None = None,
    ip_address: str | None = None,
) -> bool:
    """Record an anonymous visit. Returns True if recorded, False if source not found."""
    source = await db.scalar(
        select(ReferralSource).where(
            ReferralSource.code == code,
            ReferralSource.is_active.is_(True),
        )
    )
    if not source:
        return False

    ip_hash = hashlib.sha256(ip_address.encode()).hexdigest() if ip_address else None
    visit = ReferralVisit(
        source_id=source.id,
        visitor_id=visitor_id,
        landing_page=landing_page,
        ip_hash=ip_hash,
    )
    db.add(visit)
    await db.flush()
    return True


async def create_attribution(
    db: AsyncSession,
    ref_code: str,
    user_id: uuid.UUID,
    visitor_id: str | None = None,
) -> bool:
    """Create first-touch attribution. Returns True if created, False if already exists or source not found."""
    source = await db.scalar(
        select(ReferralSource).where(ReferralSource.code == ref_code)
    )
    if not source:
        return False

    # Idempotent: skip if this user already has an attribution
    existing = await db.scalar(
        select(ReferralAttribution).where(ReferralAttribution.user_id == user_id)
    )
    if existing:
        return False

    attribution = ReferralAttribution(
        source_id=source.id,
        user_id=user_id,
        visitor_id=visitor_id,
    )
    db.add(attribution)
    await db.flush()
    return True


async def get_source_stats(db: AsyncSession, source: ReferralSource) -> SourceStats:
    visits_count = (
        await db.scalar(
            select(func.count()).where(ReferralVisit.source_id == source.id)
        )
        or 0
    )

    unique_visitors = (
        await db.scalar(
            select(func.count(func.distinct(ReferralVisit.visitor_id))).where(
                ReferralVisit.source_id == source.id
            )
        )
        or 0
    )

    registrations = (
        await db.scalar(
            select(func.count()).where(ReferralAttribution.source_id == source.id)
        )
        or 0
    )

    purchases = (
        await db.scalar(
            select(func.count()).where(
                ReferralAttribution.source_id == source.id,
                ReferralAttribution.purchased_at.is_not(None),
            )
        )
        or 0
    )

    return SourceStats(
        source_id=source.id,
        code=source.code,
        label=source.label,
        visits_count=visits_count,
        unique_visitors=unique_visitors,
        registrations=registrations,
        purchases=purchases,
    )


async def get_dashboard(db: AsyncSession, user_id: uuid.UUID) -> list[SourceStats]:
    sources = await list_sources(db, user_id)
    stats = []
    for source in sources:
        stats.append(await get_source_stats(db, source))
    return stats


async def list_all_sources_with_stats(db: AsyncSession) -> list[AdminSourceRow]:
    visits_sub = (
        select(
            ReferralVisit.source_id.label("sid"),
            func.count().label("visits_count"),
            func.count(distinct(ReferralVisit.visitor_id)).label("unique_visitors"),
        )
        .group_by(ReferralVisit.source_id)
        .subquery()
    )
    attr_sub = (
        select(
            ReferralAttribution.source_id.label("sid"),
            func.count().label("registrations"),
            func.sum(
                case((ReferralAttribution.purchased_at.is_not(None), 1), else_=0)
            ).label("purchases"),
        )
        .group_by(ReferralAttribution.source_id)
        .subquery()
    )
    stmt = (
        select(
            ReferralSource.id.label("source_id"),
            ReferralSource.code.label("code"),
            ReferralSource.label.label("label"),
            ReferralSource.is_active.label("is_active"),
            ReferralSource.user_id.label("owner_user_id"),
            ReferralSource.created_at.label("created_at"),
            User.email.label("owner_email"),
            func.coalesce(visits_sub.c.visits_count, 0).label("visits_count"),
            func.coalesce(visits_sub.c.unique_visitors, 0).label("unique_visitors"),
            func.coalesce(attr_sub.c.registrations, 0).label("registrations"),
            func.coalesce(attr_sub.c.purchases, 0).label("purchases"),
        )
        .join(User, User.id == ReferralSource.user_id)
        .outerjoin(visits_sub, visits_sub.c.sid == ReferralSource.id)
        .outerjoin(attr_sub, attr_sub.c.sid == ReferralSource.id)
        .order_by(ReferralSource.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        AdminSourceRow(
            source_id=r.source_id,
            code=r.code,
            label=r.label,
            is_active=r.is_active,
            owner_user_id=r.owner_user_id,
            owner_email=r.owner_email,
            created_at=r.created_at,
            visits_count=int(r.visits_count),
            unique_visitors=int(r.unique_visitors),
            registrations=int(r.registrations),
            purchases=int(r.purchases),
        )
        for r in result.all()
    ]


async def get_source_detail(
    db: AsyncSession, source_id: uuid.UUID
) -> AdminSourceDetail | None:
    rows = await list_all_sources_with_stats(db)
    source_row = next((r for r in rows if r.source_id == source_id), None)
    if source_row is None:
        return None

    visits_result = await db.execute(
        select(
            ReferralVisit.visited_at.label("visited_at"),
            ReferralVisit.landing_page.label("landing_page"),
            ReferralVisit.visitor_id.label("visitor_id"),
            User.email.label("visitor_email"),
        )
        .outerjoin(
            ReferralAttribution,
            (ReferralAttribution.visitor_id == ReferralVisit.visitor_id)
            & (ReferralAttribution.source_id == ReferralVisit.source_id),
        )
        .outerjoin(User, User.id == ReferralAttribution.user_id)
        .where(ReferralVisit.source_id == source_id)
        .order_by(ReferralVisit.visited_at.desc())
        .limit(50)
    )
    recent_visits = [
        AdminVisitRow(
            visited_at=v.visited_at,
            landing_page=v.landing_page,
            visitor_id=v.visitor_id,
            visitor_email=v.visitor_email,
        )
        for v in visits_result.all()
    ]

    attr_result = await db.execute(
        select(
            User.id.label("user_id"),
            User.email.label("email"),
            ReferralAttribution.registered_at.label("registered_at"),
            ReferralAttribution.purchased_at.label("purchased_at"),
        )
        .join(User, User.id == ReferralAttribution.user_id)
        .where(ReferralAttribution.source_id == source_id)
        .order_by(ReferralAttribution.registered_at.desc())
    )
    attributions = [
        AdminAttributionRow(
            user_id=a.user_id, email=a.email, registered_at=a.registered_at, purchased_at=a.purchased_at
        )
        for a in attr_result.all()
    ]

    return AdminSourceDetail(
        source=source_row,
        attributions=attributions,
        recent_visits=recent_visits,
    )
