"""Chat service protocols."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from src.chat.entities import (
    Conversation,
    DocumentInfo,
    Message,
    MessageRole,
    RetrievedChunk,
)


class ChatRepository(Protocol):
    async def create_conversation(
        self,
        user_id: str,
        folder_id: str | None,
        title: str | None,
        *,
        test_session_id: str | None = None,
        question_id: str | None = None,
        lesson_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
    ) -> str: ...

    async def get_conversation(self, conversation_id: str) -> Conversation | None: ...

    async def list_conversations(
        self,
        user_id: str,
        folder_id: str | None,
        *,
        limit: int = 50,
        offset: int = 0,
        test_session_id: str | None = None,
        question_id: str | None = None,
        lesson_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def delete_conversation(self, conversation_id: str) -> bool: ...

    async def save_message(
        self,
        message: Message,
        *,
        parent_id: str | None = None,
        version_index: int = 1,
    ) -> str: ...

    async def get_messages(
        self,
        conversation_id: str,
        roles: list[MessageRole] | None = None,
        limit: int | None = None,
    ) -> list[Message]: ...

    async def get_messages_page(
        self,
        conversation_id: str,
        roles: list[MessageRole],
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Message], bool, str | None]: ...

    async def update_conversation_title(
        self, conversation_id: str, title: str
    ) -> None: ...

    async def touch_conversation(self, conversation_id: str) -> None: ...

    async def get_message(
        self, message_id: str, conversation_id: str
    ) -> Message | None: ...

    async def delete_messages_from(
        self, conversation_id: str, message_id: str
    ) -> int: ...

    async def get_sibling_count(
        self, message_id: str, conversation_id: str
    ) -> int: ...

    async def get_siblings(
        self, message_id: str, conversation_id: str
    ) -> list[Message]: ...

    async def get_next_version_index(
        self, parent_id: str | None, conversation_id: str, role: str | None = None
    ) -> int: ...

    async def get_subtree_path(
        self, message_id: str, conversation_id: str, active_path: list[str]
    ) -> list[str]: ...

    async def update_active_path(
        self, conversation_id: str, new_path: list[str]
    ) -> None: ...

    async def append_to_active_path(
        self, conversation_id: str, message_id: str
    ) -> None: ...

    async def get_active_path(
        self, conversation_id: str
    ) -> list[str]: ...

    async def get_active_path_messages(
        self,
        conversation_id: str,
        roles: list[MessageRole],
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Message], bool, str | None]: ...

    async def get_active_path_history(
        self,
        conversation_id: str,
        roles: list[MessageRole],
    ) -> list[Message]: ...

    async def get_messages_batch(
        self, message_ids: list[str], conversation_id: str
    ) -> dict[str, Message]: ...

    async def get_folder_documents(
        self, user_id: str, folder_id: str
    ) -> list[DocumentInfo]: ...


class RetrievalService(Protocol):
    async def semantic_search(
        self,
        user_id: str,
        query_embedding: list[float],
        document_ids: list[str] | None,
        top_k: int,
        threshold: float,
    ) -> list[RetrievedChunk]: ...

    async def get_chunks_by_pages(
        self,
        user_id: str,
        document_id: str,
        start_page: int,
        end_page: int,
        buffer: int,
    ) -> list[RetrievedChunk]: ...


class EmbeddingService(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


class LLMGateway(Protocol):
    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> dict[str, Any]: ...

    async def chat_tools_only(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> tuple[list[dict[str, Any]], Any]: ...

    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> tuple[str, Any]: ...

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> AsyncIterator[str | Any]: ...

    async def chat_stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_override: str | None = None,
        reasoning_level: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def generate_title(self, user_message: str) -> tuple[str, Any]: ...
