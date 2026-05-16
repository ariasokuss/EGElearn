"""Gemini Embedding 2 via google-genai SDK."""

from __future__ import annotations

import asyncio

from google import genai

from src.config import get_settings


class GeminiEmbeddingService:
    """Gemini Embedding 2 query embedding adapter."""

    def __init__(self, genai_client: genai.Client, model: str | None = None) -> None:
        self._client = genai_client
        self._model = model or get_settings().genai.embedding_model

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Embedding query cannot be empty.")

        response = await asyncio.to_thread(
            self._client.models.embed_content,
            model=self._model,
            contents=text,
        )

        if not response.embeddings:
            raise RuntimeError("Gemini embeddings response did not include embeddings.")

        values = response.embeddings[0].values
        if not values:
            raise RuntimeError("Gemini embedding has no values.")

        return list(values)
