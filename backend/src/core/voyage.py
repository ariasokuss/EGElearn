from __future__ import annotations

import uuid
from typing import Any

from src.config import get_settings
from src.core.qdrant import ChunkPayload, ChunkPoint, QdrantStore


class VoyageEmbeddingService:
    """Voyage AI embedding service with automatic batching."""

    def __init__(
        self,
        voyage_client: Any,
        model: str | None = None,
        output_dimension: int | None = None,
    ) -> None:
        self._client = voyage_client
        settings = get_settings()
        self._model = model or settings.voyage.embedding_model
        self._output_dimension = output_dimension or settings.voyage.output_dimension
        self._max_batch_tokens = settings.voyage.max_batch_tokens

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval."""
        if not text.strip():
            raise ValueError("Embedding query cannot be empty.")
        embeddings = await self._embed_one_batch([text], input_type="query")
        return embeddings[0]

    async def embed_batch(
        self,
        texts: list[str],
        *,
        input_type: str = "document",
        store: bool = False,
        qdrant_store: QdrantStore | None = None,
        chunks: list[ChunkPayload] | None = None,
        filter_empty: bool = False,
    ) -> list[list[float]]:
        """Embed multiple texts with optional Qdrant storage.

        When store=True, saves embeddings to Qdrant. Requires qdrant_store and chunks
        with matching length and order (chunks[i].content == texts[i]).

        When filter_empty=True, empty/whitespace-only strings are silently skipped
        and receive a zero-vector in the output.
        """
        if not texts:
            return []

        if filter_empty:
            return await self._embed_with_empty_filter(texts, input_type)

        self._validate_texts(texts)
        if store:
            self._validate_store_args(qdrant_store, chunks, len(texts))

        embeddings = await self._embed_in_batches(texts, input_type)

        if store and qdrant_store and chunks:
            await self._store_embeddings(qdrant_store, chunks, embeddings)

        return embeddings

    async def _embed_with_empty_filter(
        self, texts: list[str], input_type: str
    ) -> list[list[float]]:
        """Embed a batch while replacing empty strings with zero-vectors."""
        non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty_indices:
            return [[] for _ in texts]

        non_empty_texts = [texts[i] for i in non_empty_indices]
        non_empty_embeddings = await self._embed_in_batches(non_empty_texts, input_type)

        dim = len(non_empty_embeddings[0]) if non_empty_embeddings else 0
        result: list[list[float]] = [[0.0] * dim for _ in texts]
        for idx, emb in zip(non_empty_indices, non_empty_embeddings):
            result[idx] = emb
        return result

    async def _embed_in_batches(
        self, texts: list[str], input_type: str
    ) -> list[list[float]]:
        """Split texts into token-safe batches and embed each one."""
        batches = self._build_batches(texts)
        if len(batches) <= 1:
            return await self._embed_one_batch(texts, input_type)

        all_embeddings: list[list[float]] = [[] for _ in texts]
        for batch_indices in batches:
            batch_texts = [texts[i] for i in batch_indices]
            batch_embeddings = await self._embed_one_batch(batch_texts, input_type)
            for idx, emb in zip(batch_indices, batch_embeddings):
                all_embeddings[idx] = emb
        return all_embeddings

    async def _embed_one_batch(
        self, texts: list[str], input_type: str
    ) -> list[list[float]]:
        """Call the Voyage API for a single batch."""
        if hasattr(self._client, "embed"):
            response = await self._client.embed(
                texts,
                model=self._model,
                input_type=input_type,
                output_dimension=self._output_dimension,
            )
            return [list(emb) for emb in response.embeddings]

        if hasattr(self._client, "embeddings") and hasattr(
            self._client.embeddings, "create"
        ):
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                input_type=input_type,
                output_dimension=self._output_dimension,
            )
            data = getattr(response, "data", None) or []
            if len(data) != len(texts):
                raise RuntimeError(
                    "Voyage embeddings response count does not match input count."
                )
            return [list(d.embedding) for d in data]

        raise RuntimeError(
            "Unsupported Voyage client: expected embed() or embeddings.create()."
        )

    def _build_batches(self, texts: list[str]) -> list[list[int]]:
        """Group text indices into batches that fit within the token limit."""
        batches: list[list[int]] = []
        current_batch: list[int] = []
        current_tokens = 0

        for i, text in enumerate(texts):
            tokens = max(len(text) // 4, 1)
            if current_batch and current_tokens + tokens > self._max_batch_tokens:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            current_batch.append(i)
            current_tokens += tokens

        if current_batch:
            batches.append(current_batch)
        return batches

    @staticmethod
    async def _store_embeddings(
        qdrant_store: QdrantStore,
        chunks: list[ChunkPayload],
        embeddings: list[list[float]],
    ) -> None:
        """Upload chunk embeddings to Qdrant."""
        points = [
            ChunkPoint(
                chunk_id=uuid.uuid4(),
                vector=emb,
                **chunk.model_dump(),
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        await qdrant_store.upload_chunks(points)

    @staticmethod
    def _validate_texts(texts: list[str]) -> None:
        """Raise if any text is empty or whitespace-only."""
        if any(not t or not t.strip() for t in texts):
            raise ValueError("Embedding batch cannot contain empty strings.")

    @staticmethod
    def _validate_store_args(
        qdrant_store: QdrantStore | None,
        chunks: list[ChunkPayload] | None,
        text_count: int,
    ) -> None:
        """Raise if store arguments are missing or mismatched."""
        if qdrant_store is None:
            raise ValueError("qdrant_store required when store=True.")
        if not chunks or len(chunks) != text_count:
            raise ValueError(
                "chunks required when store=True; len(chunks) must match len(texts)."
            )
