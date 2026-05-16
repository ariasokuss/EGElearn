"""Lesson API models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.sqltypes import Boolean, Integer

from src.core.db import Base

LEARNING_JSON_TYPE = JSONB().with_variant(JSON(), "sqlite")
LEARNING_INT_ARRAY_TYPE = ARRAY(Integer).with_variant(JSON(), "sqlite")


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    num_blocks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lesson_blocks: Mapped[list[LessonBlock]] = relationship(
        "LessonBlock", back_populates="lesson", cascade="all, delete-orphan"
    )
    feynman_blocks: Mapped[list[FeynmanBlock]] = relationship(
        "FeynmanBlock", back_populates="lesson", cascade="all, delete-orphan"
    )
    progress_entries: Mapped[list[LessonProgress]] = relationship(
        "LessonProgress", back_populates="lesson", cascade="all, delete-orphan"
    )
    access_entries: Mapped[list[LessonAccessEvent]] = relationship(
        "LessonAccessEvent", back_populates="lesson", cascade="all, delete-orphan"
    )


class LessonBlock(Base):
    __tablename__ = "lesson_blocks"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_summary: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100%
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lesson: Mapped[Lesson] = relationship("Lesson", back_populates="lesson_blocks")


class FeynmanBlock(Base):
    """A parsed feynman exercise block extracted from a lesson's markdown content."""

    __tablename__ = "feynman_blocks"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Block numbers from the lesson that are in scope for this exercise
    scope: Mapped[list[int]] = mapped_column(LEARNING_INT_ARRAY_TYPE, nullable=False)
    # The pre-authored question text verbatim from the markdown
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Bullet-point concepts the student must cover, stored as a JSON list of strings
    points: Mapped[list[str]] = mapped_column(LEARNING_JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lesson: Mapped[Lesson] = relationship("Lesson", back_populates="feynman_blocks")
    sessions: Mapped[list[FeynmanSession]] = relationship(
        "FeynmanSession", back_populates="feynman_block", cascade="all, delete-orphan"
    )


class FeynmanSession(Base):
    """One student's attempt at a feynman exercise (up to 3 iterations)."""

    __tablename__ = "feynman_sessions"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feynman_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feynman_blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # active | completed | aborted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # mini | standard
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="mini")
    current_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # mini: list[bool] per point; standard: list[int] (0-5) per theme
    covered_points: Mapped[list | None] = mapped_column(LEARNING_JSON_TYPE, nullable=True)
    # LLM-generated per-theme feedback, populated when session is completed or aborted.
    # Format: list[{"theme": str, "feedback": str}]
    feedback: Mapped[list | None] = mapped_column(LEARNING_JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    feynman_block: Mapped[FeynmanBlock] = relationship(
        "FeynmanBlock", back_populates="sessions"
    )
    messages: Mapped[list[FeynmanMessage]] = relationship(
        "FeynmanMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="FeynmanMessage.created_at",
    )


class FeynmanMessage(Base):
    """A single message in a feynman session conversation."""

    __tablename__ = "feynman_messages"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feynman_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # user | assistant
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(LEARNING_JSON_TYPE, nullable=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[FeynmanSession] = relationship(
        "FeynmanSession", back_populates="messages"
    )


class LessonProgress(Base):
    """Per-user progress on a lesson (0-3 stars)."""

    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("lesson_id", "user_id", name="uq_lesson_progress_lesson_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    study_star: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feynman_star: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    test_star: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    star_reward_shown: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    mastery: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100%
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    lesson: Mapped[Lesson] = relationship("Lesson", back_populates="progress_entries")


class LessonAccessEvent(Base):
    __tablename__ = "lesson_access_events"
    __table_args__ = (
        Index(
            "uq_lesson_access_user_lesson_no_folder",
            "user_id",
            "lesson_id",
            unique=True,
            postgresql_where=text("folder_id IS NULL"),
        ),
        Index(
            "uq_lesson_access_user_lesson_folder",
            "user_id",
            "lesson_id",
            "folder_id",
            unique=True,
            postgresql_where=text("folder_id IS NOT NULL"),
        ),
        Index(
            "ix_lesson_access_user_last_accessed_at",
            "user_id",
            "last_accessed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    lesson: Mapped[Lesson] = relationship("Lesson", back_populates="access_entries")
