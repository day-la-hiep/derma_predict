"""Nghiệp vụ Tư vấn & Báo cáo tiền tư vấn (Pre-consultation Report Generation)."""
import json
from dataclasses import dataclass
import logging
from typing import Any
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent.dto.schemas import TurnRequest
from app.api.deps import get_rabbitmq_client
from app.common.constant import MessageSender, MessageType
from app.config.constants import AGENT_REQUEST_QUEUE
from app.dto.consultation import (
    ClinicalFactOutput,
    ConsultationSessionOutput,
    PatientProfileDto,
    PreConsultationReportOutput,
)
from app.dto.response.message import MessageMetadataDto, MessageOutput
from app.exception.errors import ConflictError, ForbiddenError, NotFoundError
from app.infra.rabbitmq_client import RabbitMQClient
from app.infra.redis_client import RedisClient
from app.models.clinical import (
    ClinicalFact,
    PreConsultationReport,
)
from app.models.consultation_session import ConsultationSession
from app.models.message import Message
from app.models.user import User
from app.models.patient_profile import PatientProfile
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.doctor_medical_record_service import to_patient_profile_dto
from app.repositories.user_repository import UserRepository
from app.services.patient_graph_service import PatientGraphService
from app.services.room_events import publish_inbox, publish_room

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomAccess:
    is_doctor: bool
    until: datetime | None  # tin sau mốc này bác sĩ không được thấy; None = tới hiện tại
    closed: bool  # phiên của bác sĩ đã kết thúc: không nhận stream live nữa


class ConsultationService:
    def __init__(
        self,
        db: AsyncSession,
        redis: RedisClient,
        rabbitmq: RabbitMQClient | None = None,
        patient_graph_service: PatientGraphService | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._rabbitmq = rabbitmq or get_rabbitmq_client()
        self._patient_graph = patient_graph_service
        self._repo = ConsultationRepository(db)
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)

    def _to_output(
        self,
        session: ConsultationSession,
        conv_title: str = "Hội thoại tư vấn",
        report: PreConsultationReport | None = None,
        facts: list[ClinicalFactOutput] | None = None,
        patient: PatientProfileDto | None = None,
    ) -> ConsultationSessionOutput:
        patient_dto = patient or PatientProfileDto(id="", full_name="Bệnh nhân", dob="", gender="male")

        report_dto = None
        if report:
            report_dto = PreConsultationReportOutput(
                id=report.id,
                summary=report.summary,
                created_at=report.created_at.isoformat(),
            )

        return ConsultationSessionOutput(
            id=session.id,
            conversation_id=session.conversation_id,
            conversation_title=conv_title,
            patient=patient_dto,
            doctor_id=session.doctor_id,
            status=session.status,
            reason=session.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn",
            requested_at=session.requested_at.isoformat(),
            started_at=session.started_at.isoformat() if session.started_at else None,
            resolved_at=session.resolved_at.isoformat() if session.resolved_at else None,
            report=report_dto,
            clinical_facts=facts or [],
        )

    async def _patient_dto(self, patient_profile_id: str | None) -> PatientProfileDto | None:
        profile = await self._db.get(PatientProfile, patient_profile_id) if patient_profile_id else None
        return to_patient_profile_dto(profile) if profile else None

    async def _owned_session(self, session_id: str, doctor_id: str) -> ConsultationSession:
        session = await self._repo.get_session(session_id)
        if session is None:
            raise NotFoundError(f"Không tìm thấy phiên tư vấn id={session_id}")
        if session.doctor_id not in (None, doctor_id):
            raise ForbiddenError("Ca tư vấn này đang do bác sĩ khác phụ trách.")
        return session

    async def _announce(self, output: ConsultationSessionOutput) -> None:
        await publish_room(
            self._redis,
            output.conversation_id,
            {
                "type": "consultation.updated",
                "session_id": output.id,
                "status": output.status,
                "doctor_id": output.doctor_id,
            },
        )
        await publish_inbox(
            self._redis,
            {"type": "consultation.updated", "session": output.model_dump(mode="json")},
        )

    async def announce_finalized(self, session_id: str, doctor_id: str) -> None:
        # chốt bệnh án đã đóng ca ở service khác, nên mốc "kết thúc" và event phải phát ở đây
        session = await self._owned_session(session_id, doctor_id)
        await self._post_marker(session, MessageType.CONSULTATION_RESOLVED, MessageSender.DOCTOR, doctor_id)
        await self._announce(await self.get_session(session_id, doctor_id))

    async def _post_marker(
        self, session: ConsultationSession, message_type: MessageType, sender: MessageSender, actor_id: str
    ) -> Message:
        """Tin mốc đầu/cuối phiên tư vấn: hiện thành đường chia trong luồng chat của cả 3 bên."""
        user = await self._db.get(User, actor_id)
        name = user.full_name if user else "Bác sĩ"
        content = {
            MessageType.CONSULTATION_REQUESTED: "Bạn đã gửi yêu cầu kết nối bác sĩ",
            MessageType.CONSULTATION_ACCEPTED: f"Bác sĩ {name} đã tham gia cuộc trò chuyện",
            MessageType.CONSULTATION_RESOLVED: f"Bác sĩ {name} đã kết thúc phiên tư vấn",
        }[message_type]
        msg = Message(
            id=f"msg-{uuid.uuid4()}",
            conversation_id=session.conversation_id,
            sender=sender.value,
            message_type=message_type.value,
            consultation_session_id=session.id,
            content=content,
            status="done",
            created_at=datetime.now(UTC),
        )
        await self._msg_repo.create(msg)
        out = MessageOutput(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender=sender,
            content=content,
            status="done",
            metadata=MessageMetadataDto(message_type=message_type),
            created_at=msg.created_at.isoformat(),
        )
        await publish_room(
            self._redis,
            msg.conversation_id,
            {"type": "message.created", "message": out.model_dump(mode="json")},
        )
        return msg

    async def room_access(self, conversation_id: str, user_id: str) -> "RoomAccess":
        """Ai được xem hội thoại và tới đâu: chủ hội thoại xem hết; bác sĩ xem từ đầu tới hết phiên gần nhất của mình."""
        conv = await self._conv_repo.get(conversation_id)
        if conv is None:
            raise NotFoundError("Không tìm thấy hội thoại.")
        if await self._conv_repo.owner_user_id(conv) == user_id:
            return RoomAccess(is_doctor=False, until=None, closed=False)
        if await UserRepository(self._db).get_role(user_id) == "doctor":
            session = await self._repo.get_session_visible_to_doctor(conversation_id, user_id)
            if session is not None:
                if session.status != "resolved":
                    return RoomAccess(is_doctor=True, until=None, closed=False)
                until = await self._repo.resolved_marker_time(session.id) or session.resolved_at
                return RoomAccess(is_doctor=True, until=until, closed=True)
        raise ForbiddenError("Bạn không có quyền xem hội thoại này.")

    async def list_sessions(
        self, status: str | None = None, doctor_id: str | None = None
    ) -> list[ConsultationSessionOutput]:
        sessions = await self._repo.list_sessions(status, doctor_id)
        results: list[ConsultationSessionOutput] = []
        for s in sessions:
            conv = await self._conv_repo.get(s.conversation_id)
            title = conv.title if conv else "Hội thoại da liễu"
            report = await self._repo.get_report(s.id)
            facts_dto: list[ClinicalFactOutput] = []
            if conv and conv.patient_profile_id:
                raw_facts = await self._repo.get_clinical_facts_by_patient(conv.patient_profile_id)
                facts_dto = [
                    ClinicalFactOutput(
                        id=f.id,
                        template_label=tpl.label,
                        fact_type=tpl.fact_type,
                        detail=f.detail,
                        status=f.status,
                        created_at=f.created_at.isoformat(),
                    )
                    for f, tpl in raw_facts
                ]
            patient = await self._patient_dto(conv.patient_profile_id if conv else None)
            results.append(self._to_output(s, title, report, facts_dto, patient))
        return results

    async def get_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput:
        session = await self._owned_session(session_id, doctor_id)
        conv = await self._conv_repo.get(session.conversation_id)
        title = conv.title if conv else "Hội thoại da liễu"
        report = await self._repo.get_report(session.id)
        facts_dto: list[ClinicalFactOutput] = []
        if conv and conv.patient_profile_id:
            raw_facts = await self._repo.get_clinical_facts_by_patient(conv.patient_profile_id)
            facts_dto = [
                ClinicalFactOutput(
                    id=f.id,
                    template_label=tpl.label,
                    fact_type=tpl.fact_type,
                    detail=f.detail,
                    status=f.status,
                    created_at=f.created_at.isoformat(),
                )
                for f, tpl in raw_facts
            ]
        patient = await self._patient_dto(conv.patient_profile_id if conv else None)
        return self._to_output(session, title, report, facts_dto, patient)

    async def accept_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput:
        session = await self._owned_session(session_id, doctor_id)
        if session.status == "resolved":
            raise ConflictError("Ca tư vấn đã được đóng.")
        if session.status == "pending":
            session = await self._repo.accept_session(session, doctor_id)
            await self._post_marker(session, MessageType.CONSULTATION_ACCEPTED, MessageSender.DOCTOR, doctor_id)
        out = await self.get_session(session_id, doctor_id)
        await self._announce(out)
        return out

    async def resolve_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput:
        session = await self._owned_session(session_id, doctor_id)
        if session.status != "active":
            raise ConflictError("Chỉ đóng được ca đang tư vấn (bác sĩ cần nhận ca trước).")
        await self._repo.resolve_session(session)
        await self._post_marker(session, MessageType.CONSULTATION_RESOLVED, MessageSender.DOCTOR, doctor_id)
        out = await self.get_session(session_id, doctor_id)
        await self._announce(out)
        return out

    async def request_consultation(self, conversation_id: str, user_id: str, reason: str) -> ConsultationSessionOutput:
        """Kích hoạt tạo phiên tư vấn & gửi task qua RabbitMQ cho Agent Worker sinh báo cáo bất đồng bộ."""
        conv = await self._conv_repo.get(conversation_id)
        if conv is None:
            raise NotFoundError("Không tìm thấy hội thoại.")
        if await self._conv_repo.owner_user_id(conv) != user_id:
            raise ForbiddenError("Bạn chỉ có thể yêu cầu bác sĩ cho hội thoại của chính mình.")
        patient = await self._patient_dto(conv.patient_profile_id)

        # 1. Kiểm tra nếu đã có phiên đang mở thì trả về luôn
        existing = await self._repo.get_open_session_by_conversation(conversation_id)
        conv_title = conv.title
        if existing:
            rep = await self._repo.get_report(existing.id)
            return self._to_output(existing, conv_title, rep, patient=patient)

        # 2. Tạo session mới (trạng thái pending)
        session_id = f"cs-{uuid.uuid4()}"
        session = ConsultationSession(
            id=session_id,
            conversation_id=conversation_id,
            status="pending",
            reason=reason,
            requested_at=datetime.now(UTC),
        )
        await self._repo.create_session(session)
        marker_msg = await self._post_marker(
            session, MessageType.CONSULTATION_REQUESTED, MessageSender.PATIENT, user_id
        )

        # 3. Gửi task sang RabbitMQ để Agent Worker xử lý
        turn_req = TurnRequest(
            type="consultation_report",
            conversation_id=conversation_id,
            message_id=marker_msg.id,
            session_id=session_id,
            patient_profile_id=conv.patient_profile_id,
            reason=reason,
        )
        await self._rabbitmq.publish(
            AGENT_REQUEST_QUEUE,
            turn_req.model_dump_json().encode("utf-8"),
        )

        out = self._to_output(session, conv_title, report=None, facts=[], patient=patient)
        await self._announce(out)
        return out

    async def save_generated_report(
        self,
        session_id: str,
        summary: str,
        facts: list[dict[str, Any]],
        provenance_pairs: list[list[str]],
    ) -> None:
        """Được gọi bởi agent_response_consumer khi Worker sinh xong báo cáo tiền tư vấn."""
        session = await self._repo.get_session(session_id)
        if session is None:
            logger.warning("Không tìm thấy session %s để lưu báo cáo từ worker", session_id)
            return

        conv = await self._conv_repo.get(session.conversation_id)
        patient_profile_id = conv.patient_profile_id if conv else ""

        # 1. Lưu Report
        report = PreConsultationReport(
            id=f"rep-{uuid.uuid4()}",
            consultation_session_id=session_id,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        await self._repo.create_report(report)

        # 2. Lưu Facts
        facts_to_save: list[ClinicalFact] = []
        facts_dto: list[ClinicalFactOutput] = []
        now = datetime.now(UTC)

        for rf in facts:
            f_type = rf.get("fact_type", "symptom")
            f_label = rf.get("template_label", "Dữ kiện lâm sàng")
            f_detail = rf.get("detail", "")
            f_id = rf.get("id") or f"cf-{uuid.uuid4()}"

            tpl = await self._repo.get_or_create_template(f_type, f_label)
            facts_to_save.append(
                ClinicalFact(
                    id=f_id,
                    patient_profile_id=patient_profile_id,
                    template_id=tpl.id,
                    detail=f_detail,
                    status="active",
                    created_at=now,
                )
            )
            facts_dto.append(
                ClinicalFactOutput(
                    id=f_id,
                    template_label=tpl.label,
                    fact_type=tpl.fact_type,
                    detail=f_detail,
                    status="active",
                    created_at=now.isoformat(),
                )
            )

        if facts_to_save:
            await self._repo.add_clinical_facts(facts_to_save)

        # 3. Lưu Provenances
        saved_fact_ids = {f.id for f in facts_to_save}
        valid_pairs = [
            (p[0], p[1])
            for p in provenance_pairs
            if len(p) >= 2 and p[0] in saved_fact_ids
        ]
        if valid_pairs:
            await self._repo.add_provenances(valid_pairs)

        await self._db.commit()

        # 4. Broadcast realtime kết quả qua SSE cho Bác sĩ và Bệnh nhân
        conv_title = conv.title if conv else "Hội thoại tư vấn"
        patient = await self._patient_dto(patient_profile_id)
        out = self._to_output(session, conv_title, report, facts_dto, patient)
        await self._announce(out)
        logger.info("Đã lưu báo cáo tiền tư vấn và phát event cập nhật cho session=%s", session_id)

        # 5. Đồng bộ đồ thị hành trình bệnh nhân (Patient Journey Knowledge Graph) trên Neo4j
        if self._patient_graph and patient_profile_id:
            try:
                await self._patient_graph.sync_pre_consultation(
                    patient_id=patient_profile_id,
                    session_id=session_id,
                    session_date=session.requested_at,
                    summary=summary,
                    reason=session.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn",
                    facts=facts,
                    gender=patient.gender if patient else "unknown",
                    dob=patient.dob if patient else "",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không thể đồng bộ session %s sang Neo4j: %s", session_id, exc)


    async def send_doctor_reply(
        self, session_id: str, content: str, doctor_id: str
    ) -> MessageOutput:
        session = await self._owned_session(session_id, doctor_id)
        if session.status == "resolved":
            raise ConflictError("Ca tư vấn đã đóng, không thể gửi thêm tin nhắn.")

        # Gửi tin cũng là nhận ca (UI báo trước điều này ở nút gửi)
        accepted = session.status == "pending"
        if accepted:
            await self._repo.accept_session(session, doctor_id)
            await self._post_marker(session, MessageType.CONSULTATION_ACCEPTED, MessageSender.DOCTOR, doctor_id)

        msg = Message(
            id=f"msg-{uuid.uuid4()}",
            conversation_id=session.conversation_id,
            sender=MessageSender.DOCTOR.value,
            message_type=MessageType.TEXT.value,
            content=content,
            status="done",
            extra={"doctorId": doctor_id},
            created_at=datetime.now(UTC),
        )
        await self._msg_repo.create(msg)

        out = MessageOutput(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender=MessageSender.DOCTOR,
            content=msg.content,
            status="done",
            created_at=msg.created_at.isoformat(),
        )
        await publish_room(
            self._redis,
            msg.conversation_id,
            {"type": "message.created", "message": out.model_dump(mode="json")},
        )
        if accepted:
            await self._announce(await self.get_session(session_id, doctor_id))
        return out
