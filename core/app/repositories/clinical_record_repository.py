"""Truy vấn DB cho hồ sơ lâm sàng: đợt bệnh, fact theo phạm vi (hồ sơ / đợt), nhật ký nguồn, giả thuyết AI."""
from collections import defaultdict

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical import ClinicalFact, ClinicalProvenance
from app.models.episode import AiHypothesis, ClinicalEpisode
from app.models.file import File
from app.models.message import Message
from app.models.visit import Appointment

ACTIVE_STATUSES = ("open", "in_exam")


class ClinicalRecordRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def active_episode(self, patient_profile_id: str, body_site: str) -> ClinicalEpisode | None:
        stmt = select(ClinicalEpisode).where(
            ClinicalEpisode.patient_profile_id == patient_profile_id,
            ClinicalEpisode.body_site == body_site,
            ClinicalEpisode.status.in_(ACTIVE_STATUSES),
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def open_episodes_of_conversation(self, conversation_id: str) -> list[ClinicalEpisode]:
        stmt = select(ClinicalEpisode).where(
            ClinicalEpisode.last_conversation_id == conversation_id, ClinicalEpisode.status == "open"
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def flush(self) -> None:
        await self._db.flush()

    async def add_episode(self, episode: ClinicalEpisode) -> ClinicalEpisode:
        self._db.add(episode)
        await self._db.flush()
        return episode

    async def find_fact(
        self, patient_profile_id: str, episode_id: str | None, fact_type: str, label: str
    ) -> ClinicalFact | None:
        """Theo khoá duy nhất: (hồ sơ, loại, nhãn) với fact dài hạn, (đợt, loại, nhãn) với fact theo đợt."""
        scope = (
            ClinicalFact.episode_id == episode_id
            if episode_id
            else (ClinicalFact.patient_profile_id == patient_profile_id) & ClinicalFact.episode_id.is_(None)
        )
        stmt = select(ClinicalFact).where(
            scope, ClinicalFact.fact_type == fact_type, func.lower(ClinicalFact.label) == label.lower()
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def add_fact(self, fact: ClinicalFact) -> ClinicalFact:
        self._db.add(fact)
        await self._db.flush()
        return fact

    async def provenance_messages(self, fact_ids: list[str]) -> set[tuple[str, str]]:
        """Các cặp (fact_id, message_id) đã có trong nhật ký."""
        if not fact_ids:
            return set()
        stmt = select(ClinicalProvenance.fact_id, ClinicalProvenance.message_id).where(
            ClinicalProvenance.fact_id.in_(fact_ids), ClinicalProvenance.message_id.is_not(None)
        )
        return {(f, m) for f, m in (await self._db.execute(stmt)).all() if m}

    async def add_provenances(self, provenances: list[ClinicalProvenance]) -> None:
        self._db.add_all(provenances)
        await self._db.flush()

    async def message_contents(self, message_ids: list[str]) -> dict[str, str]:
        """Chỉ trả tin có thật trong DB (id tin trong checkpoint cũ của agent không khớp DB)."""
        if not message_ids:
            return {}
        stmt = select(Message.id, Message.content).where(Message.id.in_(message_ids))
        return {mid: content or "" for mid, content in (await self._db.execute(stmt)).all()}

    async def replace_hypotheses(self, episode_id: str, hypotheses: list[AiHypothesis]) -> None:
        await self._db.execute(delete(AiHypothesis).where(AiHypothesis.episode_id == episode_id))
        await self._db.flush()
        self._db.add_all(hypotheses)
        await self._db.flush()

    async def file_ids_by_storage_key(self, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
        stmt = select(File.storage_key, File.id).where(File.storage_key.in_(keys))
        return {key: fid for key, fid in (await self._db.execute(stmt)).all()}

    async def current_facts(self, patient_profile_id: str) -> list[tuple[ClinicalFact, str | None]]:
        """Fact dài hạn + fact của các đợt đang hoạt động, kèm vùng của đợt (None với fact dài hạn) — agent nạp mỗi lượt."""
        stmt = (
            select(ClinicalFact, ClinicalEpisode.body_site)
            .outerjoin(ClinicalEpisode, ClinicalEpisode.id == ClinicalFact.episode_id)
            .where(
                ClinicalFact.patient_profile_id == patient_profile_id,
                or_(ClinicalFact.episode_id.is_(None), ClinicalEpisode.status.in_(ACTIVE_STATUSES)),
            )
            .order_by(ClinicalFact.updated_at.asc())
        )
        return [(f, site) for f, site in (await self._db.execute(stmt)).all()]

    async def long_term_facts(self, patient_profile_ids: list[str]) -> dict[str, list[ClinicalFact]]:
        """Fact dài hạn (dị ứng / tiền sử / thuốc) theo hồ sơ, cũ trước."""
        out: dict[str, list[ClinicalFact]] = {pid: [] for pid in patient_profile_ids}
        if not patient_profile_ids:
            return out
        stmt = (
            select(ClinicalFact)
            .where(ClinicalFact.patient_profile_id.in_(patient_profile_ids), ClinicalFact.episode_id.is_(None))
            .order_by(ClinicalFact.created_at.asc())
        )
        for f in (await self._db.execute(stmt)).scalars().all():
            out[f.patient_profile_id].append(f)
        return out

    async def delete_facts(self, facts: list[ClinicalFact]) -> None:
        for f in facts:
            await self._db.delete(f)
        await self._db.flush()

    async def get_episode(self, episode_id: str) -> ClinicalEpisode | None:
        return await self._db.get(ClinicalEpisode, episode_id)

    async def active_episodes_of_profile(self, patient_profile_id: str) -> list[ClinicalEpisode]:
        stmt = (
            select(ClinicalEpisode)
            .where(ClinicalEpisode.patient_profile_id == patient_profile_id, ClinicalEpisode.status.in_(ACTIVE_STATUSES))
            .order_by(ClinicalEpisode.updated_at.desc())
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def has_active_appointment(self, episode_id: str) -> bool:
        stmt = select(
            exists().where(
                Appointment.episode_id == episode_id,
                Appointment.status.in_(("requested", "confirmed", "in_progress")),
            )
        )
        return bool((await self._db.execute(stmt)).scalar())

    async def hypotheses(self, episode_ids: list[str]) -> dict[str, list[AiHypothesis]]:
        out: dict[str, list[AiHypothesis]] = {eid: [] for eid in episode_ids}
        if not episode_ids:
            return out
        stmt = select(AiHypothesis).where(AiHypothesis.episode_id.in_(episode_ids)).order_by(AiHypothesis.rank.asc())
        for h in (await self._db.execute(stmt)).scalars().all():
            out[h.episode_id].append(h)
        return out

    async def episode_facts(self, episode_ids: list[str]) -> dict[str, list[ClinicalFact]]:
        out: dict[str, list[ClinicalFact]] = {eid: [] for eid in episode_ids}
        if not episode_ids:
            return out
        stmt = select(ClinicalFact).where(ClinicalFact.episode_id.in_(episode_ids)).order_by(ClinicalFact.created_at.asc())
        for f in (await self._db.execute(stmt)).scalars().all():
            if f.episode_id:
                out[f.episode_id].append(f)
        return out

    async def facts_with_sources(self, patient_profile_id: str, episode_id: str | None) -> list[tuple[ClinicalFact, list[Message]]]:
        """Fact dài hạn của hồ sơ + fact của một đợt (nếu có), cùng tin nhắn nguồn còn tồn tại; cũ trước."""
        scope = ClinicalFact.episode_id.is_(None)
        if episode_id:
            scope = scope | (ClinicalFact.episode_id == episode_id)
        stmt = (
            select(ClinicalFact)
            .where(ClinicalFact.patient_profile_id == patient_profile_id, scope)
            .order_by(ClinicalFact.created_at.asc())
        )
        facts = list((await self._db.execute(stmt)).scalars().all())
        if not facts:
            return []
        prov = (
            select(ClinicalProvenance.fact_id, Message)
            .join(Message, Message.id == ClinicalProvenance.message_id)
            .where(ClinicalProvenance.fact_id.in_([f.id for f in facts]))
            .order_by(Message.created_at.asc())
        )
        by_fact: dict[str, dict[str, Message]] = defaultdict(dict)
        for fact_id, message in (await self._db.execute(prov)).all():
            by_fact[fact_id][message.id] = message
        return [(f, list(by_fact[f.id].values())) for f in facts]

    async def files_by_ids(self, file_ids: list[str]) -> dict[str, File]:
        if not file_ids:
            return {}
        stmt = select(File).where(File.id.in_(file_ids))
        return {f.id: f for f in (await self._db.execute(stmt)).scalars().all()}
