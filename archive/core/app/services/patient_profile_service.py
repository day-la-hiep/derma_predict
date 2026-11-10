"""Business logic cho hồ sơ bệnh nhân của một tài khoản và báo cáo kết luận (chỉ đọc) của từng hồ sơ."""

from app.dto.request.patient_profile import CreatePatientProfileInput, UpdatePatientProfileInput
from app.dto.response.patient_profile import PatientFinalizeReportOutput, PatientProfileOutput, ProfileFactOutput
from app.exception.errors import ConflictError, NotFoundError
from app.models.clinical import ClinicalFact
from app.models.patient_profile import PatientProfile
from app.repositories.finalize_report_repository import FinalizeReportRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.clinical_record_service import ClinicalRecordService


def to_output(p: PatientProfile, facts: list[ClinicalFact]) -> PatientProfileOutput:
    return PatientProfileOutput(
        id=p.id,
        full_name=p.full_name,
        dob=p.dob.isoformat(),
        gender=p.gender,
        relationship=p.relationship,
        phone=p.phone,
        created_at=p.created_at.isoformat(),
        long_term_facts=[
            ProfileFactOutput(
                id=f.id,
                fact_type=f.fact_type,
                label=f.label,
                detail=f.detail,
                verified_at=f.verified_at.isoformat() if f.verified_at else None,
            )
            for f in facts
        ],
    )


class PatientProfileService:
    def __init__(
        self, profiles: PatientProfileRepository, reports: FinalizeReportRepository, clinical: ClinicalRecordService
    ) -> None:
        self._profiles = profiles
        self._reports = reports
        self._clinical = clinical
        self._clinical_repo = clinical.repo

    async def _owned(self, user_id: str, profile_id: str) -> PatientProfile:
        profile = await self._profiles.get_for_user(user_id, profile_id)
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân")
        return profile

    async def list_profiles(self, user_id: str) -> list[PatientProfileOutput]:
        profiles = await self._profiles.list_for_user(user_id)
        facts = await self._clinical_repo.long_term_facts([p.id for p in profiles])
        return [to_output(p, facts[p.id]) for p in profiles]

    async def create(self, user_id: str, body: CreatePatientProfileInput) -> PatientProfileOutput:
        fields = body.model_dump(mode="json", exclude={"long_term_facts"})
        profile = await self._profiles.create(PatientProfile(user_id=user_id, **{**fields, "dob": body.dob}))
        return to_output(profile, await self._clinical.replace_long_term_facts(profile.id, body.long_term_facts))

    async def update(self, user_id: str, profile_id: str, body: UpdatePatientProfileInput) -> PatientProfileOutput:
        profile = await self._owned(user_id, profile_id)
        fields = body.model_dump(mode="json", exclude_unset=True, exclude={"long_term_facts"})
        if body.dob is not None:
            fields["dob"] = body.dob
        # `phone` được phép gửi null để xoá; field bắt buộc gửi null thì bỏ qua thay vì ghi NULL vào cột NOT NULL
        fields = {k: v for k, v in fields.items() if v is not None or k == "phone"}
        profile = await self._profiles.update(profile, fields)
        if body.long_term_facts is not None:
            facts = await self._clinical.replace_long_term_facts(profile.id, body.long_term_facts)
        else:
            facts = (await self._clinical_repo.long_term_facts([profile.id]))[profile.id]
        return to_output(profile, facts)

    async def delete(self, user_id: str, profile_id: str) -> None:
        profile = await self._owned(user_id, profile_id)
        if len(await self._profiles.list_for_user(user_id)) <= 1:
            raise ConflictError("Không thể xoá hồ sơ cuối cùng của tài khoản.")
        if await self._profiles.has_linked_data(profile_id):
            raise ConflictError("Hồ sơ đã có hội thoại hoặc báo cáo kết luận nên không thể xoá.")
        await self._profiles.delete(profile)

    async def list_finalize_reports(self, user_id: str, profile_id: str) -> list[PatientFinalizeReportOutput]:
        await self._owned(user_id, profile_id)
        return [
            PatientFinalizeReportOutput(
                id=r.id,
                diagnosis=r.diagnosis,
                notes=r.notes,
                doctor_name=doctor_name,
                created_at=r.created_at.isoformat(),
            )
            for r, doctor_name in await self._reports.list_for_profile(profile_id)
        ]
