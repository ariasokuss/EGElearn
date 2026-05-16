from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.learning.models import Lesson  # noqa: F401


class RoadmapNode(Base):
    """A node in the roadmap tree: section (level 1), subsection (level 2), or lesson (level 3)."""

    __tablename__ = "roadmap_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lesson: Mapped["Lesson | None"] = relationship(
        "Lesson",
        foreign_keys=[lesson_id],
        uselist=False,
    )

    children: Mapped[list[RoadmapNode]] = relationship(
        "RoadmapNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="RoadmapNode.position",
    )
    parent: Mapped[RoadmapNode | None] = relationship(
        "RoadmapNode",
        back_populates="children",
        remote_side=[id],
    )
    progress_entries: Mapped[list[RoadmapProgress]] = relationship(
        "RoadmapProgress",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class RoadmapProgress(Base):
    """Per-user progress on a level-3 (lesson) roadmap node."""

    __tablename__ = "roadmap_progress"
    __table_args__ = (
        UniqueConstraint("node_id", "user_id", name="uq_roadmap_progress_node_user"),
        Index("ix_roadmap_progress_user_node", "user_id", "node_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    mastery: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    node: Mapped[RoadmapNode] = relationship(
        "RoadmapNode", back_populates="progress_entries"
    )


class UserFolderPosition(Base):
    """Per-user folder ordering (works for both personal and shared folders)."""

    __tablename__ = "user_folder_positions"
    __table_args__ = (
        UniqueConstraint("user_id", "folder_id", name="uq_user_folder_position"),
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
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
