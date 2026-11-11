"""Stream Redis Pub/Sub ra SSE dài hạn (không đóng ở `[DONE]`)."""
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from app.infra.redis_client import RedisClient

HEARTBEAT_SECONDS = 15


async def pubsub_event_stream(
    redis: RedisClient,
    channel: str,
    after_subscribe: Callable[[], Awaitable[None]] | None = None,
    stop_after: Callable[[dict[str, object]], bool] | None = None,
) -> AsyncIterator[str]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        # subscribe xong mới chạy hook (vd flush turn đang chờ) để không mất event đầu luồng — Pub/Sub không replay
        if after_subscribe is not None:
            await after_subscribe()
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS)
            if message is None:
                # comment SSE: giữ kết nối qua proxy và giúp server phát hiện client đã rời
                yield ": ping\n\n"
                continue
            yield f"data: {message['data']}\n\n"
            if stop_after is not None:
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                if isinstance(event, dict) and stop_after(event):
                    break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
