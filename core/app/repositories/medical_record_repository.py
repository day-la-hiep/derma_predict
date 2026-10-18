"""Truy vấn DB cho `MedicalRecord` (`app/models/medical_record.py`)."""
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
from app.models.patient_profile import PatientProfile
from app.models.user import User


class MedicalRecordRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_profile(self, profile_id: str) -> list[tuple[MedicalRecord, str | None]]:
        """(bệnh án, tên bác sĩ ghi), mới nhất trước. `doctors.user_id` = `users.id` nên join thẳng `users`."""
        stmt = (
            select(MedicalRecord, User.full_name)
            .outerjoin(User, User.id == MedicalRecord.doctor_id)
            .where(MedicalRecord.patient_profile_id == profile_id)
            .order_by(MedicalRecord.created_at.desc())
        )
        return [(record, name) for record, name in (await self._db.execute(stmt)).all()]

    async def list_for_doctor(self, doctor_id: str, q: str = "") -> list[tuple[MedicalRecord, PatientProfile]]:
        stmt = (
            select(MedicalRecord, PatientProfile)
            .join(PatientProfile, PatientProfile.id == MedicalRecord.patient_profile_id)
            .where(MedicalRecord.doctor_id == doctor_id)
        )
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(MedicalRecord.diagnosis.ilike(pattern), PatientProfile.full_name.ilike(pattern)))
        stmt = stmt.order_by(MedicalRecord.created_at.desc())
        return [(record, profile) for record, profile in (await self._db.execute(stmt)).all()]

    async def create(
        self,
        *,
        patient_profile_id: str,
        doctor_id: str,
        diagnosis: str,
        notes: str,
        is_reference_case: bool,
        consultation_session_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> MedicalRecord:
        record = MedicalRecord(
            patient_profile_id=patient_profile_id,
            doctor_id=doctor_id,
            diagnosis=diagnosis,
            notes=notes,
            is_reference_case=is_reference_case,
            consultation_session_id=consultation_session_id,
            snapshot=snapshot,
        )
        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)
        return record
