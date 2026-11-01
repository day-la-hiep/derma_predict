"""Truy vấn DB cho `FinalizeReport` (`app/models/finalize_report.py`)."""
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.finalize_report import FinalizeReport, PatientImage
from app.models.patient_profile import PatientProfile
from app.models.user import User


class FinalizeReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_profile(self, profile_id: str) -> list[tuple[FinalizeReport, str | None]]:
        """(báo cáo kết luận, tên bác sĩ ghi), mới nhất trước. `doctors.user_id` = `users.id` nên join thẳng `users`."""
        stmt = (
            select(FinalizeReport, User.full_name)
            .outerjoin(User, User.id == FinalizeReport.doctor_id)
            .where(FinalizeReport.patient_profile_id == profile_id)
            .order_by(FinalizeReport.created_at.desc())
        )
        return [(report, name) for report, name in (await self._db.execute(stmt)).all()]

    async def list_for_doctor(self, doctor_id: str, q: str = "") -> list[tuple[FinalizeReport, PatientProfile]]:
        stmt = (
            select(FinalizeReport, PatientProfile)
            .join(PatientProfile, PatientProfile.id == FinalizeReport.patient_profile_id)
            .where(FinalizeReport.doctor_id == doctor_id)
        )
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(FinalizeReport.diagnosis.ilike(pattern), PatientProfile.full_name.ilike(pattern)))
        stmt = stmt.order_by(FinalizeReport.created_at.desc())
        return [(report, profile) for report, profile in (await self._db.execute(stmt)).all()]

    async def create(
        self,
        *,
        patient_profile_id: str,
        doctor_id: str,
        diagnosis: str,
        notes: str,
        is_reference_case: bool,
        consultation_session_id: str,
        snapshot: dict[str, Any] | None = None,
    ) -> FinalizeReport:
        report = FinalizeReport(
            patient_profile_id=patient_profile_id,
            doctor_id=doctor_id,
            diagnosis=diagnosis,
            notes=notes,
            is_reference_case=is_reference_case,
            consultation_session_id=consultation_session_id,
            snapshot=snapshot,
        )
        self._db.add(report)
        await self._db.flush()
        await self._db.refresh(report)
        return report

    async def add_patient_image(
        self,
        *,
        finalize_report_id: str,
        file_id: str,
        body_site: str = "",
        description: str = "",
        confirmed_label: str | None = None,
        captured_at: Any = None,
    ) -> PatientImage:
        image = PatientImage(
            finalize_report_id=finalize_report_id,
            file_id=file_id,
            body_site=body_site,
            description=description,
            confirmed_label=confirmed_label,
            captured_at=captured_at,
        )
        self._db.add(image)
        await self._db.flush()
        await self._db.refresh(image)
        return image

    async def list_images(self, finalize_report_id: str) -> list[tuple[PatientImage, File]]:
        stmt = (
            select(PatientImage, File)
            .join(File, File.id == PatientImage.file_id)
            .where(PatientImage.finalize_report_id == finalize_report_id)
            .order_by(PatientImage.captured_at.asc().nulls_last(), PatientImage.id.asc())
        )
        return [(img, f) for img, f in (await self._db.execute(stmt)).all()]

    async def list_images_for_reports(
        self, report_ids: list[str]
    ) -> dict[str, list[tuple[PatientImage, File]]]:
        if not report_ids:
            return {}
        stmt = (
            select(PatientImage, File)
            .join(File, File.id == PatientImage.file_id)
            .where(PatientImage.finalize_report_id.in_(report_ids))
        )
        out: dict[str, list[tuple[PatientImage, File]]] = {rid: [] for rid in report_ids}
        for img, f in (await self._db.execute(stmt)).all():
            out.setdefault(img.finalize_report_id, []).append((img, f))
        return out
