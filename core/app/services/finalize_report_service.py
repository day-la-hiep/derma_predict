import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from datetime import UTC, datetime

from app.common.constant import (
    DIAGNOSIS_CODE_LABELS,
    LONG_TERM_FACT_TYPES,
    AppointmentStatus,
    ClinicalFactType,
    EncounterStatus,
    EpisodeStatus,
    FactOrigin,
    Gender,
    MessageSender,
    ProfileRelationship,
    ProvenanceKind,
)
from app.dto.base import (
    Assessment,
    File as FileEntity,
    FinalizeReportSnapshot,
    PatientImage as PatientImageEntity,
    SnapshotClinicalFact,
    SnapshotMessage,
    SnapshotPatientProfile,
    SnapshotProvenance,
)
from app.dto.common import FileDto
from app.dto.request.finalize_report import FactInput, FinalizeEncounterInput, FinalizeReportInput, PatientImageInput
from app.dto.response.finalize_report import (
    FinalizeReportItemOutput,
    FinalizeReportOutput,
    DraftFactOutput,
    DiagnosisOptionOutput,
    EncounterDraftOutput,
    FinalizeDraftOutput,
    GraphSuggestionOutput,
    FinalizeReportSnapshotOutput,
    PatientImageOutput,
    SnapshotClinicalFactOutput,
    SnapshotMessageOutput,
    SnapshotProvenanceOutput,
)
from app.exception.errors import ConflictError, ForbiddenError, InvalidError, NotFoundError
from app.models.clinical import ClinicalFact, ClinicalProvenance
from app.models.consultation_session import ConsultationSession
from app.models.file import File
from app.models.finalize_report import FinalizeReport
from app.models.message import Message
from app.models.patient_profile import PatientProfile
from app.models.visit import Appointment
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.clinical_record_repository import ClinicalRecordRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.file_repository import FileRepository
from app.repositories.finalize_report_repository import FinalizeReportRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.appointment_service import AppointmentService
from app.services.clinical_record_service import to_patient_profile_dto
from app.services.file_store_service import FileStoreService

logger = logging.getLogger(__name__)

FactRow = tuple[ClinicalFact, list[Message]]


def _candidate_names(texts: list[str]) -> list[str]:
    """Tách tên bệnh từ câu 'Bệnh ứng viên theo đồ thị tri thức: <tên> (điểm ...'."""
    return [t.split(": ", 1)[-1].split(" (điểm", 1)[0] for t in texts]


def default_origin(fact_type: str) -> FactOrigin:
    """Fact trích từ hội thoại: kết quả phân loại ảnh là AI suy ra, còn lại là bệnh nhân khai."""
    return FactOrigin.AI_INFERRED if fact_type == ClinicalFactType.IMAGE_FINDING else FactOrigin.PATIENT_REPORTED


def _snapshot_provenances(messages: list[Message], files: dict[str, list[File]]) -> list[SnapshotProvenance]:
    return [
        SnapshotProvenance(
            message=SnapshotMessage(
                id=m.id,
                sender=MessageSender(m.sender),
                content=m.content,
                created_at=m.created_at,
                files=[
                    FileEntity(file_name=f.file_name, storage_key=f.storage_key, content_type=f.content_type)
                    for f in files.get(m.id, [])
                ],
            )
        )
        for m in messages
    ]


def _fact_line(f: SnapshotClinicalFact) -> str:
    return f"{f.label} ({f.detail})" if f.detail else f.label


def build_snapshot(
    profile: PatientProfile,
    body: FinalizeReportInput,
    source_facts: dict[str, FactRow],
    files: dict[str, list[File]],
    removed: list[FactRow] | None = None,
) -> FinalizeReportSnapshot:
    """Chép mọi thứ cần hiển thị phiếu vào một bản bất biến; nguồn của fact lấy từ DB, không tin nội dung client gửi."""
    facts: list[SnapshotClinicalFact] = []
    for f in body.facts:
        source = source_facts.get(f.source_fact_id) if f.source_fact_id else None
        if f.source_fact_id and source is None:
            raise InvalidError("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc bệnh nhân này, hãy tải lại form.")
        if source is None:
            origin, provenances = FactOrigin.DOCTOR_OBSERVED, []
        else:
            fact, messages = source
            unchanged = (f.label.strip(), f.detail.strip(), f.fact_type.value) == (fact.label, fact.detail, fact.fact_type)
            origin = default_origin(fact.fact_type) if unchanged else FactOrigin.DOCTOR_CORRECTED
            provenances = _snapshot_provenances(messages, files)
        facts.append(
            SnapshotClinicalFact(
                fact_type=f.fact_type, label=f.label.strip(), detail=f.detail.strip(), origin=origin, provenances=provenances
            )
        )
    return FinalizeReportSnapshot(
        patient_profile=SnapshotPatientProfile(
            full_name=profile.full_name,
            dob=profile.dob,
            gender=Gender(profile.gender),
            relationship=ProfileRelationship(profile.relationship),
            phone=profile.phone,
            # chuỗi cho phiếu / payload Qdrant: lấy từ fact bác sĩ đã chốt, không đọc lại DB
            allergies="; ".join(_fact_line(f) for f in facts if f.fact_type == ClinicalFactType.ALLERGY),
            medical_history="; ".join(_fact_line(f) for f in facts if f.fact_type == ClinicalFactType.HISTORY),
        ),
        assessment=Assessment(
            reasoning=body.reasoning.strip(),
            urgency=body.urgency,
            instructions=[i.strip() for i in body.instructions if i.strip()],
        ),
        clinical_facts=facts,
        removed_facts=[
            SnapshotClinicalFact(
                fact_type=ClinicalFactType(fact.fact_type),
                label=fact.label,
                detail=fact.detail,
                origin=default_origin(fact.fact_type),
                provenances=_snapshot_provenances(messages, files),
            )
            for fact, messages in (removed or [])
        ],
    )


from app.services.finalize_report_index_service import FinalizeReportIndexService
from app.services.patient_graph_service import PatientGraphService


class FinalizeReportService:
    def __init__(
        self,
        db: AsyncSession,
        file_store: FileStoreService,
        index_service: FinalizeReportIndexService | None = None,
        patient_graph_service: PatientGraphService | None = None,
    ) -> None:
        self._db = db
        self._reports = FinalizeReportRepository(db)
        self._appointments = AppointmentRepository(db)
        self._profiles = PatientProfileRepository(db)
        self._consultations = ConsultationRepository(db)
        self._conversations = ConversationRepository(db)
        self._files = FileRepository(db)
        self._clinical = ClinicalRecordRepository(db)
        self._file_store = file_store
        self._appointments_service = AppointmentService(db, file_store)
        self._index_service = index_service
        self._patient_graph = patient_graph_service

    # ---------------------------------------------------------------- đọc

    async def list_mine(self, doctor_id: str, doctor_name: str, q: str) -> list[FinalizeReportItemOutput]:
        rows = await self._reports.list_for_doctor(doctor_id, q.strip())
        long_term = await self._clinical.long_term_facts(list({p.id for _, p in rows}))
        conv_ids = await self._conversation_ids([r for r, _ in rows])
        images_map = await self._reports.list_images_for_reports([r.id for r, _ in rows])
        return [
            FinalizeReportItemOutput(
                **self._report_output(r, doctor_name, conv_ids, images_map.get(r.id, [])).model_dump(), patient=to_patient_profile_dto(p, long_term[p.id])
            )
            for r, p in rows
        ]

    async def list_for_patient(self, profile_id: str) -> list[FinalizeReportOutput]:
        if await self._profiles.get(profile_id) is None:
            raise NotFoundError(f"hồ sơ bệnh nhân id={profile_id}")
        return await self._history(profile_id)

    async def list_for_session(self, session_id: str, doctor_id: str) -> list[FinalizeReportOutput]:
        """Lịch sử báo cáo kết luận của bệnh nhân thuộc phiên này (mọi lần khám, không chỉ ca hiện tại)."""
        session = await self._owned_session(session_id, doctor_id)
        profile_id = await self._profile_id_of(session)
        return await self._history(profile_id) if profile_id else []

    async def draft_for_session(self, session_id: str, doctor_id: str) -> FinalizeDraftOutput:
        session = await self._owned_session(session_id, doctor_id)
        profile = await self._profile_of(session)
        rows = await self._consultations.list_facts_with_sources(profile.id)
        files = await self._files_of(rows)
        return FinalizeDraftOutput(
            patient=to_patient_profile_dto(profile, (await self._clinical.long_term_facts([profile.id]))[profile.id]),
            suggestions=await self._graph_suggestions(profile.id, rows),
            facts=[
                DraftFactOutput(
                    source_fact_id=fact.id,
                    fact_type=ClinicalFactType(fact.fact_type),
                    label=fact.label,
                    detail=fact.detail,
                    origin=default_origin(fact.fact_type),
                    provenances=self._provenances_output(_snapshot_provenances(messages, files)),
                )
                for fact, messages in rows
            ],
        )

    async def _graph_suggestions(self, profile_id: str, rows: list[FactRow]) -> GraphSuggestionOutput:
        """Lỗi graph chỉ làm mất gợi ý, không chặn đóng ca."""
        out = GraphSuggestionOutput()
        if self._patient_graph:
            try:
                out.previous_conditions, out.previous_advice = await self._patient_graph.get_history_hints(profile_id)
            except Exception:  # noqa: BLE001
                out.notes.append("Không đọc được lịch sử từ đồ thị bệnh nhân.")
        symptoms = [fact.label for fact, _ in rows if fact.fact_type in (ClinicalFactType.SYMPTOM, ClinicalFactType.LESION)]
        if not symptoms:
            return out
        # import muộn: kg_templates import app.api.deps nên import đầu file sẽ vòng
        from agent.tools.hybrid_retrieval.kg_templates import run_intent

        try:
            # translate=False: tên không khớp thì bỏ qua, không gọi LLM dịch
            facts, notes, _ = await run_intent("diseases_with_symptom", symptoms, 5, translate=False)
            out.candidate_diseases = [f["text"] for f in facts]
            out.notes += notes
            top = await run_intent("red_flags_risk", [d for d in _candidate_names(out.candidate_diseases)][:2], 6, translate=False)
            out.red_flags = [f["text"] for f in top[0]]
        except Exception:  # noqa: BLE001
            out.notes.append("Không tra được đồ thị tri thức da liễu.")
        return out

    # ---------------------------------------------------------------- chốt

    async def finalize_session(
        self, session_id: str, doctor_id: str, doctor_name: str, body: FinalizeReportInput
    ) -> FinalizeReportOutput:
        """Chốt báo cáo kết luận từ ca tư vấn và đóng ca trong cùng một giao dịch."""
        session = await self._owned_session(session_id, doctor_id)
        if session.status != "active" or session.doctor_id != doctor_id:
            raise ConflictError("Chỉ chốt được ca bạn đang tư vấn (đã nhận, chưa đóng).")
        profile = await self._profile_of(session)
        report = await self._create(profile, doctor_id, body, session.id)
        await self._consultations.resolve_session(session)
        images = await self._reports.list_images(report.id)
        return self._report_output(report, doctor_name, {session.id: session.conversation_id}, images)

    async def _create(
        self, profile: PatientProfile, doctor_id: str, body: FinalizeReportInput, session_id: str
    ) -> FinalizeReport:
        """Luồng cũ (phiên tư vấn): ghi báo cáo rồi nạp Qdrant / graph ngay."""
        source_facts = await self._source_facts(profile.id, body.facts)
        files = await self._files_of(list(source_facts.values()))
        snapshot = build_snapshot(profile, body, source_facts, files)
        report, attached = await self._store_report(profile, doctor_id, body, snapshot, session_id=session_id)
        await self._publish(report, profile, doctor_id, body, snapshot, attached, session_id)
        return report

    async def _store_report(
        self,
        profile: PatientProfile,
        doctor_id: str,
        body: FinalizeReportInput,
        snapshot: FinalizeReportSnapshot,
        *,
        session_id: str | None = None,
        encounter_id: str | None = None,
        diagnosis_code: str | None = None,
    ) -> tuple[FinalizeReport, list[tuple[Any, Any]]]:
        report = await self._reports.create(
            patient_profile_id=profile.id,
            doctor_id=doctor_id,
            diagnosis=body.diagnosis.strip(),
            notes=body.notes.strip(),
            is_reference_case=body.is_reference_case,
            consultation_session_id=session_id,
            encounter_id=encounter_id,
            diagnosis_code=diagnosis_code,
            snapshot=snapshot.model_dump(mode="json"),
        )
        # Gắn ảnh bệnh bác sĩ chọn từ đoạn chat vào báo cáo kết luận
        attached: list[tuple[Any, Any]] = []
        for img_input in body.images:
            file_row = await self._files.get(img_input.file_id)
            if file_row is None:
                logger.warning("[finalize] bỏ ảnh %s: không thấy file", img_input.file_id)
                continue
            patient_image = await self._reports.add_patient_image(
                finalize_report_id=report.id,
                file_id=img_input.file_id,
                body_site=img_input.body_site,
                description=img_input.description,
                confirmed_label=img_input.confirmed_label,
            )
            attached.append((patient_image, file_row))
        return report, attached

    async def _publish(
        self,
        report: FinalizeReport,
        profile: PatientProfile,
        doctor_id: str,
        body: FinalizeReportInput,
        snapshot: FinalizeReportSnapshot,
        attached: list[tuple[Any, Any]],
        session_node_id: str,
    ) -> None:
        """Nạp ca bệnh vào Qdrant (kèm ảnh) và graph bệnh nhân; lỗi chỉ ghi log vì kết luận đã lưu."""
        if self._index_service:
            try:
                await self._index_service.index_report(report, profile, images=attached)
            except Exception:  # noqa: BLE001
                # báo cáo này sẽ thiếu trong Qdrant tới khi chạy `make reindex-qdrant`
                logger.warning("Không nạp được báo cáo %s vào Qdrant", report.id, exc_info=True)
        if self._patient_graph:
            try:
                await self._patient_graph.sync_finalized_session(
                    patient_id=profile.id,
                    gender=profile.gender,
                    dob=profile.dob.isoformat(),
                    session_id=session_node_id,
                    session_date=report.created_at,
                    doctor_id=doctor_id,
                    suspected_condition=body.diagnosis,
                    notes=body.notes,
                    instructions=body.instructions,
                    facts=[f.model_dump(mode="json") for f in snapshot.clinical_facts],
                    images=[
                        {
                            "file_id": img.file_id,
                            "body_site": img.body_site,
                            "description": img.description,
                            "confirmed_label": img.confirmed_label,
                        }
                        for img, _ in attached
                    ],
                )
            except Exception:  # noqa: BLE001
                logger.warning("Không đồng bộ %s vào đồ thị bệnh nhân", session_node_id, exc_info=True)

    # ---------------------------------------------------------------- khám trực tiếp (lần khám từ lịch hẹn)

    async def draft_for_encounter(self, encounter_id: str, doctor_id: str) -> EncounterDraftOutput:
        appointment = await self._encounter_appointment(encounter_id, doctor_id)
        profile = await self._profiles.get(appointment.patient_profile_id)
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân của lần khám")
        detail = await self._appointments_service.detail(doctor_id, appointment.id)
        rows = await self._clinical.facts_with_sources(profile.id, appointment.episode_id)
        files = await self._files_of(rows)
        return EncounterDraftOutput(
            encounter_id=encounter_id,
            appointment_id=appointment.id,
            episode=detail.episode,
            images=detail.episode.image_predictions,
            diagnosis_options=[DiagnosisOptionOutput(code=c.value, label=label) for c, label in DIAGNOSIS_CODE_LABELS.items()],
            patient=to_patient_profile_dto(profile, [f for f, _ in rows if f.episode_id is None]),
            suggestions=await self._graph_suggestions(profile.id, rows),
            facts=[
                DraftFactOutput(
                    source_fact_id=fact.id,
                    fact_type=ClinicalFactType(fact.fact_type),
                    label=fact.label,
                    detail=fact.detail,
                    origin=default_origin(fact.fact_type),
                    provenances=self._provenances_output(_snapshot_provenances(messages, files)),
                )
                for fact, messages in rows
            ],
        )

    async def finalize_encounter(
        self, encounter_id: str, doctor_id: str, doctor_name: str, body: FinalizeEncounterInput
    ) -> FinalizeReportOutput:
        """Một transaction: ghi fact + nhật ký doctor + kết luận, đóng lần khám / lịch hẹn / đợt; sau khi lưu mới nạp Qdrant + graph."""
        appointment = await self._encounter_appointment(encounter_id, doctor_id)
        encounter = await self._appointments.get_encounter(encounter_id)
        episode = await self._clinical.get_episode(appointment.episode_id)
        profile = await self._profiles.get(appointment.patient_profile_id)
        if encounter is None or episode is None or profile is None:
            raise NotFoundError("lần khám")
        if encounter.status != EncounterStatus.OPEN.value or episode.status != EpisodeStatus.IN_EXAM.value:
            raise ConflictError("Lần khám này đã được chốt.")
        if await self._reports.exists_for_encounter(encounter_id):
            raise ConflictError("Lần khám này đã có kết luận.")

        rows = await self._clinical.facts_with_sources(profile.id, episode.id)
        by_id = {fact.id: (fact, messages) for fact, messages in rows}
        keys = [(f.fact_type.value, " ".join(f.label.split()).lower()) for f in body.facts]
        if len(keys) != len(set(keys)):
            raise InvalidError("Có hai dữ kiện trùng loại và nhãn, hãy gộp lại thành một.")
        for f in body.facts:
            source = by_id.get(f.source_fact_id) if f.source_fact_id else None
            if f.source_fact_id and source is None:
                raise InvalidError("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc lần khám này, hãy tải lại form.")
            if source and (source[0].episode_id is None) != (f.fact_type in LONG_TERM_FACT_TYPES):
                raise InvalidError("Không đổi dữ kiện giữa nhóm dài hạn (dị ứng, tiền sử, thuốc) và nhóm theo đợt.")
        kept = {f.source_fact_id for f in body.facts if f.source_fact_id}
        removed = [row for fid, row in by_id.items() if fid not in kept]

        # snapshot dựng từ trạng thái TRƯỚC khi sửa để so ra fact bác sĩ đã đổi
        files = await self._files_of(rows)
        snapshot = build_snapshot(profile, body, by_id, files, removed)

        now = datetime.now(UTC)
        await self._clinical.delete_facts([fact for fact, _ in removed])
        for f in body.facts:
            label, detail = " ".join(f.label.split()), f.detail.strip()
            source = by_id.get(f.source_fact_id) if f.source_fact_id else None
            if source:
                fact = source[0]
                fact.fact_type, fact.label, fact.detail, fact.updated_at = f.fact_type.value, label, detail, now
            else:
                fact = await self._clinical.add_fact(
                    ClinicalFact(
                        patient_profile_id=profile.id,
                        episode_id=None if f.fact_type in LONG_TERM_FACT_TYPES else episode.id,
                        fact_type=f.fact_type.value,
                        label=label,
                        detail=detail,
                        created_at=now,
                        updated_at=now,
                    )
                )
            fact.verified_at, fact.verified_by_id = now, doctor_id
            await self._clinical.add_provenances(
                [
                    ClinicalProvenance(
                        fact_id=fact.id,
                        kind=ProvenanceKind.DOCTOR.value,
                        doctor_id=doctor_id,
                        encounter_id=encounter_id,
                        quote=label,
                        detail=detail,
                        created_at=now,
                    )
                ]
            )

        report, attached = await self._store_report(
            profile, doctor_id, body, snapshot, encounter_id=encounter_id, diagnosis_code=body.diagnosis_code.value
        )
        encounter.status, encounter.closed_at = EncounterStatus.CLOSED.value, now
        appointment.status = AppointmentStatus.DONE.value
        episode.status, episode.closed_at = EpisodeStatus.CLOSED.value, now
        await self._db.commit()

        await self._publish(report, profile, doctor_id, body, snapshot, attached, encounter_id)
        images = await self._reports.list_images(report.id)
        return self._report_output(report, doctor_name, {}, images)

    async def _encounter_appointment(self, encounter_id: str, doctor_id: str) -> Appointment:
        encounter = await self._appointments.get_encounter(encounter_id)
        if encounter is None:
            raise NotFoundError("lần khám")
        if encounter.doctor_id != doctor_id:
            raise ForbiddenError("Lần khám này do bác sĩ khác phụ trách.")
        appointment = await self._appointments.get(encounter.appointment_id)
        if appointment is None:
            raise NotFoundError("lịch hẹn của lần khám")
        return appointment

    # ---------------------------------------------------------------- tiện ích

    async def _owned_session(self, session_id: str, doctor_id: str) -> ConsultationSession:
        session = await self._consultations.get_session(session_id)
        if session is None:
            raise NotFoundError(f"phiên tư vấn id={session_id}")
        if session.doctor_id not in (None, doctor_id):
            raise ForbiddenError("Ca tư vấn này đang do bác sĩ khác phụ trách.")
        return session

    async def _profile_id_of(self, session: ConsultationSession) -> str | None:
        conv = await self._conversations.get(session.conversation_id)
        return conv.patient_profile_id if conv else None

    async def _profile_of(self, session: ConsultationSession) -> PatientProfile:
        profile_id = await self._profile_id_of(session)
        profile = await self._profiles.get(profile_id) if profile_id else None
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân của hội thoại này")
        return profile

    async def _source_facts(self, profile_id: str, facts: list[FactInput]) -> dict[str, FactRow]:
        if not any(f.source_fact_id for f in facts):
            return {}
        rows = await self._consultations.list_facts_with_sources(profile_id)
        return {fact.id: (fact, messages) for fact, messages in rows}

    async def _files_of(self, rows: list[FactRow]) -> dict[str, list[File]]:
        return await self._files.for_messages(list({m.id for _, messages in rows for m in messages}))

    async def _history(self, profile_id: str) -> list[FinalizeReportOutput]:
        rows = await self._reports.list_for_profile(profile_id)
        conv_ids = await self._conversation_ids([r for r, _ in rows])
        images_map = await self._reports.list_images_for_reports([r.id for r, _ in rows])
        return [self._report_output(r, name, conv_ids, images_map.get(r.id, [])) for r, name in rows]

    async def _conversation_ids(self, reports: list[FinalizeReport]) -> dict[str, str]:
        return await self._consultations.conversation_ids(
            [r.consultation_session_id for r in reports if r.consultation_session_id]
        )

    def _provenances_output(self, provenances: list[SnapshotProvenance]) -> list[SnapshotProvenanceOutput]:
        return [
            SnapshotProvenanceOutput(
                message=SnapshotMessageOutput(
                    **p.message.model_dump(exclude={"files"}),
                    files=[
                        FileDto(**f.model_dump(), url=self._file_store.presigned_url(f.storage_key))
                        for f in p.message.files
                    ],
                )
            )
            for p in provenances
        ]

    def _snapshot_output(self, raw: dict | None) -> FinalizeReportSnapshotOutput | None:
        if raw is None:
            return None
        snap = FinalizeReportSnapshot.model_validate(raw)
        return FinalizeReportSnapshotOutput(
            patient_profile=snap.patient_profile,
            assessment=snap.assessment,
            clinical_facts=[
                SnapshotClinicalFactOutput(
                    **f.model_dump(exclude={"provenances"}), provenances=self._provenances_output(f.provenances)
                )
                for f in snap.clinical_facts
            ],
            removed_facts=[
                SnapshotClinicalFactOutput(
                    **f.model_dump(exclude={"provenances"}), provenances=self._provenances_output(f.provenances)
                )
                for f in snap.removed_facts
            ],
        )

    def _report_output(
        self, report: FinalizeReport, doctor_name: str | None, conv_ids: dict[str, str],
        images: list[tuple[Any, Any]] | None = None,
    ) -> FinalizeReportOutput:
        session_id = report.consultation_session_id
        image_outputs: list[PatientImageOutput] = []
        for img, f in (images or []):
            image_outputs.append(
                PatientImageOutput(
                    id=img.id,
                    file=FileDto(
                        file_name=f.file_name,
                        content_type=f.content_type,
                        storage_key=f.storage_key,
                        url=self._file_store.presigned_url(f.storage_key),
                    ),
                    body_site=img.body_site or "",
                    description=img.description or "",
                    confirmed_label=img.confirmed_label,
                    captured_at=img.captured_at.isoformat() if img.captured_at else None,
                )
            )
        return FinalizeReportOutput(
            id=report.id,
            diagnosis=report.diagnosis,
            notes=report.notes,
            is_reference_case=report.is_reference_case,
            doctor_name=doctor_name,
            created_at=report.created_at.isoformat(),
            consultation_session_id=session_id,
            conversation_id=conv_ids.get(session_id) if session_id else None,
            encounter_id=report.encounter_id,
            diagnosis_code=report.diagnosis_code,
            snapshot=self._snapshot_output(report.snapshot),
            images=image_outputs,
        )
