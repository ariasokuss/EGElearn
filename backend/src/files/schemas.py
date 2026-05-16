from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.files.models import FolderType
from src.processing.models import ProcessingJobStatus

ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: FolderType = FolderType.user


class FolderOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    name: str
    type: FolderType
    position: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderReorderRequest(BaseModel):
    folder_ids: list[uuid.UUID] = Field(min_length=1)


class UploadRequest(BaseModel):
    """Create a direct upload slot for a document."""

    name: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=500)
    content_type: str
    size_bytes: int | None = Field(default=None, gt=0)


class UploadResponse(BaseModel):
    """Return the direct upload URL and the created document id."""

    document_id: uuid.UUID
    upload_url: str
    source_s3_key: str
    expires_in: int


class UploadConfirmRequest(BaseModel):
    """Confirm a direct upload and enqueue processing."""

    size_bytes: int | None = Field(default=None, gt=0)


class ProcessingJobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    folder_id: uuid.UUID
    status: ProcessingJobStatus
    attempt_count: int
    error_message: str | None
    source_s3_key: str
    processed_s3_key: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
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
    processing_job: ProcessingJobOut | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchUploadResponse(BaseModel):
    """Return uploaded documents with their queued jobs."""

    documents: list[DocumentOut]


class MarkdownResponse(BaseModel):
    markdown: str


class DownloadUrlResponse(BaseModel):
    download_url: str
