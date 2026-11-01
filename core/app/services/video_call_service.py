import base64
import hashlib
import hmac
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constant import MessageSender, MessageType
from app.config.settings import settings
from app.dto.base import VideoCall as VideoCallEntity
from app.dto.response.message import MessageMetadataDto, MessageOutput
from app.dto.response.video_call import IceConfigOutput, IceServer, VideoCallOutput
from app.exception.errors import ConflictError, ForbiddenError, NotFoundError
from app.infra.redis_client import RedisClient
from app.models.consultation_session import ConsultationSession
from app.models.message import Message
from app.models.video_call import VideoCall
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.video_call_repository import VideoCallRepository
from app.services.room_events import publish_room, publish_user_call


def build_ice_config(user_id: str) -> IceConfigOutput:
    servers = [IceServer(urls=settings.STUN_URLS)]
    if settings.TURN_URL:
        # coturn `use-auth-secret`: username = "<hết hạn>:<user>", credential = HMAC-SHA1(secret, username)
        username = f"{int(time.time()) + settings.TURN_CREDENTIAL_TTL_SECONDS}:{user_id}"
        digest = hmac.new(settings.TURN_SECRET.encode(), username.encode(), hashlib.sha1).digest()
        servers.append(
            IceServer(urls=[settings.TURN_URL], username=username, credential=base64.b64encode(digest).decode())
        )
    if settings.METERED_TURN_USERNAME and settings.METERED_TURN_CREDENTIAL:
        host = settings.METERED_TURN_HOST
        # cổng 80/443 + TCP/TLS để vượt firewall chặn UDP
        urls = [
            f"turn:{host}:80",
            f"turn:{host}:80?transport=tcp",
            f"turn:{host}:443",
            f"turns:{host}:443?transport=tcp",
        ]
        servers.append(IceServer(urls=["stun:stun.relay.metered.ca:80"]))
        servers.append(
            IceServer(urls=urls, username=settings.METERED_TURN_USERNAME, credential=settings.METERED_TURN_CREDENTIAL)
        )
    return IceConfigOutput(ice_servers=servers)


class VideoCallService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self._redis = redis
        self._calls = VideoCallRepository(db)
        self._sessions = ConsultationRepository(db)
        self._convs = ConversationRepository(db)
        self._msgs = MessageRepository(db)

    async def _participants(self, session: ConsultationSession) -> tuple[str, str]:
        """(bác sĩ, bệnh nhân) của cuộc gọi — chủ hội thoại là bên nhận."""
        conv = await self._convs.get(session.conversation_id)
        patient_id = await self._convs.owner_user_id(conv) if conv else None
        if session.doctor_id is None or patient_id is None:
            raise ConflictError("Phiên tư vấn chưa có bác sĩ nhận nên chưa gọi được.")
        return session.doctor_id, patient_id

    async def _load(self, call_id: str, user_id: str) -> tuple[VideoCall, ConsultationSession, str, str]:
        call = await self._calls.get(call_id)
        session = await self._sessions.get_session(call.consultation_session_id) if call else None
        if call is None or session is None:
            raise NotFoundError("Không tìm thấy cuộc gọi.")
        doctor_id, patient_id = await self._participants(session)
        if user_id not in (doctor_id, patient_id):
            raise ForbiddenError("Bạn không thuộc cuộc gọi này.")
        return call, session, doctor_id, patient_id

    async def _notify(self, doctor_id: str, patient_id: str, payload: dict[str, Any], only: str | None = None) -> None:
        """Event cuộc gọi đi theo kênh riêng của từng người (không qua room hội thoại) để nhận được ở mọi trang."""
        for user_id in (doctor_id, patient_id):
            if only is None or user_id == only:
                await publish_user_call(self._redis, user_id, payload)

    def _output(self, call: VideoCall, session: ConsultationSession, doctor_id: str) -> VideoCallOutput:
        return VideoCallOutput(
            id=call.id,
            conversation_id=session.conversation_id,
            doctor_id=doctor_id,
            room_id=call.room_id,
            status=call.status,  # pyright: ignore[reportArgumentType]
            started_at=call.started_at,
            ended_at=call.ended_at,
        )

    async def start(self, conversation_id: str, user_id: str, mode: str = "audio") -> VideoCallOutput:
        session = await self._sessions.get_open_session_by_conversation(conversation_id)
        if session is None or session.status != "active":
            raise ConflictError("Chỉ gọi được khi bác sĩ đang tư vấn trong hội thoại này.")
        doctor_id, patient_id = await self._participants(session)
        if user_id != doctor_id:
            raise ForbiddenError("Chỉ bác sĩ phụ trách mới được khởi tạo cuộc gọi.")
        if await self._calls.get_live_by_session(session.id) is not None:
            raise ConflictError("Phiên này đang có một cuộc gọi chưa kết thúc.")

        call = await self._calls.create(
            VideoCall(
                id=f"call-{uuid.uuid4()}",
                consultation_session_id=session.id,
                room_id=f"room-{uuid.uuid4()}",
                status="pending",
            )
        )
        out = self._output(call, session, doctor_id)
        await self._notify(doctor_id, patient_id, {"type": "call.ringing", "mode": mode, "call": out.model_dump(mode="json")})
        return out

    async def accept(self, call_id: str, user_id: str) -> VideoCallOutput:
        call, session, doctor_id, patient_id = await self._load(call_id, user_id)
        if user_id != patient_id:
            raise ForbiddenError("Chỉ bên nhận mới bắt máy được.")
        if call.status != "pending":
            raise ConflictError("Cuộc gọi không còn ở trạng thái chờ bắt máy.")
        call.status = "ongoing"
        call.started_at = datetime.now(UTC)
        out = self._output(call, session, doctor_id)
        await self._post_line(call, session, "Cuộc gọi bắt đầu")
        await self._notify(doctor_id, patient_id, {"type": "call.accepted", "call": out.model_dump(mode="json")})
        return out

    async def end(self, call_id: str, user_id: str, missed: bool = False) -> VideoCallOutput:
        call, session, doctor_id, patient_id = await self._load(call_id, user_id)
        if call.status == "ended":
            return self._output(call, session, doctor_id)  # hai bên cùng bấm kết thúc: lần sau không lỗi

        if call.status == "ongoing":
            reason = "ended"
        elif user_id == patient_id:
            reason = "rejected"
        else:
            reason = "missed" if missed else "cancelled"
        was_started_at = call.started_at
        call.status = "ended"
        call.ended_at = datetime.now(UTC)
        out = self._output(call, session, doctor_id)

        await self._post_line(call, session, self._end_text(call, reason, was_started_at))
        await self._notify(
            doctor_id,
            patient_id,
            {"type": "call.ended", "reason": reason, "ended_by": user_id, "call": out.model_dump(mode="json")},
        )
        return out

    async def signal(self, call_id: str, user_id: str, kind: str, payload: dict[str, Any]) -> None:
        call, _, doctor_id, patient_id = await self._load(call_id, user_id)
        if call.status != "ongoing":
            raise ConflictError("Cuộc gọi chưa bắt đầu hoặc đã kết thúc.")
        peer = patient_id if user_id == doctor_id else doctor_id
        await self._notify(
            doctor_id,
            patient_id,
            {"type": "call.signal", "call_id": call.id, "from": user_id, "kind": kind, "payload": payload},
            only=peer,
        )

    def _end_text(self, call: VideoCall, reason: str, started_at: datetime | None) -> str:
        if reason == "ended" and started_at is not None and call.ended_at:
            seconds = int((call.ended_at - started_at).total_seconds())
            return f"Cuộc gọi kết thúc · {seconds // 60:02d}:{seconds % 60:02d}"
        return {"rejected": "Bệnh nhân đã từ chối cuộc gọi", "cancelled": "Bác sĩ đã huỷ cuộc gọi"}.get(
            reason, "Cuộc gọi nhỡ"
        )

    async def _post_line(self, call: VideoCall, session: ConsultationSession, content: str) -> None:
        # tin hệ thống trong luồng chat; mỗi mốc (bắt đầu, kết thúc) là một tin riêng, không sửa lại sau
        msg = Message(
            id=f"msg-{uuid.uuid4()}",
            conversation_id=session.conversation_id,
            sender=MessageSender.DOCTOR.value,
            message_type=MessageType.VIDEO_CALL.value,
            video_call_id=call.id,
            content=content,
            status="done",
            created_at=datetime.now(UTC),
        )
        await self._msgs.create(msg)
        out = MessageOutput(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender=MessageSender.DOCTOR,
            content=content,
            status="done",
            metadata=MessageMetadataDto(
                message_type=MessageType.VIDEO_CALL,
                video_call=VideoCallEntity(
                    room_id=call.room_id,
                    status=call.status,  # pyright: ignore[reportArgumentType]
                    started_at=call.started_at,
                    ended_at=call.ended_at,
                ),
            ),
            created_at=msg.created_at.isoformat(),
        )
        await publish_room(
            self._redis, msg.conversation_id, {"type": "message.created", "message": out.model_dump(mode="json")}
        )
