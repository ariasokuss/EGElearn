#!/usr/bin/env python3
"""
Ensure Qdrant collections exist with the correct schema and payload indexes.

Idempotent — safe to run on every deploy, k8s init-container, or locally.
Collections are never auto-deleted; a warning is printed if vector_size
mismatches so the operator can decide whether to recreate manually.

Usage:
    # from backend/ root
    uv run python scripts/setup_qdrant.py

    # override settings via env
    QDRANT__URL=https://my-host.cloud.qdrant.io uv run python scripts/setup_qdrant.py
"""

import asyncio
import logging
import sys
from pathlib import Path

from grpc import StatusCode
from grpc.aio import AioRpcError

# Make `src` importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from src.config import QdrantSettings, get_settings
from src.core.qdrant import (
    CHUNKS_COLLECTION,
    CLUSTERS_COLLECTION,
    create_qdrant_client,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Payload fields to index per collection.
# Indexed fields are used in filter conditions — without indexes Qdrant does a
# full scan, which is slow at scale.
_INDEXES: dict[str, list[str]] = {
    CHUNKS_COLLECTION: [
        "user_id",
        "folder_id",
        "document_id",
        "cluster_id",
        "megacluster_id",
    ],
    CLUSTERS_COLLECTION: ["user_id", "folder_id", "document_id", "megacluster_id"],
}


async def ensure_collection(
    client,
    name: str,
    vector_size: int,
) -> None:
    exists = await client.collection_exists(name)

    if exists:
        # Verify vector size to catch mismatches early (never auto-delete data).
        info = await client.get_collection(name)
        current_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if current_size != vector_size:
            log.warning(
                "Collection '%s' exists with vector_size=%d but config expects %d. "
                "If you changed embedding models, recreate the collection manually "
                "after migrating or discarding existing data.",
                name,
                current_size,
                vector_size,
            )
        else:
            log.info(
                "Collection '%s' already exists (vector_size=%d) ✓", name, vector_size
            )
    else:
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        log.info("Created collection '%s' (vector_size=%d)", name, vector_size)

    # Payload indexes — idempotent in Qdrant (no error if already exist).
    for field in _INDEXES[name]:
        await client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    log.info(
        "  Ensured %d payload index(es) on '%s': %s",
        len(_INDEXES[name]),
        name,
        ", ".join(_INDEXES[name]),
    )


async def main() -> None:
    settings: QdrantSettings = get_settings().qdrant

    log.info(
        "Connecting to Qdrant at %s (prefer_grpc=%s) ...",
        settings.url,
        settings.prefer_grpc,
    )

    client = create_qdrant_client(settings)

    try:
        try:
            for collection_name in (CHUNKS_COLLECTION, CLUSTERS_COLLECTION):
                await ensure_collection(client, collection_name, settings.vector_size)
        except AioRpcError as exc:
            if exc.code() != StatusCode.UNAVAILABLE or not settings.prefer_grpc:
                raise

            log.warning(
                "gRPC connection to %s failed; retrying via REST",
                settings.url,
            )
            await client.close()
            client = create_qdrant_client(settings, prefer_grpc=False)

            for collection_name in (CHUNKS_COLLECTION, CLUSTERS_COLLECTION):
                await ensure_collection(client, collection_name, settings.vector_size)

        log.info("Qdrant setup complete.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
