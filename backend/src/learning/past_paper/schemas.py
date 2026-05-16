from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PastPaperQuestionOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    question: str
    model_answer: str | None
    mark_scheme: str | None
    context: str | None
    type: str
    options: list[str] | None
    correct_option_index: int | None
    hint: str | None
    points: int
    index: int
    question_number: str | None
    is_unsupported: bool
    node_ids: list[uuid.UUID] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PastPaperOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    folder_id: uuid.UUID
    name: str
    original_filename: str | None
    mark_scheme_filename: str | None = None
    status: str
    processing_phase: str | None = None
    created_at: datetime
    questions: list[PastPaperQuestionOut] = []

    model_config = {"from_attributes": True}


class PastPaperListOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    folder_id: uuid.UUID
    name: str
    original_filename: str | None
    mark_scheme_filename: str | None = None
    status: str
    processing_phase: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParsedQuestion(BaseModel):
    """Internal schema for LLM-parsed questions. Not exposed over the API."""

    question: str
    model_answer: str
    mark_scheme: str | None = None
    sources: list[str] = []
    context: str | None = None
    type: Literal["mcq", "short"]
    options: list[str] | None = None
    correct_option_index: int | None = None
    hint: str | None = None
    points: int = 1
    question_number: str | None = None
    requires_diagram: bool = False
    is_unsupported: bool = False


class PastPaperStatusOut(BaseModel):
    id: uuid.UUID
    status: str           # processing | ready | failed
    processing_phase: str | None  # ocr | parsing | matching | None

    model_config = {"from_attributes": True}


class MarkSchemeJobOut(BaseModel):
    id: uuid.UUID
    past_paper_id: uuid.UUID
    status: Literal["queued", "processing", "completed", "failed"]
    phase: str | None = None
    message: str | None = None
    matched_questions: int | None = None
    total_short_questions: int | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
