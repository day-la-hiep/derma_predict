import json
import unittest
from types import SimpleNamespace

from app.exception.errors import ConflictError, ForbiddenError
from app.services.video_call_service import VideoCallService, build_ice_config


class FakeRedis:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.channels: list[str] = []

    async def publish(self, channel: str, data: str) -> None:
        self.events.append(json.loads(data))
        self.channels.append(channel)


class FakeCalls:
    def __init__(self) -> None:
        self.rows: dict = {}

    async def create(self, call):
        self.rows[call.id] = call
        return call

    async def get(self, call_id):
        return self.rows.get(call_id)

    async def get_live_by_session(self, _session_id):
        return next((c for c in self.rows.values() if c.status != "ended"), None)


class FakeMsgs:
    def __init__(self) -> None:
        self.rows: list = []

    async def create(self, msg):
        self.rows.append(msg)
        return msg


def make_service() -> tuple[VideoCallService, FakeRedis]:
    session = SimpleNamespace(id="sess", conversation_id="conv", doctor_id="doc", status="active")

    class Sessions:
        async def get_open_session_by_conversation(self, _cid):
            return session

        async def get_session(self, _sid):
            return session

    class Convs:
        async def get(self, _cid):
            return SimpleNamespace(id="conv")

        async def owner_user_id(self, _conv):
            return "pat"

    redis = FakeRedis()
    svc = VideoCallService(None, redis)  # pyright: ignore[reportArgumentType]
    svc._calls = FakeCalls()  # pyright: ignore[reportAttributeAccessIssue]
    svc._sessions = Sessions()  # pyright: ignore[reportAttributeAccessIssue]
    svc._convs = Convs()  # pyright: ignore[reportAttributeAccessIssue]
    svc._msgs = FakeMsgs()  # pyright: ignore[reportAttributeAccessIssue]
    return svc, redis


class VideoCallServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_full_call(self) -> None:
        svc, redis = make_service()
        call = await svc.start("conv", "doc", "video")
        self.assertEqual(call.status, "pending")
        self.assertEqual(redis.events[-1]["type"], "call.ringing")
        self.assertEqual(redis.events[-1]["mode"], "video")

        with self.assertRaises(ConflictError):
            await svc.start("conv", "doc")
        with self.assertRaises(ForbiddenError):
            await svc.accept(call.id, "doc")
        with self.assertRaises(ConflictError):  # chưa bắt máy thì chưa relay signaling
            await svc.signal(call.id, "doc", "offer", {})

        await svc.accept(call.id, "pat")
        await svc.signal(call.id, "doc", "offer", {"sdp": "x"})
        self.assertEqual(redis.events[-1]["type"], "call.signal")
        self.assertEqual(redis.channels[-1], "user:calls:pat")  # signal chỉ tới bên kia, không dội lại người gửi
        with self.assertRaises(ForbiddenError):
            await svc.signal(call.id, "other", "offer", {})

        ended = await svc.end(call.id, "pat")
        self.assertEqual(ended.status, "ended")
        self.assertEqual(redis.events[-1]["type"], "call.ended")
        lines = [e["message"]["content"] for e in redis.events if e["type"] == "message.created"]
        self.assertEqual(lines[0], "Cuộc gọi bắt đầu")
        self.assertTrue(lines[1].startswith("Cuộc gọi kết thúc · "))
        self.assertEqual(redis.events[-1]["reason"], "ended")
        await svc.end(call.id, "doc")  # kết thúc lần 2 không lỗi

    async def test_reject_and_cancel(self) -> None:
        svc, redis = make_service()
        call = await svc.start("conv", "doc")
        await svc.end(call.id, "pat")
        self.assertEqual(redis.events[-1]["reason"], "rejected")
        call = await svc.start("conv", "doc")
        await svc.end(call.id, "doc", missed=True)
        self.assertEqual(redis.events[-1]["reason"], "missed")

    async def test_patient_cannot_start(self) -> None:
        svc, _ = make_service()
        with self.assertRaises(ForbiddenError):
            await svc.start("conv", "pat")


class IceConfigTest(unittest.TestCase):
    def test_turn_credential_only_when_configured(self) -> None:
        from app.config.settings import settings

        old = (settings.TURN_URL, settings.METERED_TURN_USERNAME)
        try:
            settings.TURN_URL, settings.METERED_TURN_USERNAME = "", ""
            self.assertEqual(len(build_ice_config("u").ice_servers), 1)
            settings.TURN_URL = "turn:localhost:3478"
            turn = build_ice_config("u").ice_servers[1]
            self.assertTrue(turn.username and turn.username.endswith(":u") and turn.credential)
            settings.TURN_URL, settings.METERED_TURN_USERNAME = "", "user"
            settings.METERED_TURN_CREDENTIAL = "pw"
            self.assertTrue(any(s.username == "user" for s in build_ice_config("u").ice_servers))
        finally:
            settings.TURN_URL, settings.METERED_TURN_USERNAME = old
            settings.METERED_TURN_CREDENTIAL = ""


if __name__ == "__main__":
    unittest.main()
