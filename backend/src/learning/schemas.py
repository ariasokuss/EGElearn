"""Lesson API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class LessonSchema(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    name: Optional[str]
    description: Optional[str]
    content: str
    num_blocks: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class LessonListSchema(BaseModel):
    """Lightweight lesson schema for list responses — omits content."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    name: Optional[str]
    description: Optional[str]
    num_blocks: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class LessonBlockSchema(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    user_id: uuid.UUID | None
    content: str
    block_number: int
    block_id: Optional[str] = None
    title: Optional[str] = None
    is_summary: Optional[bool]
    progress: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class FeynmanBlockRead(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    user_id: uuid.UUID | None
    scope: list[int]
    question: str
    points: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ThemeFeedbackItem(BaseModel):
    theme: str
    feedback: str


class LessonUploadResponse(BaseModel):
    lesson: LessonSchema
    blocks: list[LessonBlockSchema]
    num_blocks: int


class LessonProgressRead(BaseModel):
    lesson_id: uuid.UUID
    stars: int
    study_star: bool = False
    feynman_star: bool = False
    test_star: bool = False
    star_reward_shown: bool = False
    mastery: float | None = None
    progress: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoadmapContextRead(BaseModel):
    node_id: uuid.UUID
    section_name: str
    subsection_name: str | None = None

    model_config = {"from_attributes": True}


class LessonDetailRead(BaseModel):
    lesson: LessonSchema
    blocks: list[LessonBlockSchema]
    feynman_blocks: list[FeynmanBlockRead]
    progress: LessonProgressRead | None = None
    roadmap_context: RoadmapContextRead | None = None


class ParseFeynmanResponse(BaseModel):
    count: int
    blocks: list[FeynmanBlockRead]


class FeynmanSessionRead(BaseModel):
    id: uuid.UUID
    feynman_block_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    type: str
    current_iteration: int
    covered_points: list[int | None] | list[bool] | None = None
    feedback: list[ThemeFeedbackItem] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeynmanMessageRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    citations: list[str] = Field(default_factory=list)
    iteration: int
    created_at: datetime

    @field_validator("citations", mode="before")
    @classmethod
    def _citations_none_to_empty(cls, v: object) -> object:
        return [] if v is None else v

    model_config = {"from_attributes": True}


class StartSessionResponse(BaseModel):
    session: FeynmanSessionRead
    first_message: FeynmanMessageRead
    feynman_block: FeynmanBlockRead


class SessionDetailRead(BaseModel):
    session: FeynmanSessionRead
    feynman_block: FeynmanBlockRead
    messages: list[FeynmanMessageRead]


class CompleteStepRequest(BaseModel):
    step: int = Field(ge=1, le=3)


class CompleteStepResponse(BaseModel):
    stars: int
    study_star: bool = False
    feynman_star: bool = False
    test_star: bool = False
    roadmap_progress: int | None = None
    mastery: float | None = None
    confidence: float | None = None


# ---------------------------------------------------------------------------
# Feynman history & feedback
# ---------------------------------------------------------------------------


class SessionHistoryItem(BaseModel):
    """One session row returned in a lesson's history list."""

    session: FeynmanSessionRead
    feynman_block: FeynmanBlockRead


class SessionFeedbackRead(BaseModel):
    """Full result of a completed (or aborted) feynman session.

    Standard feynman: only session + feynman_block are populated.
    Mini-feynman: also includes summary, covered_points, points, all_covered.
    """

    session: FeynmanSessionRead
    feynman_block: FeynmanBlockRead
    summary: str | None = None
    covered_points: list[bool] | None = None
    points: list[str] | None = None
    all_covered: bool | None = None


# ---------------------------------------------------------------------------
# Lesson results
# ---------------------------------------------------------------------------


class LessonResultBreakdown(BaseModel):
    lesson_block_id: uuid.UUID | None = None
    title: str
    percent: float
    description: str


class LessonResultRead(BaseModel):
    earned_marks: int
    total_marks: int
    percent: float
    stars: int
    breakdown: list[LessonResultBreakdown]
    need_review: list[str]
