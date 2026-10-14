"""Truy vấn DB cho `PatientProfile` (`app/models/patient_profile.py`)."""
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.medical_record import MedicalRecord
from app.models.patient_profile import PatientProfile


class PatientProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def first_for_user(self, user_id: str) -> PatientProfile | None:
        """Hồ sơ tạo sớm nhất của tài khoản — dùng làm hồ sơ mặc định khi client không chọn hồ sơ."""
        stmt = (
            select(PatientProfile)
            .where(PatientProfile.user_id == user_id)
            .order_by(PatientProfile.created_at.asc())
            .limit(1)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: str) -> list[PatientProfile]:
        stmt = select(PatientProfile).where(PatientProfile.user_id == user_id).order_by(PatientProfile.created_at.asc())
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_for_user(self, user_id: str, profile_id: str) -> PatientProfile | None:
        """Lọc theo chủ tài khoản: hồ sơ của người khác coi như không tồn tại."""
        stmt = select(PatientProfile).where(PatientProfile.id == profile_id, PatientProfile.user_id == user_id)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get(self, profile_id: str) -> PatientProfile | None:
        return await self._db.get(PatientProfile, profile_id)

    async def search(self, q: str, limit: int = 20) -> list[PatientProfile]:
        """Bác sĩ tìm hồ sơ theo tên/SĐT; q rỗng trả các hồ sơ mới nhất để có gợi ý ngay khi mở ô chọn."""
        stmt = select(PatientProfile)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(PatientProfile.full_name.ilike(pattern), PatientProfile.phone.ilike(pattern)))
        stmt = stmt.order_by(PatientProfile.created_at.desc()).limit(limit)
        return list((await self._db.execute(stmt)).scalars().all())

    async def create(self, profile: PatientProfile) -> PatientProfile:
        """Tạo mới một hồ sơ bệnh nhân (flush để sinh id/giá trị mặc định)."""
        self._db.add(profile)
        await self._db.flush()
        await self._db.refresh(profile)
        return profile

    async def update(self, profile: PatientProfile, fields: dict[str, Any]) -> PatientProfile:
        for name, value in fields.items():
            setattr(profile, name, value)
        await self._db.flush()
        return profile

    async def delete(self, profile: PatientProfile) -> None:
        await self._db.delete(profile)
        await self._db.flush()

    async def has_linked_data(self, profile_id: str) -> bool:
        """Có hội thoại hoặc bệnh án trỏ tới — xoá sẽ mất dữ liệu y khoa (và `conversations` không cascade)."""
        stmt = select(
            exists().where(Conversation.patient_profile_id == profile_id)
            | exists().where(MedicalRecord.patient_profile_id == profile_id)
        )
        return bool((await self._db.execute(stmt)).scalar())
