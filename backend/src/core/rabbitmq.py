import json
import uuid
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from src.config import RabbitMQSettings


class RabbitMQNotConnectedError(RuntimeError):
    """Publish/consume requested while AMQP is down or was disabled at startup."""


class RabbitMQClient:
    """Publish and consume processing jobs through a single durable queue."""

    def __init__(self, settings: RabbitMQSettings) -> None:
        self._settings = settings
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None

    @property
    def is_connected(self) -> bool:
        return self._channel is not None

    async def open(self, *, prefetch_count: int | None = None) -> None:
        """Open the connection, channel, and queue."""
        self._connection = await aio_pika.connect_robust(self._settings.url)
        self._channel = await self._connection.channel()
        if prefetch_count is not None:
            await self._channel.set_qos(prefetch_count=prefetch_count)
        self._queue = await self._channel.declare_queue(
            self._settings.queue_name,
            durable=True,
        )

    async def close(self) -> None:
        """Close the connection if it was opened."""
        if self._connection is not None:
            await self._connection.close()

    async def publish_job(self, job_id: uuid.UUID) -> None:
        """Publish a processing job id to the durable queue."""
        if self._channel is None:
            raise RabbitMQNotConnectedError(
                "RabbitMQ is not connected; cannot enqueue processing job"
            )
        message = aio_pika.Message(
            body=json.dumps({"job_id": str(job_id)}).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._channel.default_exchange.publish(
            message,
            routing_key=self._settings.queue_name,
        )

    async def consume_jobs(
        self,
        handler: Callable[[AbstractIncomingMessage], Awaitable[None]],
    ) -> None:
        """Start consuming jobs with the provided async handler."""
        if self._queue is None:
            raise RabbitMQNotConnectedError(
                "RabbitMQ is not connected; cannot consume processing jobs"
            )
        await self._queue.consume(handler)
