from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base

ACTIVITY_JSON_TYPE = JSONB(none_as_null=True).with_variant(JSON(), "sqlite")


class UserActivityEvent(Base):
    __tablename__ = "user_activity_events"
    __table_args__ = (
        Index("ix_user_activity_user_created", "user_id", "created_at"),
        Index("ix_user_activity_user_type_created", "user_id", "event_type", "created_at"),
        Index("ix_user_activity_test_session", "test_session_id"),
        Index("ix_user_activity_lesson", "lesson_id"),
        Index("ix_user_activity_folder", "folder_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_group: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    http_method: Mapped[str | None] = mapped_column(String(12), nullable=True)
    route_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    test_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", ACTIVITY_JSON_TYPE, nullable=False, default=dict
    )
    replay_payload: Mapped[dict] = mapped_column(
        ACTIVITY_JSON_TYPE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
