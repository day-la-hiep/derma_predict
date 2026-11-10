import unittest
from datetime import UTC, datetime, timedelta

import jwt

import asyncio

from derma_shared.errors import AppError, NotFoundError
from derma_shared.redis_client import RedisClient
from derma_shared.security import decode_token
from derma_shared.settings import settings


class SharedTest(unittest.TestCase):
    def test_decode_token_reads_token_from_identity(self) -> None:
        exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
        token = jwt.encode(
            {"sub": "u1", "role": "admin", "type": "access", "exp": exp},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        self.assertEqual(decode_token(token)["sub"], "u1")

    def test_decode_token_rejects_wrong_key(self) -> None:
        token = jwt.encode({"sub": "u1"}, "khoa-khac-khoa-khac-khoa-khac-32b", algorithm="HS256")
        with self.assertRaises(jwt.PyJWTError):
            decode_token(token)

    def test_not_found_is_app_error(self) -> None:
        self.assertEqual(NotFoundError.status_code, 404)
        self.assertTrue(issubclass(NotFoundError, AppError))

    def test_add_stream_event_caps_length_and_sets_expiry(self) -> None:
        calls: list[tuple] = []

        class FakeRedis:
            async def xadd(self, stream: str, fields: dict, **kwargs: object) -> str:
                calls.append(("xadd", stream, fields, kwargs))
                return "1-0"

            async def expire(self, stream: str, seconds: int) -> None:
                calls.append(("expire", stream, seconds))

        client = RedisClient("localhost", 6379)
        client._async = FakeRedis()  # type: ignore[assignment]
        entry_id = asyncio.run(client.add_stream_event("conversation:events:c1", '{"type": "message.done"}', maxlen=10, ttl_seconds=60))
        self.assertEqual(entry_id, "1-0")
        self.assertEqual(calls[0], ("xadd", "conversation:events:c1", {"event": '{"type": "message.done"}'}, {"maxlen": 10, "approximate": True}))
        self.assertEqual(calls[1], ("expire", "conversation:events:c1", 60))


if __name__ == "__main__":
    unittest.main()
