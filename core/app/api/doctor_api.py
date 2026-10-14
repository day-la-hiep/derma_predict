"""API endpoints cho Bác sĩ & Báo cáo tư vấn."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    get_consultation_service,
    get_current_user,
    get_doctor_medical_record_service,
    require_role,
)
from app.dto.common import ApiResponse
from app.dto.consultation import (
    ConsultationSessionOutput,
    DoctorReplyInput,
    PatientProfileDto,
    RequestConsultationInput,
)
from app.dto.request.medical_record import CreateDoctorMedicalRecordInput, FinalizeMedicalRecordInput
from app.dto.response.medical_record import (
    DoctorMedicalRecordItemOutput,
    DoctorMedicalRecordOutput,
    FinalizeDraftOutput,
)
from app.dto.response.message import MessageOutput
from app.models.user import User
from app.services.consultation_service import ConsultationService
from app.services.doctor_medical_record_service import DoctorMedicalRecordService

router = APIRouter(tags=["doctor"])

ConsultationServiceDep = Annotated[
    ConsultationService, Depends(get_consultation_service)
]
MedicalRecordServiceDep = Annotated[
    DoctorMedicalRecordService, Depends(get_doctor_medical_record_service)
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
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy phiên tư vấn id={session_id}",
        )
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
    try:
        session = await service.accept_session(session_id, doctor.id)
        return ApiResponse(data=session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    try:
        session = await service.resolve_session(session_id, doctor.id)
        return ApiResponse(data=session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/doctor/consultations/{session_id}/medical-records",
    response_model=ApiResponse[list[DoctorMedicalRecordOutput]],
    operation_id="listSessionMedicalRecords",
)
async def list_session_medical_records(
    session_id: str,
    service: MedicalRecordServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[list[DoctorMedicalRecordOutput]]:
    """Lịch sử bệnh án của bệnh nhân thuộc phiên này (mọi lần khám, không chỉ ca hiện tại)."""
    return ApiResponse(data=await service.list_for_session(session_id, doctor.id))


@router.get(
    "/doctor/consultations/{session_id}/finalize-draft",
    response_model=ApiResponse[FinalizeDraftOutput],
    operation_id="getFinalizeDraft",
)
async def get_finalize_draft(
    session_id: str,
    service: MedicalRecordServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[FinalizeDraftOutput]:
    """Dữ liệu điền sẵn form chốt: hồ sơ bệnh nhân + dữ kiện đang hiệu lực kèm tin nguồn."""
    return ApiResponse(data=await service.draft_for_session(session_id, doctor.id))


@router.post(
    "/doctor/consultations/{session_id}/finalize",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[DoctorMedicalRecordOutput],
    operation_id="finalizeConsultation",
)
async def finalize_consultation(
    session_id: str,
    body: FinalizeMedicalRecordInput,
    service: MedicalRecordServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[DoctorMedicalRecordOutput]:
    """Bác sĩ chốt bệnh án cho ca đang tư vấn và đóng ca."""
    return ApiResponse(data=await service.finalize_session(session_id, doctor.id, doctor.full_name, body))


@router.get(
    "/doctor/medical-records",
    response_model=ApiResponse[list[DoctorMedicalRecordItemOutput]],
    operation_id="listMyMedicalRecords",
)
async def list_my_medical_records(
    service: MedicalRecordServiceDep,
    doctor: DoctorDep,
    q: str = Query(default="", max_length=100),
) -> ApiResponse[list[DoctorMedicalRecordItemOutput]]:
    """Lịch sử khám: các bệnh án do chính bác sĩ đang đăng nhập chốt, lọc theo tên bệnh nhân / chẩn đoán."""
    return ApiResponse(data=await service.list_mine(doctor.id, doctor.full_name, q))


@router.post(
    "/doctor/medical-records",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[DoctorMedicalRecordItemOutput],
    operation_id="createDoctorMedicalRecord",
)
async def create_doctor_medical_record(
    body: CreateDoctorMedicalRecordInput,
    service: MedicalRecordServiceDep,
    doctor: DoctorDep,
) -> ApiResponse[DoctorMedicalRecordItemOutput]:
    """Ghi bệnh án cho ca khám trực tiếp (không qua tư vấn online)."""
    return ApiResponse(data=await service.create(doctor.id, doctor.full_name, body))


@router.get(
    "/doctor/patient-profiles",
    response_model=ApiResponse[list[PatientProfileDto]],
    operation_id="searchPatientProfiles",
)
async def search_patient_profiles(
    service: MedicalRecordServiceDep,
    _doctor: DoctorDep,
    q: str = Query(default="", max_length=100),
) -> ApiResponse[list[PatientProfileDto]]:
    """Tìm hồ sơ bệnh nhân theo tên/SĐT để ghi bệnh án."""
    return ApiResponse(data=await service.search_patients(q))


@router.get(
    "/doctor/patient-profiles/{profile_id}/medical-records",
    response_model=ApiResponse[list[DoctorMedicalRecordOutput]],
    operation_id="listPatientMedicalRecordsForDoctor",
)
async def list_patient_medical_records(
    profile_id: str,
    service: MedicalRecordServiceDep,
    _doctor: DoctorDep,
) -> ApiResponse[list[DoctorMedicalRecordOutput]]:
    """Toàn bộ lịch sử khám của một bệnh nhân (mọi bác sĩ)."""
    return ApiResponse(data=await service.list_for_patient(profile_id))


@router.post(
    "/conversations/{conversation_id}/request-consultation",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="requestConsultation",
)
async def request_consultation(
    conversation_id: str,
    body: RequestConsultationInput,
    service: ConsultationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bệnh nhân yêu cầu kết nối Bác sĩ -> Tự động kích hoạt LLM sinh báo cáo tiền tư vấn AI."""
    session = await service.request_consultation(
        conversation_id, current_user.id, body.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn"
    )
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
    try:
        msg = await service.send_doctor_reply(session_id, body.content, doctor.id)
        return ApiResponse(data=msg)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
