"""Pydantic schemas for the Feedback Hub API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackNoteOut(BaseModel):
    id: uuid.UUID
    source_type: str
    source_session_id: uuid.UUID
    source_answer_id: uuid.UUID | None
    question_id: uuid.UUID | None = None
    severity: str
    topic: str
    mistake: str
    correction: str
    status: str
    review_question: dict | None
    created_at: datetime
    folder_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class FeedbackSummaryOut(BaseModel):
    see: int = 0
    review: int = 0
    complete: int = 0
    total: int = 0


class NoteStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(see|review|complete)$")


class NoteAnswerRequest(BaseModel):
    answer: str


class NoteAnswerOut(BaseModel):
    is_correct: bool
    earned_marks: int
    total_marks: int
    feedback: str
    recommendations: str
