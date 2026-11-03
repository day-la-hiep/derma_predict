"""Truy vấn DB cho `Appointment` / `Encounter` (`app/models/visit.py`)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.episode import ClinicalEpisode
from app.models.patient_profile import PatientProfile
from app.models.visit import Appointment, Encounter

ACTIVE_STATUSES = ("requested", "confirmed", "in_progress")


class AppointmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, appointment_id: str) -> Appointment | None:
        return await self._db.get(Appointment, appointment_id)

    async def active_for_episodes(self, episode_ids: list[str]) -> dict[str, Appointment]:
        if not episode_ids:
            return {}
        stmt = select(Appointment).where(Appointment.episode_id.in_(episode_ids), Appointment.status.in_(ACTIVE_STATUSES))
        return {a.episode_id: a for a in (await self._db.execute(stmt)).scalars().all()}

    async def list_for_profiles(self, profile_ids: list[str]) -> list[tuple[Appointment, ClinicalEpisode]]:
        if not profile_ids:
            return []
        stmt = (
            select(Appointment, ClinicalEpisode)
            .join(ClinicalEpisode, ClinicalEpisode.id == Appointment.episode_id)
            .where(Appointment.patient_profile_id.in_(profile_ids))
            .order_by(Appointment.scheduled_at.desc())
        )
        return [(a, e) for a, e in (await self._db.execute(stmt)).all()]

    async def list_for_doctor(
        self, doctor_id: str, start: datetime | None, end: datetime | None, status: str | None
    ) -> list[tuple[Appointment, ClinicalEpisode, PatientProfile]]:
        """Lịch của bác sĩ + lịch `requested` chưa ai nhận (mọi bác sĩ đều thấy để xác nhận)."""
        stmt = (
            select(Appointment, ClinicalEpisode, PatientProfile)
            .join(ClinicalEpisode, ClinicalEpisode.id == Appointment.episode_id)
            .join(PatientProfile, PatientProfile.id == Appointment.patient_profile_id)
            .where((Appointment.doctor_id == doctor_id) | (Appointment.doctor_id.is_(None) & (Appointment.status == "requested")))
        )
        if start:
            stmt = stmt.where(Appointment.scheduled_at >= start)
        if end:
            stmt = stmt.where(Appointment.scheduled_at < end)
        if status:
            stmt = stmt.where(Appointment.status == status)
        stmt = stmt.order_by(Appointment.scheduled_at.asc())
        return [(a, e, p) for a, e, p in (await self._db.execute(stmt)).all()]

    async def add(self, appointment: Appointment) -> Appointment:
        self._db.add(appointment)
        await self._db.flush()
        return appointment

    async def encounter_of(self, appointment_id: str) -> Encounter | None:
        stmt = select(Encounter).where(Encounter.appointment_id == appointment_id)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def get_encounter(self, encounter_id: str) -> Encounter | None:
        return await self._db.get(Encounter, encounter_id)

    async def add_encounter(self, encounter: Encounter) -> Encounter:
        self._db.add(encounter)
        await self._db.flush()
        return encounter

    async def flush(self) -> None:
        await self._db.flush()
