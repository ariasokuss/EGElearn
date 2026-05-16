import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.config import Settings
from src.core.db import create_engine, create_session_factory
from src.mail.client import MailClient
from src.core.qdrant import QdrantStore
from src.core.rabbitmq import RabbitMQClient
from src.core.s3 import S3Client
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


def _rabbitmq_host_for_log(url: str) -> str:
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        if p.hostname:
            return f"{p.hostname}:{p.port or ''}".rstrip(":")
        return "(parse failed)"
    except Exception:
        return "(parse failed)"


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    s3: S3Client
    rabbitmq: RabbitMQClient
    qdrant: QdrantStore
    prompt_manager: PromptManager
    mail_client: MailClient


async def build_container(settings: Settings) -> AppContainer:
    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)

    s3 = S3Client(settings.s3)
    await s3.open()
    await s3.ensure_bucket()

    rabbitmq = RabbitMQClient(settings.rabbitmq)
    if not settings.rabbitmq.enabled:
        logger.info("RabbitMQ disabled (RABBITMQ__ENABLED=false); AMQP not used")
    elif not (settings.rabbitmq.url or "").strip():
        logger.warning("RabbitMQ URL empty; skipping AMQP connect")
    else:
        try:
            await rabbitmq.open()
            logger.info(
                "RabbitMQ connected queue=%r host=%s",
                settings.rabbitmq.queue_name,
                _rabbitmq_host_for_log(settings.rabbitmq.url),
            )
        except Exception:
            logger.exception(
                "RabbitMQ connect failed; API will run without AMQP until broker is reachable "
                "(file processing jobs and grading queue unavailable)"
            )

    qdrant = await QdrantStore.create(settings.qdrant)
    prompt_manager = PromptManager(session_factory)
    mail_client = MailClient(settings.mail)

    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        s3=s3,
        rabbitmq=rabbitmq,
        qdrant=qdrant,
        prompt_manager=prompt_manager,
        mail_client=mail_client,
    )


async def close_container(container: AppContainer) -> None:
    await container.qdrant.close()
    await container.rabbitmq.close()
    await container.s3.close()
    await container.engine.dispose()
