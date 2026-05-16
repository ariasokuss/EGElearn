from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base


class ReferralSource(Base):
    """A creator's referral link (e.g. ?ref=roman-yt)."""

    __tablename__ = "referral_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    visits: Mapped[list[ReferralVisit]] = relationship(
        "ReferralVisit", back_populates="source", cascade="all, delete-orphan"
    )
    attributions: Mapped[list[ReferralAttribution]] = relationship(
        "ReferralAttribution", back_populates="source", cascade="all, delete-orphan"
    )


class ReferralVisit(Base):
    """An anonymous page view from a referral link."""

    __tablename__ = "referral_visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referral_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visitor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    landing_page: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    source: Mapped[ReferralSource] = relationship(
        "ReferralSource", back_populates="visits"
    )


class ReferralAttribution(Base):
    """Links a registered user to the referral source that brought them."""

    __tablename__ = "referral_attributions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_referral_attributions_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referral_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    visitor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    purchased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    source: Mapped[ReferralSource] = relationship(
        "ReferralSource", back_populates="attributions"
    )
