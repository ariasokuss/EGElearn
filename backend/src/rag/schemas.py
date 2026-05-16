"""RAG schemas — compatible with chat RetrievalService interface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetrievedChunk:
    """Chunk retrieved from semantic search or page-range query."""

    chunk_id: str
    text: str
    document_id: str
    document_name: str
    page: int
    similarity_score: float | None = None
