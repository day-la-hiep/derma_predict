"""Publish event của hội thoại (room) và của danh sách ca bác sĩ (inbox) lên Redis Pub/Sub."""
import json
import logging
from typing import Any

from app.config.constants import CONVERSATION_ROOM_CHANNEL, DOCTOR_INBOX_CHANNEL
from app.infra.redis_client import RedisClient

logger = logging.getLogger(__name__)


async def _publish(redis: RedisClient, channel: str, payload: dict[str, Any]) -> None:
    # Pub/Sub chỉ là kênh báo realtime — dữ liệu đã ở DB, client refetch được, nên lỗi Redis không làm hỏng nghiệp vụ
    try:
        await redis.publish(channel, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không publish được event lên %s: %s", channel, exc)


async def publish_room(redis: RedisClient, conversation_id: str, payload: dict[str, Any]) -> None:
    await _publish(
        redis,
        CONVERSATION_ROOM_CHANNEL.format(conversation_id=conversation_id),
        {"conversation_id": conversation_id, **payload},
    )


async def publish_inbox(redis: RedisClient, payload: dict[str, Any]) -> None:
    await _publish(redis, DOCTOR_INBOX_CHANNEL, payload)
