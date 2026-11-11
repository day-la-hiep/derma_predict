"""RabbitMQ client dùng chung"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from app.config.settings import settings

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class RabbitMQClient:
    """Instance do `app/api/deps.py` tạo; Core/Worker gọi `connect()` lúc khởi động và `close()` lúc tắt."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.RABBITMQ_URL
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None

    async def connect(self, retries: int = 5, delay: float = 1.5) -> None:
        import asyncio
        import logging

        logger = logging.getLogger(__name__)
        last_err: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                self._connection = await aio_pika.connect_robust(self._url)
                self._channel = await self._connection.channel()
                await self._channel.set_qos(prefetch_count=10)
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < retries:
                    logger.warning(
                        "Kết nối RabbitMQ thất bại (lần %d/%d): %s. Đang thử lại sau %.1fs...",
                        attempt,
                        retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise last_err

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        if self._connection is not None:
            await self._connection.close()

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    @property
    def channel(self) -> AbstractChannel:
        if self._channel is None:
            raise RuntimeError("RabbitMQ chưa connect — gọi connect() trước.")
        return self._channel

    async def declare_queue(
        self, name: str, *, durable: bool = True
    ) -> AbstractQueue:
        return await self.channel.declare_queue(name, durable=durable)

    async def publish(
        self, queue: str, body: bytes, *, persistent: bool = True
    ) -> None:
        """Publish message vào 1 queue (declare queue nếu chưa tồn tại)."""
        await self.declare_queue(queue)
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                delivery_mode=(
                    aio_pika.DeliveryMode.PERSISTENT
                    if persistent
                    else aio_pika.DeliveryMode.NOT_PERSISTENT
                ),
                content_type="application/json",
            ),
            routing_key=queue,
        )

    async def consume(self, queue: str, handler: MessageHandler) -> None:
        """Đăng ký consumer cho 1 queue. handler nên tự `async with message.process()`."""
        q = await self.declare_queue(queue)
        await q.consume(handler)

