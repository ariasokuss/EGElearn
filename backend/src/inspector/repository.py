import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import User
from src.files.models import Document, Folder
from src.processing.models import MegaClusterRecord, ProcessingJob


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_folders(session: AsyncSession, user_id: uuid.UUID) -> list[Folder]:
    result = await session.execute(
        select(Folder)
        .where(Folder.user_id == user_id)
        .order_by(Folder.created_at.desc())
    )
    return list(result.scalars().all())


async def get_folder(
    session: AsyncSession, folder_id: uuid.UUID, user_id: uuid.UUID
) -> Folder | None:
    result = await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    *,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Document]:
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.processing_job))
        .join(Folder, Folder.id == Document.folder_id)
        .where(Document.folder_id == folder_id, Folder.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession,
    *,
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Document | None:
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.processing_job))
        .join(Folder, Folder.id == Document.folder_id)
        .where(
            Document.id == document_id,
            Document.folder_id == folder_id,
            Folder.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_recent_jobs(
    session: AsyncSession, limit: int = 200
) -> list[ProcessingJob]:
    result = await session.execute(
        select(ProcessingJob)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_megaclusters(
    session: AsyncSession,
    *,
    folder_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[MegaClusterRecord]:
    result = await session.execute(
        select(MegaClusterRecord)
        .join(Folder, Folder.id == MegaClusterRecord.folder_id)
        .where(
            MegaClusterRecord.folder_id == folder_id,
            Folder.user_id == user_id,
        )
        .order_by(MegaClusterRecord.created_at.desc(), MegaClusterRecord.id.desc())
    )
    return list(result.scalars().all())
