import logging
import uuid
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.s3 import S3Client
from src.files.models import Document, Folder, FolderType
from src.roadmap.models import UserFolderPosition
from src.files.schemas import ALLOWED_CONTENT_TYPES
from src.processing.markdown import infer_page_count
from src.processing.models import ProcessingJob, ProcessingJobStatus

logger = logging.getLogger(__name__)

_UPLOAD_URL_TTL = 900


class FilesError(Exception):
    """Raised for business-logic failures in the files domain."""


async def create_folder(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    type: FolderType = FolderType.user,
) -> Folder:
    folder = Folder(user_id=user_id, name=name, type=type)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def list_folders(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Folder]:
    result = await db.scalars(
        select(Folder)
        .where(or_(Folder.user_id == user_id, Folder.user_id.is_(None)))
        .order_by(Folder.created_at.desc())
    )
    return list(result)


async def list_folders_by_type(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_type: FolderType,
) -> list[tuple[Folder, int]]:
    """Returns list of (folder, position) tuples ordered by user's position, then created_at.

    On first call for a given user+type, seeds user_folder_positions with the default order.
    """
    rows = await db.execute(
        select(Folder, UserFolderPosition.position.label("pos"))
        .outerjoin(
            UserFolderPosition,
            (UserFolderPosition.folder_id == Folder.id)
            & (UserFolderPosition.user_id == user_id),
        )
        .where(
            or_(Folder.user_id == user_id, Folder.user_id.is_(None)),
            Folder.type == folder_type,
        )
        .order_by(
            func.coalesce(UserFolderPosition.position, 32767).asc(),
            Folder.created_at.asc(),
        )
    )
    results = list(rows)

    # Seed positions on first access: any folder without a row in user_folder_positions
    unseeded = [
        (idx, folder) for idx, (folder, pos) in enumerate(results) if pos is None
    ]
    if unseeded:
        stmt = (
            pg_insert(UserFolderPosition)
            .values(
                [
                    dict(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        folder_id=folder.id,
                        position=idx,
                    )
                    for idx, folder in unseeded
                ]
            )
            .on_conflict_do_nothing(constraint="uq_user_folder_position")
        )
        await db.execute(stmt)
        await db.commit()

    return [
        (folder, pos if pos is not None else idx)
        for idx, (folder, pos) in enumerate(results)
    ]


async def reorder_folders(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_type: FolderType,
    folder_ids: list[uuid.UUID],
) -> list[tuple[Folder, int]]:
    result = await db.scalars(
        select(Folder).where(
            or_(Folder.user_id == user_id, Folder.user_id.is_(None)),
            Folder.type == folder_type,
            Folder.id.in_(folder_ids),
        )
    )
    folders_by_id = {f.id: f for f in result}

    for folder_id in folder_ids:
        if folder_id not in folders_by_id:
            raise FilesError(f"Folder {folder_id} not found")

    existing = await db.scalars(
        select(UserFolderPosition).where(
            UserFolderPosition.user_id == user_id,
            UserFolderPosition.folder_id.in_(folder_ids),
        )
    )
    positions_by_folder = {p.folder_id: p for p in existing}

    for position, folder_id in enumerate(folder_ids):
        if folder_id in positions_by_folder:
            positions_by_folder[folder_id].position = position
        else:
            db.add(
                UserFolderPosition(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    folder_id=folder_id,
                    position=position,
                )
            )

    await db.commit()

    return [(folders_by_id[fid], pos) for pos, fid in enumerate(folder_ids)]


async def get_folder(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> Folder:
    folder = await db.get(Folder, folder_id)
    if not folder or (folder.user_id is not None and folder.user_id != user_id):
        raise FilesError("Folder not found")
    return folder


async def rename_folder(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    name: str,
) -> Folder:
    folder = await get_folder(db, user_id, folder_id)
    folder.name = name
    await db.commit()
    await db.refresh(folder)
    return folder


async def delete_folder(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    s3: S3Client,
) -> None:
    folder = await get_folder(db, user_id, folder_id)
    result = await db.scalars(select(Document).where(Document.folder_id == folder_id))
    documents = list(result)
    keys = list(
        {
            key
            for document in documents
            for key in (document.source_s3_key, document.processed_s3_key)
            if key
        }
    )
    if keys:
        await s3.delete_objects(keys)
    await db.delete(folder)
    await db.commit()


async def initiate_upload(
    db: AsyncSession,
    s3: S3Client,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    *,
    name: str,
    filename: str,
    content_type: str,
    size_bytes: int | None,
) -> tuple[Document, str]:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FilesError(
            f"Unsupported content type {content_type!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    await get_folder(db, user_id, folder_id)

    document = _new_document(
        user_id=user_id,
        folder_id=folder_id,
        name=name,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    upload_url = await s3.presigned_put_url(
        document.source_s3_key,
        content_type=content_type,
        expires_in=_UPLOAD_URL_TTL,
    )
    return document, upload_url


async def upload_document(
    db: AsyncSession,
    s3: S3Client,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    *,
    filename: str,
    content_type: str,
    payload: bytes,
    name: str | None = None,
) -> tuple[Document, ProcessingJob]:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FilesError(
            f"Unsupported content type {content_type!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )
    if not filename:
        raise FilesError("Filename is required")

    await get_folder(db, user_id, folder_id)

    document = _new_document(
        user_id=user_id,
        folder_id=folder_id,
        name=(name or Path(filename).stem).strip(),
        filename=filename,
        content_type=content_type,
        size_bytes=len(payload),
    )
    if not document.name:
        raise FilesError("Document name is required")

    try:
        await s3.upload_bytes(
            document.source_s3_key,
            payload,
            content_type=content_type,
        )
    except Exception as exc:
        raise FilesError("Failed to upload file to object storage") from exc

    job = _new_processing_job(document)
    document.processing_job = job
    db.add(document)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await s3.delete_object(document.source_s3_key)
        raise
    return document, job


async def confirm_upload(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    size_bytes: int | None,
) -> tuple[Document, ProcessingJob]:
    document = await _get_document(db, user_id, document_id)
    if document.processing_job is not None:
        raise FilesError("Processing job already exists for this document")
    if size_bytes is not None:
        document.size_bytes = size_bytes
    job = _new_processing_job(document)
    document.processing_job = job
    await db.commit()
    return document, job


async def list_documents(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> list[Document]:
    await get_folder(db, user_id, folder_id)
    result = await db.scalars(
        select(Document)
        .options(selectinload(Document.processing_job))
        .where(Document.folder_id == folder_id, Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    documents = list(result)
    if _backfill_document_page_counts(documents):
        await db.commit()
    return documents


async def get_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    result = await db.scalars(
        select(Document)
        .options(selectinload(Document.processing_job))
        .where(Document.id == document_id, Document.user_id == user_id)
    )
    document = result.one_or_none()
    if document is None:
        raise FilesError("Document not found")
    if _backfill_document_page_counts([document]):
        await db.commit()
    return document


async def delete_document(
    db: AsyncSession,
    s3: S3Client,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    document = await _get_document(db, user_id, document_id)
    keys = list(
        {key for key in (document.source_s3_key, document.processed_s3_key) if key}
    )
    if keys:
        await s3.delete_objects(keys)
    await db.delete(document)
    await db.commit()


async def get_download_url(
    s3: S3Client,
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    expires_in: int = 3600,
) -> str:
    document = await _get_document(db, user_id, document_id)
    key = document.processed_s3_key or document.source_s3_key
    return await s3.presigned_get_url(
        key,
        expires_in=expires_in,
        filename=document.original_filename,
    )


async def _get_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    result = await db.scalars(
        select(Document)
        .options(selectinload(Document.processing_job))
        .where(Document.id == document_id, Document.user_id == user_id)
    )
    document = result.one_or_none()
    if document is None:
        raise FilesError("Document not found")
    if _backfill_document_page_counts([document]):
        await db.commit()
    return document


def _backfill_document_page_counts(
    documents: list[Document],
) -> bool:
    changed = False
    for document in documents:
        if document.page_count is not None:
            continue
        inferred = infer_page_count(
            document.markdown_content,
            content_type=document.content_type,
        )
        if inferred is None:
            continue
        document.page_count = inferred
        changed = True
    return changed


def _new_document(
    *,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    name: str,
    filename: str,
    content_type: str,
    size_bytes: int | None,
) -> Document:
    document_id = uuid.uuid4()
    ext = Path(filename).suffix or (
        ".pdf" if content_type == "application/pdf" else ".txt"
    )
    return Document(
        id=document_id,
        folder_id=folder_id,
        user_id=user_id,
        name=name,
        original_filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        source_s3_key=f"users/{user_id}/folders/{folder_id}/docs/{document_id}{ext.lower()}",
    )


def _new_processing_job(document: Document) -> ProcessingJob:
    return ProcessingJob(
        document_id=document.id,
        user_id=document.user_id,
        folder_id=document.folder_id,
        status=ProcessingJobStatus.queued,
        source_s3_key=document.source_s3_key,
        processed_s3_key=document.processed_s3_key,
    )
