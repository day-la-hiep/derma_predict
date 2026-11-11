"""Lịch hẹn (bệnh nhân đặt, bác sĩ xác nhận) và lần khám (bác sĩ bắt đầu từ lịch hẹn, rồi chốt kết luận)."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_appointment_service, get_current_user, get_finalize_report_service, require_role
from app.dto.common import ApiResponse
from app.dto.request.appointment import BookAppointmentInput, CancelAppointmentInput, ChangeEpisodeInput
from app.dto.request.finalize_report import FinalizeEncounterInput
from app.dto.response.appointment import (
    AppointmentOutput,
    DoctorAppointmentDetailOutput,
    DoctorAppointmentItemOutput,
    PatientEpisodeOutput,
)
from app.dto.response.finalize_report import EncounterDraftOutput, FinalizeReportOutput
from app.models.user import User
from app.services.appointment_service import AppointmentService
from app.services.finalize_report_service import FinalizeReportService

router = APIRouter(tags=["appointments"])

ServiceDep = Annotated[AppointmentService, Depends(get_appointment_service)]
FinalizeServiceDep = Annotated[FinalizeReportService, Depends(get_finalize_report_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
DoctorDep = Annotated[User, Depends(require_role("doctor"))]


# ---------------------------------------------------------------- bệnh nhân


@router.get(
    "/patient-profiles/{profile_id}/episodes",
    response_model=ApiResponse[list[PatientEpisodeOutput]],
    operation_id="listPatientEpisodes",
)
async def list_episodes(profile_id: str, service: ServiceDep, user: CurrentUserDep) -> ApiResponse[list[PatientEpisodeOutput]]:
    """Các đợt bệnh đang theo dõi của hồ sơ, kèm đợt nào đặt lịch được (không có giả thuyết AI)."""
    return ApiResponse(data=await service.list_episodes(user.id, profile_id))


@router.post(
    "/appointments",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AppointmentOutput],
    operation_id="bookAppointment",
)
async def book_appointment(body: BookAppointmentInput, service: ServiceDep, user: CurrentUserDep) -> ApiResponse[AppointmentOutput]:
    return ApiResponse(data=await service.book(user.id, body))


@router.get("/appointments", response_model=ApiResponse[list[AppointmentOutput]], operation_id="listMyAppointments")
async def list_my_appointments(service: ServiceDep, user: CurrentUserDep) -> ApiResponse[list[AppointmentOutput]]:
    return ApiResponse(data=await service.list_mine(user.id))


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=ApiResponse[AppointmentOutput],
    operation_id="cancelMyAppointment",
)
async def cancel_my_appointment(
    appointment_id: str, body: CancelAppointmentInput, service: ServiceDep, user: CurrentUserDep
) -> ApiResponse[AppointmentOutput]:
    return ApiResponse(data=await service.cancel_mine(user.id, appointment_id, body.reason))


# ---------------------------------------------------------------- bác sĩ


@router.get(
    "/doctor/appointments",
    response_model=ApiResponse[list[DoctorAppointmentItemOutput]],
    operation_id="listDoctorAppointments",
)
async def list_doctor_appointments(
    service: ServiceDep,
    doctor: DoctorDep,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[DoctorAppointmentItemOutput]]:
    """Lịch của bác sĩ trong khoảng [start, end) cùng các lịch đang chờ xác nhận."""
    return ApiResponse(data=await service.list_for_doctor(doctor.id, start, end, status))


@router.get(
    "/doctor/appointments/{appointment_id}",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="getDoctorAppointment",
)
async def get_doctor_appointment(appointment_id: str, service: ServiceDep, doctor: DoctorDep) -> ApiResponse[DoctorAppointmentDetailOutput]:
    """Báo cáo trước khám của đợt: tóm tắt, fact theo đợt, giả thuyết AI (không phải chẩn đoán y khoa)."""
    return ApiResponse(data=await service.detail(doctor.id, appointment_id))


@router.post(
    "/doctor/appointments/{appointment_id}/confirm",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="confirmDoctorAppointment",
)
async def confirm_appointment(appointment_id: str, service: ServiceDep, doctor: DoctorDep) -> ApiResponse[DoctorAppointmentDetailOutput]:
    return ApiResponse(data=await service.confirm(doctor.id, appointment_id))


@router.post(
    "/doctor/appointments/{appointment_id}/cancel",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="cancelDoctorAppointment",
)
async def cancel_appointment(
    appointment_id: str, body: CancelAppointmentInput, service: ServiceDep, doctor: DoctorDep
) -> ApiResponse[DoctorAppointmentDetailOutput]:
    return ApiResponse(data=await service.cancel_by_doctor(doctor.id, appointment_id, body.reason))


@router.post(
    "/doctor/appointments/{appointment_id}/no-show",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="markDoctorAppointmentNoShow",
)
async def mark_no_show(appointment_id: str, service: ServiceDep, doctor: DoctorDep) -> ApiResponse[DoctorAppointmentDetailOutput]:
    return ApiResponse(data=await service.mark_no_show(doctor.id, appointment_id))


@router.post(
    "/doctor/appointments/{appointment_id}/change-episode",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="changeDoctorAppointmentEpisode",
)
async def change_episode(
    appointment_id: str, body: ChangeEpisodeInput, service: ServiceDep, doctor: DoctorDep
) -> ApiResponse[DoctorAppointmentDetailOutput]:
    """Đổi lịch sang đợt bệnh khác của cùng hồ sơ (trước khi bắt đầu khám)."""
    return ApiResponse(data=await service.change_episode(doctor.id, appointment_id, body.episode_id))


@router.post(
    "/doctor/appointments/{appointment_id}/start",
    response_model=ApiResponse[DoctorAppointmentDetailOutput],
    operation_id="startDoctorEncounter",
)
async def start_encounter(appointment_id: str, service: ServiceDep, doctor: DoctorDep) -> ApiResponse[DoctorAppointmentDetailOutput]:
    """Bắt đầu khám: tạo lần khám, đợt chuyển sang in_exam và giả thuyết AI bị khoá."""
    return ApiResponse(data=await service.start_encounter(doctor.id, appointment_id))


@router.get(
    "/doctor/encounters/{encounter_id}/finalize-draft",
    response_model=ApiResponse[EncounterDraftOutput],
    operation_id="getEncounterFinalizeDraft",
)
async def get_encounter_draft(encounter_id: str, service: FinalizeServiceDep, doctor: DoctorDep) -> ApiResponse[EncounterDraftOutput]:
    return ApiResponse(data=await service.draft_for_encounter(encounter_id, doctor.id))


@router.post(
    "/doctor/encounters/{encounter_id}/finalize",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FinalizeReportOutput],
    operation_id="finalizeEncounter",
)
async def finalize_encounter(
    encounter_id: str, body: FinalizeEncounterInput, service: FinalizeServiceDep, doctor: DoctorDep
) -> ApiResponse[FinalizeReportOutput]:
    """Chốt kết luận: ghi fact (đã xác nhận), kết luận, đóng lần khám / lịch hẹn / đợt trong một transaction."""
    return ApiResponse(data=await service.finalize_encounter(encounter_id, doctor.id, doctor.full_name, body))
