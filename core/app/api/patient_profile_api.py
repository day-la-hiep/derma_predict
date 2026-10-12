"""Router hồ sơ bệnh nhân của tài khoản đăng nhập + bệnh án (chỉ đọc) của từng hồ sơ."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_patient_profile_service
from app.dto.common import ApiResponse
from app.dto.request.patient_profile import CreatePatientProfileInput, UpdatePatientProfileInput
from app.dto.response.patient_profile import MedicalRecordOutput, PatientProfileOutput
from app.models.user import User
from app.services.patient_profile_service import PatientProfileService

router = APIRouter(prefix="/patient-profiles", tags=["patient-profiles"])

ServiceDep = Annotated[PatientProfileService, Depends(get_patient_profile_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=ApiResponse[list[PatientProfileOutput]], operation_id="listPatientProfiles")
async def list_profiles(service: ServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[PatientProfileOutput]]:
    return ApiResponse(data=await service.list_profiles(current_user.id))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PatientProfileOutput],
    operation_id="createPatientProfile",
)
async def create_profile(
    body: CreatePatientProfileInput, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[PatientProfileOutput]:
    return ApiResponse(data=await service.create(current_user.id, body))


@router.patch(
    "/{profile_id}", response_model=ApiResponse[PatientProfileOutput], operation_id="updatePatientProfile"
)
async def update_profile(
    profile_id: str, body: UpdatePatientProfileInput, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[PatientProfileOutput]:
    return ApiResponse(data=await service.update(current_user.id, profile_id, body))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deletePatientProfile")
async def delete_profile(profile_id: str, service: ServiceDep, current_user: CurrentUserDep) -> None:
    await service.delete(current_user.id, profile_id)


@router.get(
    "/{profile_id}/medical-records",
    response_model=ApiResponse[list[MedicalRecordOutput]],
    operation_id="listMedicalRecords",
)
async def list_medical_records(
    profile_id: str, service: ServiceDep, current_user: CurrentUserDep
) -> ApiResponse[list[MedicalRecordOutput]]:
    return ApiResponse(data=await service.list_medical_records(current_user.id, profile_id))
