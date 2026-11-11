"""Truy vấn DB cho `ConsultationSession`, `PreConsultationReport`, `ClinicalFact`."""
from collections import defaultdict
from datetime import UTC, datetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation_session import ConsultationSession
from app.models.conversation import Conversation
from app.models.clinical import (
    ClinicalFact,
    ClinicalProvenance,
    PreConsultationReport,
)
from app.models.message import Message


class ConsultationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_session(self, session: ConsultationSession) -> ConsultationSession:
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_session(self, session_id: str) -> ConsultationSession | None:
        stmt = select(ConsultationSession).where(ConsultationSession.id == session_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self, status: str | None = None, doctor_id: str | None = None
    ) -> list[ConsultationSession]:
        stmt = select(ConsultationSession).order_by(ConsultationSession.requested_at.desc())
        if doctor_id:
            # bác sĩ chỉ thấy ca chờ nhận và ca của chính mình, không thấy ca bác sĩ khác đang phụ trách
            stmt = stmt.where(
                or_(ConsultationSession.status == "pending", ConsultationSession.doctor_id == doctor_id)
            )
        if status and status != "all":
            stmt = stmt.where(ConsultationSession.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_open_session_by_conversation(
        self, conversation_id: str
    ) -> ConsultationSession | None:
        """Mỗi hội thoại tối đa 1 phiên đang mở (status != resolved)."""
        stmt = (
            select(ConsultationSession)
            .where(
                ConsultationSession.conversation_id == conversation_id,
                ConsultationSession.status != "resolved",
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_visible_to_doctor(
        self, conversation_id: str, doctor_id: str
    ) -> ConsultationSession | None:
        """Phiên gần nhất mà bác sĩ được xem: đang chờ nhận hoặc do chính bác sĩ phụ trách."""
        stmt = (
            select(ConsultationSession)
            .where(
                ConsultationSession.conversation_id == conversation_id,
                or_(ConsultationSession.status == "pending", ConsultationSession.doctor_id == doctor_id),
            )
            .order_by(ConsultationSession.requested_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def resolved_marker_time(self, session_id: str) -> datetime | None:
        """Thời điểm tin mốc kết thúc của phiên — tin cuối cùng bác sĩ được thấy."""
        stmt = select(Message.created_at).where(
            Message.consultation_session_id == session_id,
            Message.message_type == "consultation_resolved",
        )
        return (await self._db.execute(stmt)).scalars().first()

    async def conversation_ids(self, session_ids: list[str]) -> dict[str, str]:
        if not session_ids:
            return {}
        stmt = select(ConsultationSession.id, ConsultationSession.conversation_id).where(
            ConsultationSession.id.in_(session_ids)
        )
        return {sid: cid for sid, cid in (await self._db.execute(stmt)).all()}

    async def get_report(self, session_id: str) -> PreConsultationReport | None:
        stmt = select(PreConsultationReport).where(
            PreConsultationReport.consultation_session_id == session_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_past_report(
        self, patient_profile_id: str, exclude_session_id: str | None = None
    ) -> PreConsultationReport | None:
        """Lấy báo cáo tiền tư vấn của ca khám gần nhất trước đó của bệnh nhân."""
        stmt = (
            select(PreConsultationReport)
            .join(
                ConsultationSession,
                PreConsultationReport.consultation_session_id == ConsultationSession.id,
            )
            .join(Conversation, ConsultationSession.conversation_id == Conversation.id)
            .where(Conversation.patient_profile_id == patient_profile_id)
            .order_by(ConsultationSession.requested_at.desc())
        )
        if exclude_session_id:
            stmt = stmt.where(ConsultationSession.id != exclude_session_id)
        result = await self._db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def create_report(
        self, report: PreConsultationReport
    ) -> PreConsultationReport:
        self._db.add(report)
        await self._db.flush()
        return report

    async def list_facts_with_sources(
        self, patient_profile_id: str, newest_first: bool = False
    ) -> list[tuple[ClinicalFact, list[Message]]]:
        """Fact hiện trạng của hồ sơ + tin nhắn nguồn còn tồn tại (cũ trước)."""
        order = ClinicalFact.created_at.desc() if newest_first else ClinicalFact.created_at.asc()
        stmt = select(ClinicalFact).where(ClinicalFact.patient_profile_id == patient_profile_id).order_by(order)
        facts = list((await self._db.execute(stmt)).scalars().all())
        if not facts:
            return []
        prov_stmt = (
            select(ClinicalProvenance.fact_id, Message)
            .join(Message, Message.id == ClinicalProvenance.message_id)
            .where(ClinicalProvenance.fact_id.in_([f.id for f in facts]))
            .order_by(Message.created_at.asc())
        )
        by_fact: dict[str, dict[str, Message]] = defaultdict(dict)
        for fact_id, message in (await self._db.execute(prov_stmt)).all():
            # một tin có thể ghi nhận cùng fact nhiều lần (giá trị khác nhau) nhưng chỉ hiện một lần làm nguồn
            by_fact[fact_id][message.id] = message
        return [(f, list(by_fact[f.id].values())) for f in facts]

    async def accept_session(
        self, session: ConsultationSession, doctor_id: str
    ) -> ConsultationSession:
        session.status = "active"
        session.doctor_id = doctor_id
        session.started_at = datetime.now(UTC)
        await self._db.flush()
        return session

    async def resolve_session(
        self, session: ConsultationSession
    ) -> ConsultationSession:
        session.status = "resolved"
        session.resolved_at = datetime.now(UTC)
        await self._db.flush()
        return session
