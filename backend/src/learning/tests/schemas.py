"""Unified test template, session and question schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ── Requests ────────────────────────────────────────────────────────────────


class GenerateTemplateRequest(BaseModel):
    folder_id: uuid.UUID
    node_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Roadmap nodes (expanded to level-3 automatically)",
    )
    total_questions: int = Field(
        default=10, ge=0, le=100, description="Total questions to generate (derived from question_type_counts if provided)"
    )
    name: str | None = Field(
        default=None,
        max_length=500,
        description="Optional name (auto-generated if omitted)",
    )
    question_type_counts: dict[str, int] | None = Field(
        default=None,
        description=(
            "Per-type counts for Edexcel A-Level Economics A questions. "
            "Keys: section_a, five_mark, eight_mark, ten_mark, twelve_mark, "
            "fifteen_mark, twenty_five_mark. When provided, overrides total_questions."
        ),
    )


class StartSessionRequest(BaseModel):
    template_id: uuid.UUID
    mode: str = Field(default="practice", pattern="^(exam|practice)$")


class SaveAnswerRequest(BaseModel):
    answer: str = Field(..., description="Option index for MCQ, free text for short")
    image_keys: list[str] | None = Field(
        default=None,
        description="Uploaded answer image S3 keys to save with this answer",
    )


class SubmitAnswerItem(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(..., description="Option index for MCQ, free text for short")
    image_keys: list[str] | None = Field(
        default=None,
        description="Uploaded answer image S3 keys to save with this answer",
    )


class SubmitSessionRequest(BaseModel):
    answers: list[SubmitAnswerItem] = Field(
        default_factory=list,
        description="Remaining answers to save before submission (optional if all already auto-saved)",
    )


class PracticeHintRequest(BaseModel):
    """Practice hint stream options + optional sync to a practice-scoped chat thread."""

    model: str | None = Field(
        default=None,
        description="Model alias from /chat/available-models (optional)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Reasoning level key from config (optional)",
    )
    folder_id: str | None = Field(
        default=None,
        description=(
            "Folder UUID string (must match the test template folder). "
            "With conversation_id omitted: creates a new conversation for this session/question. "
            "Omit both folder_id and conversation_id to skip chat persistence."
        ),
    )
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Existing practice-scoped chat thread. When set, user+assistant messages are appended here "
            "after a successful hint. folder_id may be omitted (taken from the conversation)."
        ),
    )

    @field_validator("folder_id", "conversation_id", mode="before")
    @classmethod
    def blank_string_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("folder_id", mode="after")
    @classmethod
    def validate_folder_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as e:
            raise ValueError("folder_id must be a valid UUID") from e
        return v

    @field_validator("conversation_id", mode="after")
    @classmethod
    def validate_conversation_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid.UUID(v)
        except ValueError as e:
            raise ValueError("conversation_id must be a valid UUID") from e
        return v


# ── Responses ───────────────────────────────────────────────────────────────


class TestTemplateOut(BaseModel):
    """Template list-view."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    folder_id: uuid.UUID
    lesson_id: uuid.UUID | None = None
    name: str
    type: str
    status: str
    node_ids: list[uuid.UUID] | None = None
    total_questions: int
    total_marks: int | None
    mark_scheme: str | None = None
    original_filename: str | None = None
    created_at: datetime
    generation_progress: dict | None = None
    question_type_counts: dict | None = None

    model_config = {"from_attributes": True}


class GenerateStartedOut(BaseModel):
    """Response when generation is kicked off as background task."""

    template_id: uuid.UUID
    name: str
    status: str = "processing"


class TestQuestionOut(BaseModel):
    """Question for test-taking (no answer revealed)."""

    id: uuid.UUID
    index: int
    type: str
    question: str
    options: list[str] | None
    hint: str | None
    points: int
    context: str | None = None
    node_ids: list[uuid.UUID] | None = None
    is_unsupported: bool = False
    question_number: str | None = None
    mark_scheme: str | None = None
    ai_hint_used_at: datetime | None = Field(
        default=None,
        description="When the LLM practice hint was consumed for this question in the current session.",
    )

    model_config = {"from_attributes": True}


class QuestionWithAnswerOut(BaseModel):
    """Question + grading details (after submission)."""

    id: uuid.UUID
    index: int
    type: str
    question: str
    options: list[str] | None
    hint: str | None
    points: int
    context: str | None = None
    node_ids: list[uuid.UUID] | None = None
    question_number: str | None = None
    is_unsupported: bool = False
    model_answer: str | None = None
    mark_scheme: str | None = None
    correct_option_index: int | None = None
    # User's answer & grading
    user_answer: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    earned_marks: int | None = None
    feedback: str | None = None
    recommendations: str | None = None
    ai_hint_used_at: datetime | None = Field(
        default=None,
        description="When the LLM practice hint was consumed for this question in the session.",
    )

    model_config = {"from_attributes": True}


class TemplateDetailOut(BaseModel):
    """Template + questions."""

    template: TestTemplateOut
    questions: list[TestQuestionOut] | list[QuestionWithAnswerOut]


class SessionAnswerOut(BaseModel):
    """A saved answer within a session."""

    question_id: uuid.UUID
    answer: str
    is_correct: bool | None = None
    score: float | None = None
    earned_marks: int | None = None
    feedback: str | None = None
    recommendations: str | None = None
    answered_at: datetime
    graded_at: datetime | None = None
    image_key: str | None = None
    image_keys: list[str] = Field(default_factory=list)
    is_skipped: bool = False

    model_config = {"from_attributes": True}


class SkipQuestionRequest(BaseModel):
    """Request body for marking a question as skipped or unskipped."""

    skipped: bool


class DiagramUploadUrlOut(BaseModel):
    """Presigned S3 PUT URL and key for uploading a diagram answer image."""

    upload_url: str
    image_key: str


class DiagramAnswerRequest(BaseModel):
    """Request body for submitting a diagram answer."""

    image_key: str


class TestSessionOut(BaseModel):
    """Session list-view."""

    id: uuid.UUID
    template_id: uuid.UUID
    template_name: str | None = None
    session_mode: str
    status: str
    earned_marks: int | None
    total_marks: int
    score: float | None
    started_at: datetime | None
    submitted_at: datetime | None = None
    graded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionDetailOut(BaseModel):
    """Full session view with questions and answers."""

    session: TestSessionOut
    template: TestTemplateOut
    questions: list[QuestionWithAnswerOut]
    answers: list[SessionAnswerOut]
    graded_question_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Questions with a graded check (graded_at set); same as persisted session_answers.",
    )
    hint_used_question_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Questions for which the LLM practice hint was successfully consumed in this session.",
    )


class CheckAnswerOut(BaseModel):
    """Result of checking a single answer (mirrors persisted SessionAnswer + template fields)."""

    question_id: uuid.UUID
    type: str
    answer: str
    answered_at: datetime
    graded_at: datetime | None = None
    is_correct: bool | None
    earned_marks: int | None
    total_marks: int
    score: float | None
    model_answer: str | None
    correct_option_index: int | None = None
    feedback: str | None = None
    recommendations: str | None = None


class QuestionResultOut(BaseModel):
    """Per-question result for the results view."""

    question: str
    relation: str
    points: int | None = None
    max_points: int
    is_skipped: bool = False
    question_number: str | None = None


class SessionResultsOut(BaseModel):
    """Dedicated results endpoint — overall progress + per-question breakdown."""

    marks: int | None = None
    total_marks: int
    mode: str
    questions: list[QuestionResultOut]


class TestStatusOut(BaseModel):
    status: str
    earned_marks: int | None = None
    total_marks: int | None = None
    score: float | None = None


class FeedbackItemOut(BaseModel):
    type: str
    answer: str | None = None
    correct_option_index: int | None = None
    model_answer: str | None = None
    feedback: str | None = None
    recommendation: str | None = None
    points: int | None = None
    total_points: int
    image_url: str | None = None
    image_urls: list[str] = []
    question_number: str | None = None


class SessionFeedbackOut(BaseModel):
    session_id: uuid.UUID
    items: list[FeedbackItemOut]


# ── Inline quiz (lesson mini-questions) ────────────────────────────────────


class InlineQuestionMapEntry(BaseModel):
    question_id: uuid.UUID
    type: str  # mcq | short


class InlineAnswerEntry(BaseModel):
    answer: str
    is_correct: bool | None = None
    earned_marks: int | None = None
    total_marks: int
    feedback: str | None = None
    recommendations: str | None = None
    graded_at: datetime | None = None


class QuestionTypeOut(BaseModel):
    label: str
    key: str
    points: int


class InlineSessionOut(BaseModel):
    """Bootstrap response for inline quiz session."""

    session_id: uuid.UUID
    question_map: dict[str, InlineQuestionMapEntry]  # inline_key → {question_id, type}
    answers: dict[str, InlineAnswerEntry]  # inline_key → saved answer data
