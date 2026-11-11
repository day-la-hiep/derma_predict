"""Đặt lịch khám cho một đợt bệnh đã đủ thông tin, và bác sĩ bắt đầu khám từ lịch hẹn."""
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constant import (
    BODY_SITE_LABELS,
    DIAGNOSIS_CODE_LABELS,
    AppointmentStatus,
    BodySite,
    DiagnosisCode,
    EpisodeStatus,
)
from app.dto.common import FileDto
from app.dto.consultation import ClinicalFactOutput, ClinicalFactSourceMessageOutput
from app.dto.request.appointment import BookAppointmentInput
from app.dto.response.appointment import (
    AppointmentOutput,
    DoctorAppointmentDetailOutput,
    DoctorAppointmentItemOutput,
    DoctorEpisodeOutput,
    HypothesisEvidenceOutput,
    HypothesisOutput,
    ImagePredictionOutput,
    LabelScoreOutput,
    PatientEpisodeOutput,
)
from app.exception.errors import ConflictError, ForbiddenError, InvalidError, NotFoundError
from app.models.clinical import ClinicalFact
from app.models.episode import AiHypothesis, ClinicalEpisode
from app.models.message import Message
from app.models.patient_profile import PatientProfile
from app.models.user import User
from app.models.visit import Appointment, Encounter
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.clinical_record_repository import ClinicalRecordRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.clinical_record_service import build_episode_summary, is_expired, to_patient_profile_dto
from app.services.file_store_service import FileStoreService

logger = logging.getLogger(__name__)


def _site_label(site: str) -> str:
    return BODY_SITE_LABELS.get(BodySite(site), site)


def _code_label(code: str) -> str:
    return DIAGNOSIS_CODE_LABELS.get(DiagnosisCode(code), code) if code in DiagnosisCode._value2member_map_ else code


def fact_output(fact: ClinicalFact, messages: list[Message]) -> ClinicalFactOutput:
    return ClinicalFactOutput(
        id=fact.id,
        template_label=fact.label,
        fact_type=fact.fact_type,
        detail=fact.detail,
        verified_at=fact.verified_at.isoformat() if fact.verified_at else None,
        created_at=fact.created_at.isoformat(),
        updated_at=fact.updated_at.isoformat(),
        source_message_ids=[m.id for m in messages],
        source_messages=[
            ClinicalFactSourceMessageOutput(
                id=m.id, sender=m.sender, content=m.content, created_at=m.created_at.isoformat() if m.created_at else None
            )
            for m in messages
        ],
    )


class AppointmentService:
    def __init__(self, db: AsyncSession, file_store: FileStoreService) -> None:
        self._db = db
        self._file_store = file_store
        self._repo = AppointmentRepository(db)
        self._clinical = ClinicalRecordRepository(db)
        self._profiles = PatientProfileRepository(db)

    # ---------------------------------------------------------------- bệnh nhân

    async def list_episodes(self, user_id: str, profile_id: str) -> list[PatientEpisodeOutput]:
        await self._own_profile(user_id, profile_id)
        return await self._patient_episodes(await self._clinical.active_episodes_of_profile(profile_id))

    async def book(self, user_id: str, body: BookAppointmentInput) -> AppointmentOutput:
        await self._own_profile(user_id, body.patient_profile_id)
        episode = await self._clinical.get_episode(body.episode_id)
        if episode is None or episode.patient_profile_id != body.patient_profile_id:
            raise NotFoundError("đợt bệnh của hồ sơ này")
        reason = await self._not_bookable_reason(episode)
        if reason:
            raise InvalidError(reason)
        if body.scheduled_at <= datetime.now(UTC):
            raise InvalidError("Thời gian hẹn phải ở tương lai.")
        appointment = await self._repo.add(
            Appointment(
                patient_profile_id=episode.patient_profile_id,
                episode_id=episode.id,
                scheduled_at=body.scheduled_at,
                reason=body.reason,
            )
        )
        await self._refresh_summary(episode, force=True)
        return await self._output(appointment, episode)

    async def list_mine(self, user_id: str) -> list[AppointmentOutput]:
        profile_ids = [p.id for p in await self._profiles.list_for_user(user_id)]
        return [await self._output(a, e) for a, e in await self._repo.list_for_profiles(profile_ids)]

    async def cancel_mine(self, user_id: str, appointment_id: str, reason: str) -> AppointmentOutput:
        appointment = await self._get(appointment_id)
        await self._own_profile(user_id, appointment.patient_profile_id)
        return await self._cancel(appointment, reason)

    # ---------------------------------------------------------------- bác sĩ

    async def list_for_doctor(
        self, doctor_id: str, start: datetime | None, end: datetime | None, status: str | None
    ) -> list[DoctorAppointmentItemOutput]:
        rows = await self._repo.list_for_doctor(doctor_id, start, end, status)
        hyps = await self._clinical.hypotheses([e.id for _, e, _ in rows])
        long_term = await self._clinical.long_term_facts([p.id for _, _, p in rows])
        return [await self._item(a, e, p, long_term[p.id], hyps[e.id]) for a, e, p in rows]

    async def detail(self, doctor_id: str, appointment_id: str) -> DoctorAppointmentDetailOutput:
        return await self._detail(await self._doctor_appointment(doctor_id, appointment_id))

    async def confirm(self, doctor_id: str, appointment_id: str) -> DoctorAppointmentDetailOutput:
        appointment = await self._doctor_appointment(doctor_id, appointment_id)
        if appointment.status != AppointmentStatus.REQUESTED.value:
            raise ConflictError("Chỉ xác nhận được lịch hẹn đang chờ.")
        appointment.status = AppointmentStatus.CONFIRMED.value
        appointment.doctor_id = doctor_id
        await self._repo.flush()
        return await self._detail(appointment)

    async def cancel_by_doctor(self, doctor_id: str, appointment_id: str, reason: str) -> DoctorAppointmentDetailOutput:
        appointment = await self._doctor_appointment(doctor_id, appointment_id)
        await self._cancel(appointment, reason)
        return await self._detail(appointment)

    async def mark_no_show(self, doctor_id: str, appointment_id: str) -> DoctorAppointmentDetailOutput:
        appointment = await self._doctor_appointment(doctor_id, appointment_id)
        if appointment.status != AppointmentStatus.CONFIRMED.value:
            raise ConflictError("Chỉ đánh dấu \"không đến\" cho lịch đã xác nhận.")
        appointment.status = AppointmentStatus.NO_SHOW.value
        await self._repo.flush()
        return await self._detail(appointment)

    async def change_episode(self, doctor_id: str, appointment_id: str, episode_id: str) -> DoctorAppointmentDetailOutput:
        appointment = await self._doctor_appointment(doctor_id, appointment_id)
        if appointment.status not in (AppointmentStatus.REQUESTED.value, AppointmentStatus.CONFIRMED.value):
            raise ConflictError("Chỉ đổi được đợt bệnh trước khi bắt đầu khám.")
        episode = await self._clinical.get_episode(episode_id)
        if episode is None or episode.patient_profile_id != appointment.patient_profile_id:
            raise NotFoundError("đợt bệnh của bệnh nhân này")
        if episode.id != appointment.episode_id:
            reason = await self._not_bookable_reason(episode)
            if reason:
                raise InvalidError(reason)
            appointment.episode_id = episode.id
            await self._repo.flush()
            await self._refresh_summary(episode, force=True)
        return await self._detail(appointment)

    async def start_encounter(self, doctor_id: str, appointment_id: str) -> DoctorAppointmentDetailOutput:
        """Một transaction: lịch → in_progress, đợt → in_exam (khoá giả thuyết), tạo lần khám."""
        appointment = await self._doctor_appointment(doctor_id, appointment_id)
        if appointment.status != AppointmentStatus.CONFIRMED.value or appointment.doctor_id != doctor_id:
            raise ConflictError("Chỉ bắt đầu khám được lịch bạn đã xác nhận.")
        episode = await self._episode(appointment.episode_id)
        if episode.status != EpisodeStatus.OPEN.value:
            raise ConflictError("Đợt bệnh không còn mở, hãy đổi sang đợt khác hoặc huỷ lịch.")
        await self._refresh_summary(episode, force=True)
        episode.status = EpisodeStatus.IN_EXAM.value
        appointment.status = AppointmentStatus.IN_PROGRESS.value
        await self._repo.add_encounter(
            Encounter(appointment_id=appointment.id, patient_profile_id=appointment.patient_profile_id, doctor_id=doctor_id)
        )
        return await self._detail(appointment)

    # ---------------------------------------------------------------- nội bộ

    async def _own_profile(self, user_id: str, profile_id: str) -> PatientProfile:
        profile = await self._profiles.get_for_user(user_id, profile_id)
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân")
        return profile

    async def _get(self, appointment_id: str) -> Appointment:
        appointment = await self._repo.get(appointment_id)
        if appointment is None:
            raise NotFoundError("lịch hẹn")
        return appointment

    async def _doctor_appointment(self, doctor_id: str, appointment_id: str) -> Appointment:
        appointment = await self._get(appointment_id)
        if appointment.doctor_id not in (None, doctor_id):
            raise ForbiddenError("Lịch hẹn này do bác sĩ khác phụ trách.")
        return appointment

    async def _episode(self, episode_id: str) -> ClinicalEpisode:
        episode = await self._clinical.get_episode(episode_id)
        if episode is None:
            raise NotFoundError("đợt bệnh")
        return episode

    async def _cancel(self, appointment: Appointment, reason: str) -> AppointmentOutput:
        if appointment.status not in (AppointmentStatus.REQUESTED.value, AppointmentStatus.CONFIRMED.value):
            raise ConflictError("Chỉ huỷ được lịch hẹn chưa bắt đầu khám.")
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.cancel_reason = reason
        await self._repo.flush()
        # đợt vẫn open: bệnh nhân chat tiếp rồi đặt lại lịch khác
        return await self._output(appointment, await self._episode(appointment.episode_id))

    async def _not_bookable_reason(self, episode: ClinicalEpisode) -> str | None:
        if episode.status != EpisodeStatus.OPEN.value:
            return "Đợt bệnh này không còn mở."
        if await is_expired(self._clinical, episode, datetime.now(UTC)):
            return "Đợt bệnh đã quá hạn không cập nhật, hãy mô tả lại triệu chứng trong chat."
        if await self._clinical.has_active_appointment(episode.id):
            return "Đợt bệnh này đã có lịch hẹn."
        if not (await self._clinical.hypotheses([episode.id]))[episode.id]:
            return "Chưa đủ thông tin: hãy mô tả triệu chứng trong chat để AI thu thập trước khi đặt lịch."
        return None

    async def _refresh_summary(self, episode: ClinicalEpisode, force: bool = False) -> None:
        if not force and episode.summary_at is not None and episode.summary_at >= episode.updated_at:
            return
        facts = (await self._clinical.episode_facts([episode.id]))[episode.id]
        long_term = (await self._clinical.long_term_facts([episode.patient_profile_id]))[episode.patient_profile_id]
        hypotheses = (await self._clinical.hypotheses([episode.id]))[episode.id]
        episode.summary = build_episode_summary(episode, facts, long_term, hypotheses)
        episode.summary_at = datetime.now(UTC)
        await self._repo.flush()

    async def _patient_episodes(self, episodes: list[ClinicalEpisode]) -> list[PatientEpisodeOutput]:
        ids = [e.id for e in episodes]
        facts = await self._clinical.episode_facts(ids)
        appointments = await self._repo.active_for_episodes(ids)
        out: list[PatientEpisodeOutput] = []
        for e in episodes:
            reason = await self._not_bookable_reason(e)
            appointment = appointments.get(e.id)
            out.append(
                PatientEpisodeOutput(
                    id=e.id,
                    body_site=e.body_site,
                    body_site_label=_site_label(e.body_site),
                    status=e.status,
                    updated_at=e.updated_at.isoformat(),
                    facts=[f"{f.label}: {f.detail}" if f.detail else f.label for f in facts[e.id]],
                    bookable=reason is None,
                    not_bookable_reason=reason,
                    appointment=await self._output(appointment, e) if appointment else None,
                )
            )
        return out

    async def _output(self, a: Appointment, episode: ClinicalEpisode) -> AppointmentOutput:
        user = await self._db.get(User, a.doctor_id) if a.doctor_id else None
        encounter = await self._repo.encounter_of(a.id)
        return AppointmentOutput(
            id=a.id,
            patient_profile_id=a.patient_profile_id,
            episode_id=a.episode_id,
            body_site=episode.body_site,
            body_site_label=_site_label(episode.body_site),
            doctor_id=a.doctor_id,
            doctor_name=user.full_name if user else None,
            scheduled_at=a.scheduled_at.isoformat(),
            status=a.status,
            reason=a.reason,
            cancel_reason=a.cancel_reason,
            created_at=a.created_at.isoformat(),
            encounter_id=encounter.id if encounter else None,
        )

    async def _item(
        self,
        a: Appointment,
        episode: ClinicalEpisode,
        profile: PatientProfile,
        long_term: list[ClinicalFact],
        hypotheses: list[AiHypothesis],
    ) -> DoctorAppointmentItemOutput:
        base = await self._output(a, episode)
        return DoctorAppointmentItemOutput(
            **base.model_dump(),
            patient=to_patient_profile_dto(profile, long_term),
            top_hypothesis=hypotheses[0].disease if hypotheses else None,
        )

    async def _detail(self, a: Appointment) -> DoctorAppointmentDetailOutput:
        episode = await self._episode(a.episode_id)
        await self._refresh_summary(episode)
        profile = await self._profiles.get(a.patient_profile_id)
        if profile is None:
            raise NotFoundError("hồ sơ bệnh nhân")
        rows = await self._clinical.facts_with_sources(profile.id, episode.id)
        hypotheses = (await self._clinical.hypotheses([episode.id]))[episode.id]
        long_term_rows = [(f, m) for f, m in rows if f.episode_id is None]
        item = await self._item(a, episode, profile, [f for f, _ in long_term_rows], hypotheses)
        others = [e for e in await self._clinical.active_episodes_of_profile(profile.id) if e.id != episode.id]
        return DoctorAppointmentDetailOutput(
            **item.model_dump(),
            episode=DoctorEpisodeOutput(
                id=episode.id,
                body_site=episode.body_site,
                body_site_label=_site_label(episode.body_site),
                status=episode.status,
                summary=episode.summary,
                summary_at=episode.summary_at.isoformat() if episode.summary_at else None,
                urgency=episode.urgency,
                red_flags=[str(r) for r in (episode.red_flags or [])],
                hypotheses=[self._hypothesis(h) for h in hypotheses],
                hypotheses_locked=episode.status != EpisodeStatus.OPEN.value,
                facts=[fact_output(f, m) for f, m in rows if f.episode_id == episode.id],
                image_predictions=await self.image_predictions(episode),
                updated_at=episode.updated_at.isoformat(),
            ),
            long_term_facts=[fact_output(f, m) for f, m in long_term_rows],
            other_episodes=await self._patient_episodes(others),
        )

    @staticmethod
    def _hypothesis(h: AiHypothesis) -> HypothesisOutput:
        return HypothesisOutput(
            rank=h.rank,
            diagnosis_code=h.diagnosis_code,
            diagnosis_label=_code_label(h.diagnosis_code),
            disease=h.disease,
            confidence=h.confidence,
            evidence=[HypothesisEvidenceOutput(**e) for e in (h.evidence or []) if isinstance(e, dict)],
            missing=[str(m) for m in (h.missing or [])],
        )

    async def image_predictions(self, episode: ClinicalEpisode) -> list[ImagePredictionOutput]:
        preds = list(episode.image_predictions or [])
        files = await self._clinical.files_by_ids([str(p.get("file_id")) for p in preds])
        out: list[ImagePredictionOutput] = []
        for p in preds:
            f = files.get(str(p.get("file_id")))
            file_dto = (
                FileDto(
                    file_name=f.file_name,
                    content_type=f.content_type,
                    storage_key=f.storage_key,
                    url=self._file_store.presigned_url(f.storage_key),
                )
                if f
                else None
            )
            out.append(
                ImagePredictionOutput(
                    file_id=str(p.get("file_id")),
                    file=file_dto,
                    top_k=[
                        LabelScoreOutput(
                            label=str(t.get("label")), label_name=_code_label(str(t.get("label"))), score=float(t.get("score") or 0)
                        )
                        for t in (p.get("top_k") or [])
                    ],
                )
            )
        return out
