import json
import logging
import time
import uuid
from collections.abc import Sequence
from pathlib import PurePosixPath

from aio_pika.abc import AbstractIncomingMessage
from voyageai.client_async import AsyncClient

from src.config import ProcessingSettings, get_settings
from src.core import model_registry  # noqa: F401
from src.core.db import create_engine, create_session_factory
from src.prompts.manager import PromptManager
from src.core.logging import configure_logging
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.core.qdrant import QdrantStore, create_qdrant_client
from src.core.rabbitmq import RabbitMQClient
from src.core.s3 import S3Client
from src.core.voyage import VoyageEmbeddingService
from src.processing.markdown import MistralOCR, collect_markdown
from src.processing.runner import run_pipeline
from src.processing.service import (
    claim_job,
    get_job,
    mark_job_completed,
    mark_job_failed,
)

configure_logging(get_settings())

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Consume processing jobs from RabbitMQ and handle them in parallel."""
    settings = get_settings()
    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)
    prompt_manager = PromptManager(session_factory)
    await prompt_manager.start()
    s3 = S3Client(settings.s3)
    rabbitmq = RabbitMQClient(settings.rabbitmq)
    mistral = MistralOCR(settings.mistral)

    qdrant = QdrantStore(create_qdrant_client(settings.qdrant))
    llm = YandexGPTLLMGateway()

    voyage_client = AsyncClient(api_key=settings.voyage.api_key or None)
    voyage = VoyageEmbeddingService(
        voyage_client, model=settings.voyage.embedding_model
    )

    await s3.open()
    await rabbitmq.open(prefetch_count=settings.processing.max_parallel)

    try:
        await enqueue_backlog_jobs(session_factory, rabbitmq)
        await rabbitmq.consume_jobs(
            lambda message: handle_message(
                message=message,
                session_factory=session_factory,
                s3=s3,
                mistral=mistral,
                processing=settings.processing,
                max_attempts=settings.processing.max_attempts,
                qdrant=qdrant,
                voyage=voyage,
                llm=llm,
                prompt_manager=prompt_manager,
            )
        )
        await wait_forever()
    finally:
        await rabbitmq.close()
        await s3.close()
        await qdrant.close()
        await engine.dispose()


async def handle_message(
    *,
    message: AbstractIncomingMessage,
    session_factory,
    s3: S3Client,
    mistral: MistralOCR,
    processing: ProcessingSettings,
    max_attempts: int,
    qdrant: QdrantStore,
    voyage: VoyageEmbeddingService,
    llm: YandexGPTLLMGateway,
    prompt_manager: PromptManager | None = None,
) -> None:
    """Handle a single RabbitMQ processing job message."""
    started: float | None = None
    document_id: str | None = None
    filename: str | None = None
    try:
        payload = json.loads(message.body.decode())
        job_id = uuid.UUID(payload["job_id"])

        async with session_factory() as session:
            job = await claim_job(session, job_id)
        if job is None:
            await message.ack()
            return

        started = time.perf_counter()
        document_id = str(job.document_id)
        folder_id = str(job.folder_id)
        filename = job.document.original_filename
        content_type = job.document.content_type
        size_bytes = job.document.size_bytes

        download_started = time.perf_counter()
        source_bytes = await s3.download_bytes(job.source_s3_key)
        download_elapsed = time.perf_counter() - download_started

        markdown_started = time.perf_counter()
        markdown = await collect_markdown(
            content_type=job.document.content_type,
            source_bytes=source_bytes,
            mistral=mistral,
            processing=processing,
        )
        markdown_elapsed = time.perf_counter() - markdown_started
        markdown_key = build_markdown_key(job.source_s3_key)
        markdown_store_started = time.perf_counter()
        await s3.upload_bytes(
            markdown_key,
            markdown.encode("utf-8"),
            content_type="text/markdown",
        )
        markdown_store_elapsed = time.perf_counter() - markdown_store_started
        logger.info(
            "Converted %s to markdown (%d chars, %.2fs)",
            job.document.original_filename,
            len(markdown),
            download_elapsed + markdown_elapsed + markdown_store_elapsed,
        )

        pipeline_started = time.perf_counter()
        await run_pipeline(
            markdown=markdown,
            user_id=str(job.user_id),
            folder_id=str(job.folder_id),
            document_id=str(job.document_id),
            qdrant=qdrant,
            voyage=voyage,
            llm=llm,
            session_factory=session_factory,
            job_id=job.id,
            settings=processing,
            prompt_manager=prompt_manager,
        )
        pipeline_elapsed = time.perf_counter() - pipeline_started
        logger.info(
            "Pipeline completed for %s (%.2fs)",
            job.document.original_filename,
            pipeline_elapsed,
        )

        finalize_started = time.perf_counter()
        async with session_factory() as session:
            await mark_job_completed(
                session,
                job.id,
                processed_s3_key=markdown_key,
                markdown_content=markdown,
            )
        finalize_elapsed = time.perf_counter() - finalize_started
        await message.ack()

        logger.info(
            "Document processing summary document_id=%s folder_id=%s filename=%r content_type=%s size_bytes=%s download=%.2fs markdown=%.2fs markdown_store=%.2fs pipeline=%.2fs finalize=%.2fs total=%.2fs",
            document_id,
            folder_id,
            filename,
            content_type,
            size_bytes,
            download_elapsed,
            markdown_elapsed,
            markdown_store_elapsed,
            pipeline_elapsed,
            finalize_elapsed,
            time.perf_counter() - started,
        )
    except Exception as exc:
        logger.exception(
            "Failed to process document_id=%s filename=%r after %.2fs",
            document_id,
            filename,
            (time.perf_counter() - started) if started is not None else 0.0,
        )
        job_id = locals().get("job_id")
        if job_id is None:
            await message.reject(requeue=False)
            return
        async with session_factory() as session:
            current_job = await get_job(session, job_id)
        if current_job is None:
            await message.reject(requeue=False)
            return
        retry = current_job.attempt_count < max_attempts
        async with session_factory() as session:
            await mark_job_failed(session, current_job.id, str(exc), retry=retry)
        if retry:
            await message.reject(requeue=True)
            return
        await message.ack()


async def enqueue_backlog_jobs(
    session_factory,
    rabbitmq: RabbitMQClient,
) -> None:
    """Requeue unfinished jobs when the processing worker starts."""
    async with session_factory() as session:
        jobs = await list_pending_jobs(session)
    for job_id in jobs:
        await rabbitmq.publish_job(job_id)


async def list_pending_jobs(db) -> Sequence[uuid.UUID]:
    """List jobs that should be enqueued on startup."""
    from sqlalchemy import select

    from src.processing.models import ProcessingJob, ProcessingJobStatus

    result = await db.scalars(
        select(ProcessingJob.id).where(
            ProcessingJob.status == ProcessingJobStatus.queued
        )
    )
    return list(result)


async def wait_forever() -> None:
    """Keep the processing worker alive after the consumer is registered."""
    import asyncio

    await asyncio.Future()


def build_markdown_key(source_s3_key: str) -> str:
    """Build the processed markdown object key from the source object key."""
    return str(PurePosixPath(source_s3_key).with_suffix(".md"))
