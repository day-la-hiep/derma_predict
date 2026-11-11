from pydantic import BaseModel

from app.dto.base import VideoCall


class VideoCallOutput(VideoCall):
    id: str
    conversation_id: str
    doctor_id: str  # bên gọi; bệnh nhân (chủ hội thoại) là bên nhận


class IceServer(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class IceConfigOutput(BaseModel):
    ice_servers: list[IceServer]
