"""Business logic cho hồ sơ bệnh nhân của một tài khoản và bệnh án (chỉ đọc) của từng hồ sơ."""

from app.dto.request.patient_profile import CreatePatientProfileInput, UpdatePatientProfileInput
from app.dto.response.patient_profile import MedicalRecordOutput, PatientProfileOutput
from app.exception.errors import ConflictError, NotFoundError
from app.models.patient_profile import PatientProfile
from app.repositories.medical_record_repository import MedicalRecordRepository
from app.repositories.patient_profile_repository import PatientProfileRepository


def to_output(p: PatientProfile) -> PatientProfileOutput:
    return PatientProfileOutput(
        id=p.id,
        full_name=p.full_name,
        dob=p.dob.isoformat(),
        gender=p.gender,
        relationship=p.relationship,
        phone=p.phone,
        allergies=p.allergies,
        medical_history=p.medical_history,
        created_at=p.created_at.isoformat(),
    )


class PatientProfileService:
    def __init__(self, profiles: PatientProfileRepository, records: MedicalRecordRepository) -> None:
        self._profiles = profiles
        self._records = records

    async def _owned(self, user_id: str, profile_id: str) -> PatientProfile:
        profile = await self._profiles.get_for_user(user_id, profile_id)
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân")
        return profile

    async def list_profiles(self, user_id: str) -> list[PatientProfileOutput]:
        return [to_output(p) for p in await self._profiles.list_for_user(user_id)]

    async def create(self, user_id: str, body: CreatePatientProfileInput) -> PatientProfileOutput:
        profile = PatientProfile(user_id=user_id, **{**body.model_dump(mode="json"), "dob": body.dob})
        return to_output(await self._profiles.create(profile))

    async def update(self, user_id: str, profile_id: str, body: UpdatePatientProfileInput) -> PatientProfileOutput:
        profile = await self._owned(user_id, profile_id)
        fields = body.model_dump(mode="json", exclude_unset=True)
        if body.dob is not None:
            fields["dob"] = body.dob
        # `phone` được phép gửi null để xoá; field bắt buộc gửi null thì bỏ qua thay vì ghi NULL vào cột NOT NULL
        fields = {k: v for k, v in fields.items() if v is not None or k == "phone"}
        return to_output(await self._profiles.update(profile, fields))

    async def delete(self, user_id: str, profile_id: str) -> None:
        profile = await self._owned(user_id, profile_id)
        if len(await self._profiles.list_for_user(user_id)) <= 1:
            raise ConflictError("Không thể xoá hồ sơ cuối cùng của tài khoản.")
        if await self._profiles.has_linked_data(profile_id):
            raise ConflictError("Hồ sơ đã có hội thoại hoặc bệnh án nên không thể xoá.")
        await self._profiles.delete(profile)

    async def list_medical_records(self, user_id: str, profile_id: str) -> list[MedicalRecordOutput]:
        await self._owned(user_id, profile_id)
        return [
            MedicalRecordOutput(
                id=r.id,
                diagnosis=r.diagnosis,
                notes=r.notes,
                doctor_name=doctor_name,
                created_at=r.created_at.isoformat(),
            )
            for r, doctor_name in await self._records.list_for_profile(profile_id)
        ]
