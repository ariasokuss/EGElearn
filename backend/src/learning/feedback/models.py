"""Feedback Hub — persistent mistake tracking from tests and Feynman sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.files import models as _files_models  # noqa: F401
from src.processing import models as _processing_models  # noqa: F401

FEEDBACK_REVIEW_QUESTION_TYPE = JSONB().with_variant(JSON(), "sqlite")

class FeedbackNote(Base):
    __tablename__ = "feedback_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Polymorphic source: "test" | "feynman"
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    # For tests: links to session_answers.id; NULL for Feynman
    source_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    mistake: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)

    # Review lifecycle: "see" → "review" → "complete"
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="see")
    # Feynman notes only: LLM-generated review question stored inline
    review_question: Mapped[dict | None] = mapped_column(
        FEEDBACK_REVIEW_QUESTION_TYPE,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_feedback_notes_user_source_type", "user_id", "source_type"),
        Index("ix_feedback_notes_user_session", "user_id", "source_session_id"),
    )
