"""Mastery engine data models — Beta-Bayesian evidence ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class EvidenceEvent(Base):
    """A single scored performance event in the mastery evidence ledger.

    Each event contributes to the Beta(α, β) posterior for a roadmap node.
    Mastery = BetaPPF(0.10, α, β) × 100%.
    """

    __tablename__ = "evidence_events"
    __table_args__ = (
        Index("ix_evidence_user_node", "user_id", "node_id"),
        Index("ix_evidence_user_item", "user_id", "item_id"),
        Index("ix_evidence_attempt", "attempt_id"),
        Index("ix_evidence_source", "user_id", "node_id", "source_type", "invalidated"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Event identity ──
    item_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Stable hash per question/feynman point for repeat detection",
    )
    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="inline_mcq | inline_short | mini_feynman | feynman | "
        "lesson_test | standalone_test | past_paper | verify_card",
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="lesson_id, test_template_id, or feedback_note_id",
    )

    # ── Session grouping (for batch invalidation on retake) ──
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="TestSession.id or FeynmanSession.id — groups events per attempt",
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # ── Scoring ──
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="s ∈ [0, 1]: 1.0=fully correct, 0.0=fully wrong",
    )
    quality_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="q: evidence strength from source type (0.5–1.5)",
    )
    repeat_discount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment="d: 1.0 for first attempt, <1.0 for repeats",
    )

    # ── Lifecycle ──
    invalidated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True when superseded by a newer attempt of the same source",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
