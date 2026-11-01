from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video_call import VideoCall


class VideoCallRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, call: VideoCall) -> VideoCall:
        self._db.add(call)
        await self._db.flush()
        return call

    async def get(self, call_id: str) -> VideoCall | None:
        return await self._db.get(VideoCall, call_id)

    async def get_live_by_session(self, session_id: str) -> VideoCall | None:
        """Cuộc gọi chưa kết thúc (đang đổ chuông hoặc đang nói) của phiên."""
        stmt = select(VideoCall).where(
            VideoCall.consultation_session_id == session_id, VideoCall.status != "ended"
        )
        return (await self._db.scalars(stmt)).first()
