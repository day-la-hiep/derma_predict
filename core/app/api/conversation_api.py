"""Router Conversation + Message — REST (`docs/api-doc.md`) và SSE (`docs/async-api-doc.md`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_consultation_service,
    get_conversation_service,
    get_current_user,
    get_message_service,
    get_rabbitmq_client,
    get_redis_client,
)
from app.config.settings import settings
from app.api.sse import pubsub_event_stream
from app.config.constants import CONVERSATION_ROOM_CHANNEL
from app.dto.common import ApiResponse
from app.exception.errors import ForbiddenError
from app.dto.request.conversation import CreateConversationInput, UpdateConversationModelInput
from app.dto.request.message import MessageAnswerDto, SendMessageInput
from app.dto.response.conversation import ConversationOutput, ModelOption
from app.dto.response.message import MessageOutput, SendMessageResult
from app.infra.rabbitmq_client import RabbitMQClient
from app.models.user import User
from app.infra.redis_client import RedisClient
from app.services.consultation_service import ConsultationService
from app.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
    PatientProfileNotFoundError,
)
from app.services.message_service import (
    AttachmentNotFoundError,
    MessageNotFoundError,
    MessageService,
    TurnInProgressError,
    flush_pending_turn,
)

router = APIRouter(tags=["conversations"])

ConversationServiceDep = Annotated[
    ConversationService, Depends(get_conversation_service)
]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
ConsultationServiceDep = Annotated[ConsultationService, Depends(get_consultation_service)]


@router.get(
    "/models",
    response_model=ApiResponse[list[ModelOption]],
    operation_id="listModelOptions",
)
async def list_model_options() -> ApiResponse[list[ModelOption]]:
    """Danh sách model FE cho user chọn lúc tạo/đổi hội thoại"""
    return ApiResponse(
        data=[
            ModelOption(id=model_id)
            for model_id in settings.AGENT_MODEL_CHOICES
        ]
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationOutput]],
    operation_id="listConversations",
)
async def list_conversations(
    service: ConversationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[list[ConversationOutput]]:
    """`docs/api-doc.md` mục 1.1 — luôn theo tài khoản trong JWT, không nhận `user_id` từ client."""
    conversations = await service.list_conversations(current_user.id)
    return ApiResponse(data=conversations)


@router.post(
    "/conversations",
    status_code=201,
    response_model=ApiResponse[ConversationOutput],
    operation_id="createConversation",
)
async def create_conversation(
    body: CreateConversationInput,
    service: ConversationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[ConversationOutput]:
    """`docs/api-doc.md` mục 1.2 — tạo hội thoại + lưu `content` + publish turn đầu."""
    try:
        # chủ hội thoại luôn là tài khoản đăng nhập, bỏ qua `user_id` client gửi
        conversation = await service.create_conversation(body.model_copy(update={"user_id": current_user.id}))
    except PatientProfileNotFoundError as exc:
        raise HTTPException(
            status_code=400, detail="Không tìm thấy hồ sơ bệnh nhân của tài khoản."
        ) from exc
    return ApiResponse(data=conversation)


@router.patch(
    "/conversations/{conversation_id}/model",
    response_model=ApiResponse[ConversationOutput],
    operation_id="updateConversationModel",
)
async def update_conversation_model(
    conversation_id: str,
    body: UpdateConversationModelInput,
    service: ConversationServiceDep,
) -> ApiResponse[ConversationOutput]:
    """Đổi model cho hội thoại"""
    try:
        conversation = await service.update_model(conversation_id, body.model)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy hội thoại."
        ) from exc
    return ApiResponse(data=conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[list[MessageOutput]],
    operation_id="listMessages",
)
async def list_messages(
    conversation_id: str,
    service: MessageServiceDep,
    current_user: CurrentUserDep,
    consultations: ConsultationServiceDep,
) -> ApiResponse[list[MessageOutput]]:
    """`docs/api-doc.md` mục 1.3 — sắp theo `createdAt` tăng dần; bác sĩ chỉ thấy tới hết phiên gần nhất của mình."""
    access = await consultations.room_access(conversation_id, current_user.id)
    messages = await service.list_messages(conversation_id, access.until)
    return ApiResponse(data=messages)


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=202,
    response_model=ApiResponse[SendMessageResult],
    operation_id="sendMessage",
)
async def send_message(
    conversation_id: str, body: SendMessageInput, service: MessageServiceDep
) -> ApiResponse[SendMessageResult]:
    """`docs/api-doc.md` mục 2.1"""
    try:
        result = await service.send_message(conversation_id, body)
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=400, detail=f"Tệp đính kèm chưa được tải lên: {exc}"
        ) from exc
    except TurnInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail="Trợ lý đang trả lời hoặc đang chờ bạn trả lời câu hỏi, vui lòng đợi.",
        ) from exc
    return ApiResponse(data=result)


@router.post(
    "/conversations/{conversation_id}/questions/{question_id}/answer",
    status_code=202,
    response_model=ApiResponse[MessageOutput],
    operation_id="answerQuestion",
)
async def answer_question(
    conversation_id: str,
    question_id: str,
    body: MessageAnswerDto,
    service: MessageServiceDep,
) -> ApiResponse[MessageOutput]:
    """`docs/api-doc.md` mục 2.2 — trả lời `tool_ask` đang chờ, KHÔNG tạo `messages` mới."""
    try:
        message = await service.answer_question(
            conversation_id, question_id, body
        )
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy câu hỏi đang chờ trả lời."
        ) from exc
    return ApiResponse(data=message)


def _session_resolved(event: dict[str, object]) -> bool:
    return event.get("type") == "consultation.updated" and event.get("status") == "resolved"


@router.get("/conversations/{conversation_id}/stream", include_in_schema=False)
async def stream_conversation(
    conversation_id: str,
    current_user: CurrentUserDep,
    consultations: ConsultationServiceDep,
    redis: Annotated[RedisClient, Depends(get_redis_client)],
    rabbitmq: Annotated[RabbitMQClient, Depends(get_rabbitmq_client)],
) -> StreamingResponse:
    """Room của hội thoại: SSE dài hạn cho bệnh nhân, bác sĩ và agent (`docs/async-api-doc.md` mục 1)"""
    access = await consultations.room_access(conversation_id, current_user.id)
    if access.closed:
        raise ForbiddenError("Phiên tư vấn của bạn với hội thoại này đã kết thúc.")
    channel = CONVERSATION_ROOM_CHANNEL.format(conversation_id=conversation_id)

    async def flush() -> None:
        await flush_pending_turn(conversation_id, redis, rabbitmq)

    return StreamingResponse(
        # phiên kết thúc thì bác sĩ không được nhận thêm gì: đóng stream ngay sau event kết thúc đó
        pubsub_event_stream(
            redis,
            channel,
            flush,
            stop_after=_session_resolved if access.is_doctor else None,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
