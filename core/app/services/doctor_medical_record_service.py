from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constant import ClinicalFactType, FactOrigin, Gender, MessageSender, ProfileRelationship
from app.dto.base import (
    Assessment,
    File as FileEntity,
    MedicalRecordSnapshot,
    PatientImage as PatientImageEntity,
    SnapshotClinicalFact,
    SnapshotMessage,
    SnapshotPatientProfile,
    SnapshotProvenance,
)
from app.dto.common import FileDto
from app.dto.consultation import PatientProfileDto
from app.dto.request.medical_record import CreateDoctorMedicalRecordInput, FactInput, FinalizeMedicalRecordInput, PatientImageInput
from app.dto.response.medical_record import (
    DoctorMedicalRecordItemOutput,
    DoctorMedicalRecordOutput,
    DraftFactOutput,
    FinalizeDraftOutput,
    MedicalRecordSnapshotOutput,
    PatientImageOutput,
    SnapshotClinicalFactOutput,
    SnapshotMessageOutput,
    SnapshotProvenanceOutput,
)
from app.exception.errors import ConflictError, ForbiddenError, InvalidError, NotFoundError
from app.models.clinical import ClinicalFact, ClinicalFactTemplate
from app.models.consultation_session import ConsultationSession
from app.models.file import File
from app.models.medical_record import MedicalRecord
from app.models.message import Message
from app.models.patient_profile import PatientProfile
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.file_repository import FileRepository
from app.repositories.medical_record_repository import MedicalRecordRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.file_store_service import FileStoreService

FactRow = tuple[ClinicalFact, ClinicalFactTemplate, list[Message]]


def to_patient_profile_dto(profile: PatientProfile) -> PatientProfileDto:
    return PatientProfileDto(
        id=profile.id,
        full_name=profile.full_name,
        dob=profile.dob.isoformat(),
        gender=profile.gender,
        relationship=profile.relationship,
        phone=profile.phone,
        allergies=profile.allergies,
        medical_history=profile.medical_history,
    )


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


def build_snapshot(
    profile: PatientProfile,
    body: FinalizeMedicalRecordInput,
    source_facts: dict[str, FactRow],
    files: dict[str, list[File]],
) -> MedicalRecordSnapshot:
    """Chép mọi thứ cần hiển thị phiếu vào một bản bất biến; nguồn của fact lấy từ DB, không tin nội dung client gửi."""
    facts: list[SnapshotClinicalFact] = []
    for f in body.facts:
        source = source_facts.get(f.source_fact_id) if f.source_fact_id else None
        if f.source_fact_id and source is None:
            raise InvalidError("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc bệnh nhân này, hãy tải lại form.")
        if source is None:
            origin, provenances = FactOrigin.DOCTOR_OBSERVED, []
        else:
            fact, tpl, messages = source
            unchanged = (f.label.strip(), f.detail.strip(), f.fact_type.value) == (tpl.label, fact.detail, tpl.fact_type)
            origin = default_origin(tpl.fact_type) if unchanged else FactOrigin.DOCTOR_CORRECTED
            provenances = _snapshot_provenances(messages, files)
        facts.append(
            SnapshotClinicalFact(
                fact_type=f.fact_type, label=f.label.strip(), detail=f.detail.strip(), origin=origin, provenances=provenances
            )
        )
    return MedicalRecordSnapshot(
        patient_profile=SnapshotPatientProfile(
            full_name=profile.full_name,
            dob=profile.dob,
            gender=Gender(profile.gender),
            relationship=ProfileRelationship(profile.relationship),
            phone=profile.phone,
            allergies=profile.allergies,
            medical_history=profile.medical_history,
        ),
        assessment=Assessment(
            reasoning=body.reasoning.strip(),
            urgency=body.urgency,
            instructions=[i.strip() for i in body.instructions if i.strip()],
        ),
        clinical_facts=facts,
    )


from app.services.medical_case_index_service import MedicalCaseIndexService
from app.services.patient_graph_service import PatientGraphService


class DoctorMedicalRecordService:
    def __init__(
        self,
        db: AsyncSession,
        file_store: FileStoreService,
        case_index_service: MedicalCaseIndexService | None = None,
        patient_graph_service: PatientGraphService | None = None,
    ) -> None:
        self._records = MedicalRecordRepository(db)
        self._profiles = PatientProfileRepository(db)
        self._consultations = ConsultationRepository(db)
        self._conversations = ConversationRepository(db)
        self._files = FileRepository(db)
        self._file_store = file_store
        self._case_index_service = case_index_service
        self._patient_graph = patient_graph_service

    # ---------------------------------------------------------------- đọc

    async def list_mine(self, doctor_id: str, doctor_name: str, q: str) -> list[DoctorMedicalRecordItemOutput]:
        rows = await self._records.list_for_doctor(doctor_id, q.strip())
        conv_ids = await self._conversation_ids([r for r, _ in rows])
        images_map = await self._records.list_images_for_records([r.id for r, _ in rows])
        return [
            DoctorMedicalRecordItemOutput(
                **self._record_output(r, doctor_name, conv_ids, images_map.get(r.id, [])).model_dump(), patient=to_patient_profile_dto(p)
            )
            for r, p in rows
        ]

    async def list_for_patient(self, profile_id: str) -> list[DoctorMedicalRecordOutput]:
        if await self._profiles.get(profile_id) is None:
            raise NotFoundError(f"hồ sơ bệnh nhân id={profile_id}")
        return await self._history(profile_id)

    async def list_for_session(self, session_id: str, doctor_id: str) -> list[DoctorMedicalRecordOutput]:
        """Lịch sử bệnh án của bệnh nhân thuộc phiên này (mọi lần khám, không chỉ ca hiện tại)."""
        session = await self._owned_session(session_id, doctor_id)
        profile_id = await self._profile_id_of(session)
        return await self._history(profile_id) if profile_id else []

    async def search_patients(self, q: str) -> list[PatientProfileDto]:
        return [to_patient_profile_dto(p) for p in await self._profiles.search(q.strip())]

    async def draft_for_session(self, session_id: str, doctor_id: str) -> FinalizeDraftOutput:
        session = await self._owned_session(session_id, doctor_id)
        profile = await self._profile_of(session)
        rows = await self._consultations.get_active_facts_with_provenance(profile.id)
        files = await self._files_of(rows)
        return FinalizeDraftOutput(
            patient=to_patient_profile_dto(profile),
            facts=[
                DraftFactOutput(
                    source_fact_id=fact.id,
                    fact_type=ClinicalFactType(tpl.fact_type),
                    label=tpl.label,
                    detail=fact.detail,
                    origin=default_origin(tpl.fact_type),
                    provenances=self._provenances_output(_snapshot_provenances(messages, files)),
                )
                for fact, tpl, messages in rows
            ],
        )

    # ---------------------------------------------------------------- chốt

    async def finalize_session(
        self, session_id: str, doctor_id: str, doctor_name: str, body: FinalizeMedicalRecordInput
    ) -> DoctorMedicalRecordOutput:
        """Chốt bệnh án từ ca tư vấn và đóng ca trong cùng một giao dịch."""
        session = await self._owned_session(session_id, doctor_id)
        if session.status != "active" or session.doctor_id != doctor_id:
            raise ConflictError("Chỉ chốt được ca bạn đang tư vấn (đã nhận, chưa đóng).")
        profile = await self._profile_of(session)
        record = await self._create(profile, doctor_id, body, session.id)
        await self._consultations.resolve_session(session)
        images = await self._records.list_images(record.id)
        return self._record_output(record, doctor_name, {session.id: session.conversation_id}, images)

    async def create(
        self, doctor_id: str, doctor_name: str, body: CreateDoctorMedicalRecordInput
    ) -> DoctorMedicalRecordItemOutput:
        """Ca khám trực tiếp, không qua tư vấn online."""
        profile = await self._profiles.get(body.patient_profile_id)
        if profile is None:
            raise NotFoundError(f"hồ sơ bệnh nhân id={body.patient_profile_id}")
        record = await self._create(profile, doctor_id, body, None)
        images = await self._records.list_images(record.id)
        return DoctorMedicalRecordItemOutput(
            **self._record_output(record, doctor_name, {}, images).model_dump(), patient=to_patient_profile_dto(profile)
        )

    async def _create(
        self, profile: PatientProfile, doctor_id: str, body: FinalizeMedicalRecordInput, session_id: str | None
    ) -> MedicalRecord:
        source_facts = await self._source_facts(profile.id, body.facts)
        files = await self._files_of(list(source_facts.values()))
        snapshot = build_snapshot(profile, body, source_facts, files)
        record = await self._records.create(
            patient_profile_id=profile.id,
            doctor_id=doctor_id,
            diagnosis=body.diagnosis.strip(),
            notes=body.notes.strip(),
            is_reference_case=body.is_reference_case,
            consultation_session_id=session_id,
            snapshot=snapshot.model_dump(mode="json"),
        )
        # Gắn ảnh bệnh bác sĩ chọn từ đoạn chat vào bệnh án
        attached_images: list[tuple[Any, Any]] = []
        for img_input in body.images:
            file_row = await self._files.get(img_input.file_id)
            if file_row is None:
                continue
            patient_image = await self._records.add_patient_image(
                medical_record_id=record.id,
                file_id=img_input.file_id,
                body_site=img_input.body_site,
                description=img_input.description,
                confirmed_label=img_input.confirmed_label,
            )
            attached_images.append((patient_image, file_row))
        # Nạp ca bệnh vào Qdrant (kèm ảnh đã gắn) để chatbot tra cứu theo ảnh
        if self._case_index_service:
            try:
                await self._case_index_service.index_record(record, profile, images=attached_images)
            except Exception:  # noqa: BLE001
                # Không chặn hoàn tất hồ sơ nếu lỗi kết nối vector DB
                pass
        if self._patient_graph and session_id:
            try:
                await self._patient_graph.sync_finalized_session(
                    session_id=session_id,
                    doctor_id=doctor_id,
                    suspected_condition=body.diagnosis,
                    notes=body.notes,
                    instructions=body.instructions,
                )
            except Exception:  # noqa: BLE001
                # Không chặn hoàn tất hồ sơ nếu lỗi kết nối Graph DB
                pass
        return record

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
        rows = await self._consultations.get_active_facts_with_provenance(profile_id)
        return {fact.id: (fact, tpl, messages) for fact, tpl, messages in rows}

    async def _files_of(self, rows: list[FactRow]) -> dict[str, list[File]]:
        return await self._files.for_messages(list({m.id for _, _, messages in rows for m in messages}))

    async def _history(self, profile_id: str) -> list[DoctorMedicalRecordOutput]:
        rows = await self._records.list_for_profile(profile_id)
        conv_ids = await self._conversation_ids([r for r, _ in rows])
        images_map = await self._records.list_images_for_records([r.id for r, _ in rows])
        return [self._record_output(r, name, conv_ids, images_map.get(r.id, [])) for r, name in rows]

    async def _conversation_ids(self, records: list[MedicalRecord]) -> dict[str, str]:
        return await self._consultations.conversation_ids(
            [r.consultation_session_id for r in records if r.consultation_session_id]
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

    def _snapshot_output(self, raw: dict | None) -> MedicalRecordSnapshotOutput | None:
        if raw is None:
            return None
        snap = MedicalRecordSnapshot.model_validate(raw)
        return MedicalRecordSnapshotOutput(
            patient_profile=snap.patient_profile,
            assessment=snap.assessment,
            clinical_facts=[
                SnapshotClinicalFactOutput(
                    **f.model_dump(exclude={"provenances"}), provenances=self._provenances_output(f.provenances)
                )
                for f in snap.clinical_facts
            ],
        )

    def _record_output(
        self, record: MedicalRecord, doctor_name: str | None, conv_ids: dict[str, str],
        images: list[tuple[Any, Any]] | None = None,
    ) -> DoctorMedicalRecordOutput:
        session_id = record.consultation_session_id
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
        return DoctorMedicalRecordOutput(
            id=record.id,
            diagnosis=record.diagnosis,
            notes=record.notes,
            is_reference_case=record.is_reference_case,
            doctor_name=doctor_name,
            created_at=record.created_at.isoformat(),
            consultation_session_id=session_id,
            conversation_id=conv_ids.get(session_id) if session_id else None,
            snapshot=self._snapshot_output(record.snapshot),
            images=image_outputs,
        )
