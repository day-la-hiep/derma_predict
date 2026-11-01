"""API endpoints cho Bác sĩ & Báo cáo tư vấn."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_consultation_service,
    get_current_user,
    get_finalize_report_service,
    get_patient_graph_service,
    get_redis_client,
    require_role,
)
from app.api.sse import pubsub_event_stream
from app.config.constants import DOCTOR_INBOX_CHANNEL
from app.dto.common import ApiResponse
from app.dto.consultation import (
    ConsultationSessionOutput,
    DoctorReplyInput,
    PatientProfileDto,
    RequestConsultationInput,
)
from app.dto.request.finalize_report import FinalizeReportInput
from app.dto.response.finalize_report import (
    FinalizeReportItemOutput,
    FinalizeReportOutput,
    FinalizeDraftOutput,
)
from app.dto.response.message import MessageOutput
from app.dto.response.patient_graph import PatientJourneyGraphOutput
from app.infra.redis_client import RedisClient
from app.models.user import User
from app.services.consultation_service import ConsultationService
from app.services.finalize_report_service import FinalizeReportService
from app.services.patient_graph_service import PatientGraphService

router = APIRouter(tags=["doctor"])

PatientGraphServiceDep = Annotated[
    PatientGraphService, Depends(get_patient_graph_service)
]

ConsultationServiceDep = Annotated[
    ConsultationService, Depends(get_consultation_service)
]
FinalizeReportServiceDep = Annotated[
    FinalizeReportService, Depends(get_finalize_report_service)
]
DoctorDep = Annotated[User, Depends(require_role("doctor"))]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/doctor/consultations",
    response_model=ApiResponse[list[ConsultationSessionOutput]],
    operation_id="listDoctorConsultations",
)
async def list_consultations(
    service: ConsultationServiceDep,
    doctor: DoctorDep,
    status: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[ConsultationSessionOutput]]:
    """Lấy danh sách các phiên tư vấn cho bác sĩ theo dõi."""
    sessions = await service.list_sessions(status, doctor.id)
    return ApiResponse(data=sessions)


@router.get("/doctor/consultations/stream", include_in_schema=False)
async def stream_consultations(
    doctor: DoctorDep,
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> StreamingResponse:
    """Ca mới / đổi trạng thái theo thời gian thực cho danh sách ca của bác sĩ."""
    return StreamingResponse(
        pubsub_event_stream(redis, DOCTOR_INBOX_CHANNEL),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/doctor/consultations/{session_id}",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="getDoctorConsultation",
)
async def get_consultation(
    session_id: str,
    service: ConsultationServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Lấy chi tiết một phiên tư vấn (kèm dữ kiện lâm sàng và báo cáo AI kết luận)."""
    session = await service.get_session(session_id, doctor.id)
    return ApiResponse(data=session)


@router.post(
    "/doctor/consultations/{session_id}/accept",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="acceptDoctorConsultation",
)
async def accept_consultation(
    session_id: str,
    service: ConsultationServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bác sĩ tiếp quản ca tư vấn (chuyển status sang active)."""
    session = await service.accept_session(session_id, doctor.id)
    return ApiResponse(data=session)


@router.post(
    "/doctor/consultations/{session_id}/resolve",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="resolveDoctorConsultation",
)
async def resolve_consultation(
    session_id: str,
    service: ConsultationServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bác sĩ đóng phiên tư vấn (chuyển status sang resolved)."""
    session = await service.resolve_session(session_id, doctor.id)
    return ApiResponse(data=session)


@router.get(
    "/doctor/consultations/{session_id}/finalize-reports",
    response_model=ApiResponse[list[FinalizeReportOutput]],
    operation_id="listSessionFinalizeReports",
)
async def list_session_finalize_reports(
    session_id: str,
    service: FinalizeReportServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[list[FinalizeReportOutput]]:
    """Lịch sử báo cáo kết luận của bệnh nhân thuộc phiên này (mọi lần khám, không chỉ ca hiện tại)."""
    return ApiResponse(data=await service.list_for_session(session_id, doctor.id))


@router.get(
    "/doctor/consultations/{session_id}/finalize-draft",
    response_model=ApiResponse[FinalizeDraftOutput],
    operation_id="getFinalizeDraft",
)
async def get_finalize_draft(
    session_id: str,
    service: FinalizeReportServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[FinalizeDraftOutput]:
    """Dữ liệu điền sẵn form chốt: hồ sơ bệnh nhân + dữ kiện đang hiệu lực kèm tin nguồn."""
    return ApiResponse(data=await service.draft_for_session(session_id, doctor.id))


@router.post(
    "/doctor/consultations/{session_id}/finalize",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FinalizeReportOutput],
    operation_id="finalizeConsultation",
)
async def finalize_consultation(
    session_id: str,
    body: FinalizeReportInput,
    service: FinalizeReportServiceDep,
    consultations: ConsultationServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[FinalizeReportOutput]:
    """Bác sĩ chốt báo cáo kết luận cho ca đang tư vấn và đóng ca."""
    report = await service.finalize_session(session_id, doctor.id, doctor.full_name, body)
    # chốt báo cáo kết luận đóng ca trong service riêng, nên phải báo room + inbox ở đây
    await consultations.announce_finalized(session_id, doctor.id)
    return ApiResponse(data=report)


@router.get(
    "/doctor/finalize-reports",
    response_model=ApiResponse[list[FinalizeReportItemOutput]],
    operation_id="listMyFinalizeReports",
)
async def list_my_finalize_reports(
    service: FinalizeReportServiceDep,
    doctor: DoctorDep,
    q: str = Query(default="", max_length=100),
) -> ApiResponse[list[FinalizeReportItemOutput]]:
    """Lịch sử khám: các báo cáo kết luận do chính bác sĩ đang đăng nhập chốt, lọc theo tên bệnh nhân / chẩn đoán."""
    return ApiResponse(data=await service.list_mine(doctor.id, doctor.full_name, q))


@router.get(
    "/doctor/patient-profiles/{profile_id}/finalize-reports",
    response_model=ApiResponse[list[FinalizeReportOutput]],
    operation_id="listPatientFinalizeReportsForDoctor",
)
async def list_patient_finalize_reports(
    profile_id: str,
    service: FinalizeReportServiceDep,
    _doctor: DoctorDep,
) -> ApiResponse[list[FinalizeReportOutput]]:
    """Toàn bộ lịch sử khám của một bệnh nhân (mọi bác sĩ)."""
    return ApiResponse(data=await service.list_for_patient(profile_id))


@router.get(
    "/doctor/patient-profiles/{profile_id}/journey-graph",
    response_model=ApiResponse[PatientJourneyGraphOutput],
    operation_id="getPatientJourneyGraph",
)
@router.get(
    "/doctor/patients/{profile_id}/journey-graph",
    response_model=ApiResponse[PatientJourneyGraphOutput],
    operation_id="getPatientJourneyGraphAlias",
    include_in_schema=False,
)
async def get_patient_journey_graph(
    profile_id: str,
    graph_service: PatientGraphServiceDep,
    _doctor: DoctorDep,
) -> ApiResponse[PatientJourneyGraphOutput]:
    """Truy vấn đồ thị hành trình tư vấn của bệnh nhân (PJKG) từ Neo4j."""
    graph = await graph_service.get_patient_journey_graph(profile_id)
    return ApiResponse(data=graph)


@router.post(
    "/conversations/{conversation_id}/request-consultation",
    response_model=ApiResponse[ConsultationSessionOutput],
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="requestConsultation",
)
async def request_consultation(
    conversation_id: str,
    body: RequestConsultationInput,
    service: ConsultationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bệnh nhân yêu cầu kết nối Bác sĩ -> Tự động kích hoạt LLM sinh báo cáo tiền tư vấn AI."""
    session = await service.request_consultation(conversation_id, current_user.id, body.reason)
    return ApiResponse(data=session)


@router.post(
    "/doctor/consultations/{session_id}/reply",
    response_model=ApiResponse[MessageOutput],
    operation_id="replyDoctorConsultation",
)
async def reply_consultation(
    session_id: str,
    body: DoctorReplyInput,
    service: ConsultationServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[MessageOutput]:
    """Bác sĩ gửi tin nhắn phản hồi tới bệnh nhân trong phiên tư vấn."""
    msg = await service.send_doctor_reply(session_id, body.content, doctor.id)
    return ApiResponse(data=msg)
