"""Unified test template, question, session and answer models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text
from sqlalchemy.sql.sqltypes import Boolean, Integer

from src.core.db import Base

TESTS_JSON_TYPE = JSONB(none_as_null=True).with_variant(JSON(), "sqlite")
TESTS_UUID_ARRAY_TYPE = ARRAY(UUID(as_uuid=True)).with_variant(JSON(), "sqlite")


class TestTemplate(Base):
    """A reusable test definition — shared (user_id=NULL) or per-user.

    Type values:
      - lesson_test:        pre-authored, seeded from JSON, tied to a lesson
      - past_paper:         uploaded PDF processed via OCR + LLM
      - practice_questions: LLM-generated from roadmap nodes
    """

    __tablename__ = "test_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # lesson_test | past_paper | practice_questions | inline_quiz
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ready"
    )  # processing | ready | failed
    processing_phase: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # past_paper upload phases: ocr | parsing | matching | None when done
    node_ids: Mapped[list | None] = mapped_column(
        TESTS_UUID_ARRAY_TYPE, nullable=True
    )  # level-3 roadmap nodes only
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mark_scheme: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # past papers only
    mark_scheme_filename: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # past papers only
    ocr_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # past papers only — stored to allow later mark scheme matching
    source_pdf_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )  # past papers only — used to reuse previous OCR/indexing results
    mark_scheme_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )  # past papers only — mark scheme fingerprint for cache matching
    is_canonical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=False,
    )  # past papers only — when true, user uploads with same source_pdf_sha256 are cloned from this template
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    generation_progress: Mapped[dict | None] = mapped_column(
        TESTS_JSON_TYPE, nullable=True
    )  # {"nodes": {"Topic": {"generated": N, "total": M}}, "error": null}
    generation_task_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # asyncio task name for cancellation
    question_type_counts: Mapped[dict | None] = mapped_column(
        TESTS_JSON_TYPE, nullable=True
    )  # preserved from request for retry: {"section_a": 2, "five_mark": 3}

    __table_args__ = (
        Index(
            "ix_test_templates_canonical_sha",
            "source_pdf_sha256",
            postgresql_where=text("is_canonical = true"),
        ),
    )

    questions: Mapped[list[TestQuestion]] = relationship(
        "TestQuestion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TestQuestion.index",
    )
    sessions: Mapped[list[TestSession]] = relationship(
        "TestSession",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class TestQuestion(Base):
    """A single question within a test template."""

    __tablename__ = "test_questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based ordering
    question_number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # original label from paper, e.g. "3(b)", "1a"
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # mcq | short
    is_unsupported: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(
        TESTS_JSON_TYPE, nullable=True
    )
    correct_option_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark_scheme: Mapped[str | None] = mapped_column(Text, nullable=True)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list | None] = mapped_column(
        TESTS_JSON_TYPE, nullable=True
    )
    node_ids: Mapped[list | None] = mapped_column(
        TESTS_UUID_ARRAY_TYPE, nullable=True
    )  # roadmap level-3 nodes this question tests
    item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    inline_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )  # "block_id:question_index" for inline_quiz questions
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    template: Mapped[TestTemplate] = relationship(
        "TestTemplate", back_populates="questions"
    )
    answers: Mapped[list[SessionAnswer]] = relationship(
        "SessionAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
    )
    ai_hint_usages: Mapped[list["SessionAiHintUsage"]] = relationship(
        "SessionAiHintUsage",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class TestSession(Base):
    """One user's attempt at a test template (like FeynmanSession)."""

    __tablename__ = "test_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="practice"
    )  # practice | exam
    # not_started | active | completed | grading | graded | aborted
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_started"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    earned_marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    template: Mapped[TestTemplate] = relationship(
        "TestTemplate", back_populates="sessions"
    )
    answers: Mapped[list[SessionAnswer]] = relationship(
        "SessionAnswer",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionAnswer.answered_at",
    )
    ai_hint_usages: Mapped[list["SessionAiHintUsage"]] = relationship(
        "SessionAiHintUsage",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SessionAiHintUsage(Base):
    """Records that the student consumed the LLM practice hint for one question (one per session+question)."""

    __tablename__ = "session_ai_hint_usages"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "question_id",
            name="uq_session_ai_hint_session_question",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["TestSession"] = relationship(
        "TestSession", back_populates="ai_hint_usages"
    )
    question: Mapped["TestQuestion"] = relationship("TestQuestion")


class SessionAnswer(Base):
    """A user's answer to a question within a session."""

    __tablename__ = "session_answers"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "question_id", name="uq_session_answer_session_question"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    earned_marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_keys: Mapped[list[str]] = mapped_column(
        TESTS_JSON_TYPE, nullable=False, server_default="[]", default=list
    )
    is_skipped: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    session: Mapped[TestSession] = relationship("TestSession", back_populates="answers")
    question: Mapped[TestQuestion] = relationship(
        "TestQuestion", back_populates="answers"
    )
