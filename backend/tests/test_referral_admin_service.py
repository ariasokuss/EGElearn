from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.auth.models import User
from src.referral.models import ReferralAttribution, ReferralSource, ReferralVisit
from src.referral import service as ref_svc


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, hashed_password="x", is_active=True)
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_list_all_sources_with_stats_aggregates_across_users(db):
    u1 = await _make_user(db, "creator1@example.com")
    u2 = await _make_user(db, "creator2@example.com")
    s1 = ReferralSource(user_id=u1.id, code="alpha", label="Alpha", is_active=True)
    s2 = ReferralSource(user_id=u2.id, code="beta", label=None, is_active=False)
    db.add_all([s1, s2])
    await db.flush()

    db.add_all([
        ReferralVisit(source_id=s1.id, visitor_id="v1"),
        ReferralVisit(source_id=s1.id, visitor_id="v1"),  # duplicate visitor
        ReferralVisit(source_id=s1.id, visitor_id="v2"),
        ReferralVisit(source_id=s2.id, visitor_id="v3"),
    ])
    reg_user = await _make_user(db, "buyer@example.com")
    db.add(ReferralAttribution(
        source_id=s1.id,
        user_id=reg_user.id,
        purchased_at=datetime.now(timezone.utc),
    ))
    await db.flush()

    rows = await ref_svc.list_all_sources_with_stats(db)
    by_code = {r.code: r for r in rows}

    assert by_code["alpha"].owner_email == "creator1@example.com"
    assert by_code["alpha"].visits_count == 3
    assert by_code["alpha"].unique_visitors == 2
    assert by_code["alpha"].registrations == 1
    assert by_code["alpha"].purchases == 1

    assert by_code["beta"].is_active is False
    assert by_code["beta"].visits_count == 1
    assert by_code["beta"].unique_visitors == 1
    assert by_code["beta"].registrations == 0
    assert by_code["beta"].purchases == 0


@pytest.mark.asyncio
async def test_get_source_detail_returns_users_and_visits(db):
    creator = await _make_user(db, "c@example.com")
    src = ReferralSource(user_id=creator.id, code="gamma", label="G")
    db.add(src)
    await db.flush()

    buyer = await _make_user(db, "buyer@example.com")
    db.add_all([
        ReferralVisit(source_id=src.id, visitor_id="v1", landing_page="/"),
        ReferralVisit(source_id=src.id, visitor_id="v2", landing_page="/pricing"),
        ReferralAttribution(source_id=src.id, user_id=buyer.id),
    ])
    await db.flush()

    detail = await ref_svc.get_source_detail(db, src.id)
    assert detail is not None
    assert detail.source.code == "gamma"
    assert detail.source.owner_email == "c@example.com"
    assert detail.source.visits_count == 2
    assert detail.source.registrations == 1
    assert len(detail.recent_visits) == 2
    assert {v.landing_page for v in detail.recent_visits} == {"/", "/pricing"}
    assert len(detail.attributions) == 1
    assert detail.attributions[0].email == "buyer@example.com"


@pytest.mark.asyncio
async def test_get_source_detail_returns_none_for_unknown(db):
    assert await ref_svc.get_source_detail(db, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_get_source_detail_enriches_visit_with_email(db):
    creator = await _make_user(db, "c@example.com")
    src = ReferralSource(user_id=creator.id, code="delta")
    db.add(src)
    await db.flush()

    buyer = await _make_user(db, "buyer@example.com")
    db.add_all([
        ReferralVisit(source_id=src.id, visitor_id="known-visitor"),
        ReferralVisit(source_id=src.id, visitor_id="anon-visitor"),
        ReferralAttribution(
            source_id=src.id,
            user_id=buyer.id,
            visitor_id="known-visitor",
        ),
    ])
    await db.flush()

    detail = await ref_svc.get_source_detail(db, src.id)
    assert detail is not None
    by_visitor = {v.visitor_id: v for v in detail.recent_visits}
    assert by_visitor["known-visitor"].visitor_email == "buyer@example.com"
    assert by_visitor["anon-visitor"].visitor_email is None
