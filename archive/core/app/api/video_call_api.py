"""API cuộc gọi video: vòng đời cuộc gọi + relay signaling WebRTC qua SSE riêng của từng tài khoản."""
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_redis_client, get_video_call_service
from app.api.sse import pubsub_event_stream
from app.config.constants import USER_CALL_CHANNEL
from app.dto.common import ApiResponse
from app.dto.request.video_call import EndCallInput, SignalInput, StartCallInput
from app.dto.response.video_call import IceConfigOutput, VideoCallOutput
from app.infra.redis_client import RedisClient
from app.models.user import User
from app.services.video_call_service import VideoCallService, build_ice_config

router = APIRouter(tags=["video-call"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
VideoCallServiceDep = Annotated[VideoCallService, Depends(get_video_call_service)]


@router.get("/video-calls/stream", include_in_schema=False)
async def stream_calls(
    user: CurrentUserDep, redis: Annotated[RedisClient, Depends(get_redis_client)]
) -> StreamingResponse:
    """SSE dài hạn của riêng tài khoản: cuộc gọi đến/đổi trạng thái/signaling, nhận được ở mọi trang."""
    return StreamingResponse(
        pubsub_event_stream(redis, USER_CALL_CHANNEL.format(user_id=user.id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/video-calls/ice-config", response_model=ApiResponse[IceConfigOutput], operation_id="getIceConfig")
async def get_ice_config(user: CurrentUserDep) -> ApiResponse[IceConfigOutput]:
    return ApiResponse(data=build_ice_config(user.id))


@router.post(
    "/conversations/{conversation_id}/video-calls",
    response_model=ApiResponse[VideoCallOutput],
    status_code=status.HTTP_201_CREATED,
    operation_id="startVideoCall",
)
async def start_call(
    conversation_id: str, user: CurrentUserDep, service: VideoCallServiceDep, body: StartCallInput | None = None
) -> ApiResponse[VideoCallOutput]:
    return ApiResponse(data=await service.start(conversation_id, user.id, body.mode if body else "audio"))


@router.post(
    "/video-calls/{call_id}/accept", response_model=ApiResponse[VideoCallOutput], operation_id="acceptVideoCall"
)
async def accept_call(call_id: str, user: CurrentUserDep, service: VideoCallServiceDep) -> ApiResponse[VideoCallOutput]:
    return ApiResponse(data=await service.accept(call_id, user.id))


@router.post("/video-calls/{call_id}/end", response_model=ApiResponse[VideoCallOutput], operation_id="endVideoCall")
async def end_call(
    call_id: str, user: CurrentUserDep, service: VideoCallServiceDep, body: EndCallInput | None = None
) -> ApiResponse[VideoCallOutput]:
    return ApiResponse(data=await service.end(call_id, user.id, missed=bool(body and body.reason == "missed")))


@router.post(
    "/video-calls/{call_id}/signal", status_code=status.HTTP_204_NO_CONTENT, operation_id="signalVideoCall"
)
async def signal_call(call_id: str, body: SignalInput, user: CurrentUserDep, service: VideoCallServiceDep) -> None:
    await service.signal(call_id, user.id, body.kind, body.payload)
