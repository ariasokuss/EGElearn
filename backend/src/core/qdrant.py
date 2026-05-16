import logging
import uuid

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
    Range,
)

from src.config import QdrantSettings

logger = logging.getLogger(__name__)

CHUNKS_COLLECTION = "chunks"
CLUSTERS_COLLECTION = "clusters"

_BATCH_SIZE = 500


def create_qdrant_client(
    settings: QdrantSettings,
    *,
    prefer_grpc: bool | None = None,
) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.url,
        api_key=settings.api_key,
        prefer_grpc=settings.prefer_grpc if prefer_grpc is None else prefer_grpc,
        timeout=settings.timeout,
    )


class ChunkPayload(BaseModel):
    user_id: str
    folder_id: str
    document_id: str
    cluster_id: str
    megacluster_id: str

    page: int
    content: str
    content_type: str  # "study" | "admin" | "trash"
    content_quality: int  # 1-5 content quality score


class ClusterPayload(BaseModel):
    user_id: str
    folder_id: str
    document_id: str
    megacluster_id: str

    description: str  # LLM-generated topic summary
    pages: list[int]  # all pages this cluster spans
    content: str  # raw text of the cluster
    content_type: str  # "study" | "admin" | "trash"
    content_quality: int  # 1-5


class ChunkPoint(ChunkPayload):
    """Chunk ready for upload — includes point ID and embedding vector."""

    chunk_id: uuid.UUID
    vector: list[float]


class ClusterPoint(ClusterPayload):
    """Cluster ready for upload — includes point ID and embedding vector."""

    cluster_id: uuid.UUID
    vector: list[float]


class ChunkRecord(ChunkPayload):
    """Chunk retrieved via scroll (filter only, no similarity score)."""

    chunk_id: uuid.UUID


class ClusterRecord(ClusterPayload):
    """Cluster retrieved via scroll."""

    cluster_id: uuid.UUID


class ScoredChunk(ChunkPayload):
    """Chunk retrieved via vector search — includes cosine similarity score."""

    chunk_id: uuid.UUID
    score: float


class ScoredCluster(ClusterPayload):
    """Cluster retrieved via vector search."""

    cluster_id: uuid.UUID
    score: float


def _build_filter(
    user_id: str,
    *,
    folder_id: str | None = None,
    document_id: str | None = None,
    document_ids: list[str] | None = None,
    cluster_id: str | None = None,
    megacluster_id: str | None = None,
    page_range: tuple[int, int] | None = None,
) -> Filter:
    """Build a Qdrant Filter with user_id required and all other keys optional."""
    must: list[FieldCondition] = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id)),
    ]

    if document_id and document_ids:
        logger.warning(
            "document_id and document_ids are provided together, document_ids will be ignored"
        )
        document_ids = None

    if folder_id is not None:
        must.append(FieldCondition(key="folder_id", match=MatchValue(value=folder_id)))
    if document_id is not None:
        must.append(
            FieldCondition(key="document_id", match=MatchValue(value=document_id))
        )
    elif document_ids:
        must.append(FieldCondition(key="document_id", match=MatchAny(any=document_ids)))
    if cluster_id is not None:
        must.append(
            FieldCondition(key="cluster_id", match=MatchValue(value=cluster_id))
        )
    if megacluster_id is not None:
        must.append(
            FieldCondition(key="megacluster_id", match=MatchValue(value=megacluster_id))
        )
    if page_range is not None:
        start_page, end_page = page_range
        must.append(
            FieldCondition(
                key="page", range=Range(gte=float(start_page), lte=float(end_page))
            )
        )
    return Filter(must=must)


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    @classmethod
    async def create(cls, settings: QdrantSettings) -> "QdrantStore":
        return cls(create_qdrant_client(settings))

    async def upload_chunks(self, chunks: list[ChunkPoint]) -> None:
        """Upsert a batch of chunk points. Processes in sub-batches of 500."""
        if not chunks:
            return
        for i in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[i : i + _BATCH_SIZE]
            points = [
                PointStruct(
                    id=str(chunk.chunk_id),
                    vector=chunk.vector,
                    payload=chunk.model_dump(exclude={"chunk_id", "vector"}),
                )
                for chunk in batch
            ]
            await self._client.upsert(
                collection_name=CHUNKS_COLLECTION,
                points=points,
                wait=True,
            )
            logger.debug(
                "Upserted %d/%d chunks (batch starting at %d)",
                len(points),
                len(chunks),
                i,
            )

    async def upload_clusters(self, clusters: list[ClusterPoint]) -> None:
        """Upsert a batch of cluster points."""
        if not clusters:
            return
        for i in range(0, len(clusters), _BATCH_SIZE):
            batch = clusters[i : i + _BATCH_SIZE]
            points = [
                PointStruct(
                    id=str(cluster.cluster_id),
                    vector=cluster.vector,
                    payload=cluster.model_dump(exclude={"cluster_id", "vector"}),
                )
                for cluster in batch
            ]
            await self._client.upsert(
                collection_name=CLUSTERS_COLLECTION,
                points=points,
                wait=True,
            )
            logger.debug(
                "Upserted %d/%d clusters (batch starting at %d)",
                len(points),
                len(clusters),
                i,
            )

    async def search_chunks(
        self,
        query_vector: list[float],
        user_id: str,
        *,
        folder_id: str | None = None,
        document_id: str | None = None,
        document_ids: list[str] | None = None,
        megacluster_id: str | None = None,
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> list[ScoredChunk]:
        """
        Semantic search over chunks.
        user_id is always applied; other filters narrow scope further.
        Use document_id for a single doc, or document_ids for multiple (OR).
        """
        response = await self._client.query_points(
            collection_name=CHUNKS_COLLECTION,
            query=query_vector,
            query_filter=_build_filter(
                user_id,
                folder_id=folder_id,
                document_id=document_id,
                document_ids=document_ids,
                megacluster_id=megacluster_id,
            ),
            limit=limit,
            score_threshold=score_threshold or None,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        return [
            ScoredChunk(
                chunk_id=uuid.UUID(str(point.id)),
                score=point.score,
                **point.payload,
            )
            for point in points
        ]

    async def get_chunks_by_page_range(
        self,
        user_id: str,
        document_id: str,
        start_page: int,
        end_page: int,
        *,
        buffer: int = 0,
        limit: int = 500,
    ) -> list[ChunkRecord]:
        """
        Retrieve chunks for a document within a page range (with optional buffer).
        """
        buffered_start = max(1, start_page - buffer)
        buffered_end = end_page + buffer
        records, _ = await self._client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=_build_filter(
                user_id,
                document_id=document_id,
                page_range=(buffered_start, buffered_end),
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        result = [
            ChunkRecord(chunk_id=uuid.UUID(str(r.id)), **r.payload) for r in records
        ]
        result.sort(key=lambda c: c.page)
        return result

    async def search_clusters(
        self,
        query_vector: list[float],
        user_id: str,
        *,
        folder_id: str | None = None,
        document_id: str | None = None,
        megacluster_id: str | None = None,
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[ScoredCluster]:
        """Semantic search over cluster summaries."""
        response = await self._client.query_points(
            collection_name=CLUSTERS_COLLECTION,
            query=query_vector,
            query_filter=_build_filter(
                user_id,
                folder_id=folder_id,
                document_id=document_id,
                megacluster_id=megacluster_id,
            ),
            limit=limit,
            score_threshold=score_threshold or None,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        return [
            ScoredCluster(
                cluster_id=uuid.UUID(str(point.id)),
                score=point.score,
                **point.payload,
            )
            for point in points
        ]

    async def get_chunks(
        self,
        user_id: str,
        *,
        folder_id: str | None = None,
        document_id: str | None = None,
        cluster_id: str | None = None,
        megacluster_id: str | None = None,
        limit: int = 100,
        offset: uuid.UUID | None = None,
    ) -> tuple[list[ChunkRecord], uuid.UUID | None]:
        """
        Retrieve chunks by filter without vector similarity.
        Returns (records, next_offset) for cursor-based pagination.
        Pass next_offset as offset on the next call to get the following page.
        next_offset is None when there are no more results.
        """
        records, next_page = await self._client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=_build_filter(
                user_id,
                folder_id=folder_id,
                document_id=document_id,
                cluster_id=cluster_id,
                megacluster_id=megacluster_id,
            ),
            limit=limit,
            offset=str(offset) if offset else None,
            with_payload=True,
            with_vectors=False,
        )
        next_uuid = uuid.UUID(str(next_page)) if next_page else None
        return [
            ChunkRecord(chunk_id=uuid.UUID(str(r.id)), **r.payload) for r in records
        ], next_uuid

    async def get_clusters(
        self,
        user_id: str,
        *,
        folder_id: str | None = None,
        document_id: str | None = None,
        megacluster_id: str | None = None,
        limit: int = 100,
        offset: uuid.UUID | None = None,
    ) -> tuple[list[ClusterRecord], uuid.UUID | None]:
        """
        Retrieve clusters by filter without vector similarity.
        Returns (records, next_offset) for cursor-based pagination.
        """
        records, next_page = await self._client.scroll(
            collection_name=CLUSTERS_COLLECTION,
            scroll_filter=_build_filter(
                user_id,
                folder_id=folder_id,
                document_id=document_id,
                megacluster_id=megacluster_id,
            ),
            limit=limit,
            offset=str(offset) if offset else None,
            with_payload=True,
            with_vectors=False,
        )
        next_uuid = uuid.UUID(str(next_page)) if next_page else None
        return [
            ClusterRecord(cluster_id=uuid.UUID(str(r.id)), **r.payload) for r in records
        ], next_uuid

    async def delete_by_document(self, user_id: str, document_id: str) -> None:
        """Delete all chunks and clusters belonging to a single document."""
        doc_filter = FilterSelector(
            filter=_build_filter(user_id, document_id=document_id)
        )
        for collection in (CHUNKS_COLLECTION, CLUSTERS_COLLECTION):
            await self._client.delete(
                collection_name=collection,
                points_selector=doc_filter,
                wait=True,
            )
        logger.debug("Deleted vectors for document %s (user %s)", document_id, user_id)

    async def delete_by_folder(self, user_id: str, folder_id: str) -> None:
        """Delete all chunks and clusters belonging to a folder."""
        folder_filter = FilterSelector(
            filter=_build_filter(user_id, folder_id=folder_id)
        )
        for collection in (CHUNKS_COLLECTION, CLUSTERS_COLLECTION):
            await self._client.delete(
                collection_name=collection,
                points_selector=folder_filter,
                wait=True,
            )
        logger.debug("Deleted vectors for folder %s (user %s)", folder_id, user_id)

    async def close(self) -> None:
        await self._client.close()
