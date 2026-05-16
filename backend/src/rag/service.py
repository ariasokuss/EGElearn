"""RAG service — semantic search and page-range retrieval over Qdrant chunks."""

from __future__ import annotations

from src.config import get_settings
from src.core.qdrant import QdrantStore
from src.rag.schemas import RetrievedChunk


class RagService:
    """
    RAG retrieval service compatible with chat RetrievalService interface.
    Uses Qdrant chunks collection for semantic search and page-range queries.
    """

    def __init__(
        self,
        qdrant_store: QdrantStore,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> None:
        settings = get_settings()
        self._store = qdrant_store
        self._top_k = top_k if top_k is not None else settings.rag.top_k
        self._threshold = (
            threshold if threshold is not None else settings.rag.similarity_threshold
        )

    async def semantic_search(
        self,
        user_id: str,
        query_embedding: list[float],
        document_ids: list[str] | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        Semantic search over chunks.
        document_ids: optional list to narrow scope; None = search all user docs.
        """
        k = top_k if top_k is not None else self._top_k
        thresh = threshold if threshold is not None else self._threshold

        scored = await self._store.search_chunks(
            query_vector=query_embedding,
            user_id=user_id,
            document_ids=document_ids if document_ids else None,
            limit=k,
            score_threshold=thresh,
        )

        return [
            RetrievedChunk(
                chunk_id=str(c.chunk_id),
                text=c.content,
                document_id=c.document_id,
                document_name=c.document_id,
                page=c.page,
                similarity_score=c.score,
            )
            for c in scored
        ]

    async def get_chunks_by_pages(
        self,
        user_id: str,
        document_id: str,
        start_page: int,
        end_page: int,
        buffer: int = 0,
    ) -> list[RetrievedChunk]:
        """
        Retrieve chunks for a document within a page range (with optional buffer).
        """
        records = await self._store.get_chunks_by_page_range(
            user_id=user_id,
            document_id=document_id,
            start_page=start_page,
            end_page=end_page,
            buffer=buffer,
        )

        return [
            RetrievedChunk(
                chunk_id=str(r.chunk_id),
                text=r.content,
                document_id=r.document_id,
                document_name=r.document_id,
                page=r.page,
                similarity_score=None,
            )
            for r in records
        ]
