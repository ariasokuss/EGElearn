import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy import delete

from src.files.models import Document
from src.processing.markdown import infer_page_count
from src.processing.models import MegaClusterRecord, ProcessingJob, ProcessingJobStatus


async def get_job(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> ProcessingJob | None:
    result = await db.scalars(
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.document))
        .where(ProcessingJob.id == job_id)
    )
    return result.one_or_none()


async def claim_job(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> ProcessingJob | None:
    result = await db.scalars(
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.document))
        .where(ProcessingJob.id == job_id)
        .with_for_update(skip_locked=True)
    )
    job = result.one_or_none()
    if job is None:
        await db.rollback()
        return None
    if job.status not in {ProcessingJobStatus.queued, ProcessingJobStatus.failed}:
        await db.rollback()
        return None

    job.status = ProcessingJobStatus.processing
    job.attempt_count += 1
    job.error_message = None
    job.started_at = datetime.now(UTC)
    job.completed_at = None
    await db.commit()
    return job


async def mark_job_completed(
    db: AsyncSession,
    job_id: uuid.UUID,
    processed_s3_key: str | None = None,
    markdown_content: str | None = None,
) -> None:
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = ProcessingJobStatus.completed
    job.error_message = None
    job.completed_at = datetime.now(UTC)
    if processed_s3_key is not None:
        job.processed_s3_key = processed_s3_key

    document = await db.get(Document, job.document_id)
    if document is not None and processed_s3_key is not None:
        document.processed_s3_key = processed_s3_key
    if document is not None and markdown_content is not None:
        document.markdown_content = markdown_content
        document.page_count = infer_page_count(
            markdown_content,
            content_type=document.content_type,
        )
    await db.commit()


async def mark_job_failed(
    db: AsyncSession,
    job_id: uuid.UUID,
    error_message: str,
    *,
    retry: bool,
) -> None:
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = ProcessingJobStatus.queued if retry else ProcessingJobStatus.failed
    job.error_message = error_message
    if not retry:
        job.completed_at = datetime.now(UTC)
    await db.commit()


async def update_job_status(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: ProcessingJobStatus,
) -> None:
    """Update the processing job to a pipeline sub-stage status."""
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = status
    await db.commit()


async def save_megaclusters(
    db: AsyncSession,
    folder_id: uuid.UUID,
    megaclusters: list[dict],
) -> None:
    """Replace all megaclusters for a folder with the new set.

    Each dict in *megaclusters* should have keys:
    name, description, content_type, document_ids, cluster_uuids.
    """
    await db.execute(
        delete(MegaClusterRecord).where(MegaClusterRecord.folder_id == folder_id)
    )
    for mc in megaclusters:
        distinct_documents = {
            str(document_id).strip()
            for document_id in (mc.get("document_ids") or [])
            if str(document_id).strip()
        }
        cluster_uuids = mc.get("cluster_uuids") or []
        if len(cluster_uuids) > 1 and len(distinct_documents) < 2:
            continue
        db.add(
            MegaClusterRecord(
                folder_id=folder_id,
                name=mc["name"],
                description=mc["description"],
                content_type=mc.get("content_type", "study"),
                document_ids=mc["document_ids"],
                cluster_uuids=cluster_uuids,
            )
        )
    await db.commit()
