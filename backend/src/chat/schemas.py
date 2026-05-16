"""Chat API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.config import get_settings

_ALLOWED_ATTACHMENT_MIMES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "image/heic",
    "image/heif",
    "image/png",
    "image/jpeg",
}


class FileAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str  # base64-encoded content (no data-URI prefix)
    mime_type: str

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _ALLOWED_ATTACHMENT_MIMES:
            raise ValueError(
                f"Unsupported mime_type '{v}'. Allowed: {sorted(_ALLOWED_ATTACHMENT_MIMES)}"
            )
        return v


class InlineQuizAnswerContext(BaseModel):
    """A single inline quiz answer, pushed by the frontend for chat context."""

    block_id: str
    question_index: int
    question_type: str  # "mcq" | "open"
    total_marks: int
    answer: str
    earned_marks: int | None = None
    is_correct: bool | None = None
    feedback: str | None = None
    recommendations: str | None = None
    grading: bool = False


class ChatMessageRequest(BaseModel):
    conversation_id: str | None = None
    folder_id: str | None = None
    test_session_id: str | None = None
    question_id: str | None = None
    lesson_id: str | None = None
    current_block_id: str | None = None
    scope_type: str | None = None  # "practice" | "review" | "feedback_review"
    feedback_note_id: str | None = None
    inline_quiz_answers: list[InlineQuizAnswerContext] | None = None
    message: str = Field(
        min_length=1,
        max_length=get_settings().chat.message_max_length,
    )
    current_document_id: str | None = None
    current_page: int | None = None
    total_pages: int | None = None
    model: str | None = None
    reasoning: str | None = None
    images: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    attachments: list[FileAttachment] = Field(default_factory=list)

    @field_validator("attachments", mode="after")
    @classmethod
    def validate_attachment_count(cls, v: list[FileAttachment]) -> list[FileAttachment]:
        limit = get_settings().chat.max_attachments_per_message
        if len(v) > limit:
            raise ValueError(f"Maximum {limit} attachments per message.")
        return v

    @field_validator("folder_id", mode="before")
    @classmethod
    def coerce_empty_folder_id(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() in ("", "null", "undefined"):
            return None
        return v

    @field_validator("test_session_id", "question_id", "lesson_id", "current_block_id", "scope_type", "feedback_note_id", mode="before")
    @classmethod
    def coerce_empty_scope_ids(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() in ("", "null", "undefined"):
            return None
        return v

    @model_validator(mode="after")
    def validate_practice_scope_pair(self) -> "ChatMessageRequest":
        ts, q = self.test_session_id, self.question_id
        if (ts is None) ^ (q is None):
            raise ValueError(
                "test_session_id and question_id must both be set or both omitted."
            )
        if ts is not None:
            assert q is not None
            try:
                uuid.UUID(ts)
            except ValueError as e:
                raise ValueError("test_session_id must be a valid UUID.") from e
            try:
                uuid.UUID(q)
            except ValueError as e:
                raise ValueError("question_id must be a valid UUID.") from e
        return self

    @model_validator(mode="after")
    def validate_scope_type(self) -> "ChatMessageRequest":
        if self.scope_type is not None:
            if self.scope_type not in ("practice", "review", "feedback_review"):
                raise ValueError("scope_type must be 'practice', 'review', or 'feedback_review'.")
            if self.test_session_id is None:
                raise ValueError("scope_type requires test_session_id and question_id.")
        if self.feedback_note_id is not None:
            if self.scope_type != "feedback_review":
                raise ValueError("feedback_note_id requires scope_type='feedback_review'.")
            try:
                uuid.UUID(self.feedback_note_id)
            except ValueError as e:
                raise ValueError("feedback_note_id must be a valid UUID.") from e
        return self

    @model_validator(mode="after")
    def validate_lesson_chat_scope(self) -> "ChatMessageRequest":
        if self.lesson_id is None:
            return self
        if self.test_session_id is not None:
            raise ValueError(
                "lesson_id cannot be combined with test_session_id and question_id."
            )
        try:
            uuid.UUID(self.lesson_id)
        except ValueError as e:
            raise ValueError("lesson_id must be a valid UUID.") from e
        return self

    @model_validator(mode="after")
    def validate_current_document_context(self) -> "ChatMessageRequest":
        values = [self.current_document_id, self.current_page, self.total_pages]
        provided_count = sum(value is not None for value in values)

        if provided_count not in (0, 3):
            raise ValueError(
                "current_document_id, current_page, and total_pages must be provided together."
            )

        if provided_count == 3:
            if self.current_page is not None and self.current_page < 1:
                raise ValueError("current_page must be >= 1.")
            if self.total_pages is not None and self.total_pages < 1:
                raise ValueError("total_pages must be >= 1.")
            if (
                self.current_page is not None
                and self.total_pages is not None
                and self.current_page > self.total_pages
            ):
                raise ValueError("current_page must be <= total_pages.")

        return self


class CitationSchema(BaseModel):
    document_id: str
    document_name: str
    pages: list[int]
    chunk_ids: list[str]


class AttachmentSchema(BaseModel):
    filename: str
    mime_type: str
    type: str  # "image" | "pdf" | "text"
    url: str | None = None  # presigned S3 URL for downloadable files


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict
    citations: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    attachments: list[AttachmentSchema] = Field(default_factory=list)
    created_at: datetime
    parent_id: str | None = None
    sibling_count: int = 1
    version_index: int = 1


class ConversationSummary(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: str
    test_session_id: str | None = None
    question_id: str | None = None
    lesson_id: str | None = None
    scope_type: str | None = None
    feedback_note_id: str | None = None


class ListConversationsResponse(BaseModel):
    conversations: list[ConversationSummary]
    has_more: bool = False


class GetMessagesResponse(BaseModel):
    messages: list[MessageSchema]
    has_more: bool
    next_cursor: str | None = None


class FolderDocumentRead(BaseModel):
    id: str
    name: str
    page_count: int


class ListFolderDocumentsResponse(BaseModel):
    documents: list[FolderDocumentRead]


class RenameTitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class RegenerateRequest(BaseModel):
    message: str | None = Field(
        default=None, min_length=1, max_length=get_settings().chat.message_max_length
    )
    images: list[str] = Field(default_factory=list)
    current_document_id: str | None = None
    current_page: int | None = None
    total_pages: int | None = None
    model: str | None = None
    reasoning: str | None = None
    citations: list[str] = Field(default_factory=list)
    attachments: list[FileAttachment] = Field(default_factory=list)
    current_block_id: str | None = None
    inline_quiz_answers: list[InlineQuizAnswerContext] | None = None

    @field_validator("attachments", mode="after")
    @classmethod
    def validate_attachment_count(cls, v: list[FileAttachment]) -> list[FileAttachment]:
        limit = get_settings().chat.max_attachments_per_message
        if len(v) > limit:
            raise ValueError(f"Maximum {limit} attachments per message.")
        return v


class AvailableModelsResponse(BaseModel):
    models: list[str]
    reasoning_levels: list[str]


class SwitchBranchRequest(BaseModel):
    message_id: str
    direction: str  # "next" | "prev"

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("next", "prev"):
            raise ValueError("direction must be 'next' or 'prev'")
        return v

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("message_id must be a valid UUID")
        return v


class SwitchBranchResponse(BaseModel):
    active_path: list[str]
    messages: list[MessageSchema]


class UpdateActivePathRequest(BaseModel):
    active_path: list[str]

    @field_validator("active_path")
    @classmethod
    def validate_active_path(cls, v: list[str]) -> list[str]:
        for item in v:
            try:
                uuid.UUID(item)
            except ValueError:
                raise ValueError(f"Each item in active_path must be a valid UUID, got: {item}")
        return v


class SiblingSchema(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    parent_id: str | None = None
    version_index: int = 1


class GetSiblingsResponse(BaseModel):
    siblings: list[SiblingSchema]
