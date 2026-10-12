"""Truy vấn DB cho `MedicalRecord` (`app/models/medical_record.py`)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical_record import MedicalRecord
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
