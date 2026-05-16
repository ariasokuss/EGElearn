"""Chat domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class ToolName(str, Enum):
    RAG_SEARCH = "rag_search"
    GET_PAGES = "get_pages"
    ASK_CLARIFICATION = "ask_clarification"
    TO_FINAL_RESPONSE = "to_final_response"


@dataclass(slots=True)
class DocumentInfo:
    document_id: str
    name: str
    page_count: int


@dataclass(slots=True)
class UserContext:
    folder_id: str | None
    current_document_id: str | None = None
    current_document_name: str | None = None
    current_page: int | None = None
    total_pages: int | None = None


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    document_id: str
    document_name: str
    page: int
    similarity_score: float | None = None


@dataclass(slots=True)
class Citation:
    document_id: str
    document_name: str
    pages: list[int]
    chunk_ids: list[str]


@dataclass(slots=True)
class Message:
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None
    parent_id: str | None = None
    version_index: int = 1


@dataclass(slots=True)
class Conversation:
    id: str
    user_id: str
    folder_id: str | None
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    test_session_id: str | None = None
    question_id: str | None = None
    lesson_id: str | None = None
    active_path: list[str] | None = None
    scope_type: str | None = None
    feedback_note_id: str | None = None


@dataclass(slots=True)
class ToolCallResult:
    tool: ToolName
    arguments: dict
    result: dict
    token_count: int


@dataclass(slots=True)
class AgentLoopState:
    iteration: int = 0
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    seen_chunk_ids: set[str] = field(default_factory=set)
    total_retrieval_tokens: int = 0
