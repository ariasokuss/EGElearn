"""Async grading worker for short-answer test questions.

Publishes grading jobs to a dedicated RabbitMQ queue and consumes them
in a background task. Now operates on session_id instead of test_id.
"""

from __future__ import annotations

import json
import logging
import uuid

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from src.learning.tests.session_service import TestSessionService

logger = logging.getLogger(__name__)

GRADING_QUEUE = "test_grading_jobs"


async def publish_grading_job(container, session_id: uuid.UUID) -> bool:
    """Publish a session grading job to the RabbitMQ grading queue."""
    rmq = container.rabbitmq
    if rmq._channel is None:
        logger.error("RabbitMQ channel not available for grading job")
        return False

    try:
        await rmq._channel.declare_queue(GRADING_QUEUE, durable=True)
        message = aio_pika.Message(
            body=json.dumps({"session_id": str(session_id)}).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await rmq._channel.default_exchange.publish(message, routing_key=GRADING_QUEUE)
        logger.info("Published grading job for session %s", session_id)
        return True
    except Exception:
        logger.exception("Failed to publish grading job for session %s", session_id)
        return False


async def start_grading_consumer(container) -> None:
    """Start consuming grading jobs in the background."""
    rmq = container.rabbitmq
    if rmq._channel is None:
        logger.warning("RabbitMQ not available — grading consumer not started")
        return

    await rmq._channel.set_qos(prefetch_count=1)
    queue = await rmq._channel.declare_queue(GRADING_QUEUE, durable=True)

    service = TestSessionService(session_factory=container.session_factory)

    async def _handle(message: AbstractIncomingMessage) -> None:
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                session_id = uuid.UUID(data["session_id"])
                logger.info("Grading session %s", session_id)
                await service.grade_session(session_id)
                logger.info("Finished grading session %s", session_id)
            except Exception:
                logger.exception("Failed to grade session")

    await queue.consume(_handle)
    logger.info("Grading consumer started on queue %r", GRADING_QUEUE)
