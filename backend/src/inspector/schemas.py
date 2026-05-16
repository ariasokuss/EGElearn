from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.files.models import FolderType

# ---------------------------------------------------------------------------
# Base reads (inspector-local, compatible with monolith models)
# ---------------------------------------------------------------------------


class FolderRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: FolderType
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentRead(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    original_filename: str
    content_type: str
    size_bytes: int | None
    page_count: int | None
    source_s3_key: str
    processed_s3_key: str | None
    processing_status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobSummaryRead(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    max_attempts: int
    error: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Chunk/Cluster (from Qdrant payload)
# ---------------------------------------------------------------------------


class ChunkRead(BaseModel):
    chunk_id: uuid.UUID
    cluster_id: str
    page: int
    text: str


class ClusterRead(BaseModel):
    cluster_id: uuid.UUID
    topic_description: str
    content_text: str
    cluster_type: str
    content_quality: int
    document_pages: list[int] | None
    chunk_ids: list[str] | None = None
    created_at: datetime | None = None  # optional, for frontend
    content_token_count: int | None = None  # optional, for frontend


# ---------------------------------------------------------------------------
# Overview & summaries
# ---------------------------------------------------------------------------


class DocumentSummaryRead(DocumentRead):
    cluster_count: int
    chunk_count: int
    recent_jobs: list[JobSummaryRead]


class QdrantObjectRead(BaseModel):
    object_id: str | None
    properties: dict[str, Any]


class MegaclusterSummaryRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    document_ids: list[str] | None
    cluster_ids: list[str] | None
    cluster_count: int
    progress: int
    created_at: datetime
    cluster_topics: list[str]
    qdrant_clusters: list[QdrantObjectRead] = []


class FolderSummaryRead(FolderRead):
    document_count: int
    cluster_count: int
    chunk_count: int
    megacluster_count: int
    documents: list[DocumentSummaryRead]
    megaclusters: list[MegaclusterSummaryRead]
    recent_jobs: list[JobSummaryRead]


class InspectorOverviewRead(BaseModel):
    user_id: uuid.UUID
    email: str | None
    folders: list[FolderSummaryRead]


# ---------------------------------------------------------------------------
# Document inspector detail
# ---------------------------------------------------------------------------


class ClusterBundleRead(BaseModel):
    cluster: ClusterRead
    chunks: list[ChunkRead]


class QdrantSnapshotRead(BaseModel):
    clusters: list[QdrantObjectRead]
    chunks: list[QdrantObjectRead]
    megaclusters: list[QdrantObjectRead] = []  # empty in monolith, for frontend compat


class StorageSnapshotRead(BaseModel):
    qdrant_counts: dict[str, int]
    weaviate_counts: dict[str, int]  # alias for frontend compatibility
    database_counts: dict[str, int]  # alias for frontend compatibility
    notes: list[str]


class DocumentInspectorRead(BaseModel):
    folder: FolderRead
    document: DocumentRead
    markdown: str | None
    clusters: list[ClusterBundleRead]
    megaclusters: list[MegaclusterSummaryRead]
    recent_jobs: list[JobSummaryRead]
    qdrant: QdrantSnapshotRead
    weaviate: QdrantSnapshotRead  # alias for frontend compatibility
    storage: StorageSnapshotRead


class DocumentLiveStatusRead(BaseModel):
    document: DocumentRead
    recent_jobs: list[JobSummaryRead]
    cluster_count: int
    chunk_count: int
