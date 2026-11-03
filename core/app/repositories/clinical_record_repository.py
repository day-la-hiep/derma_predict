"""Truy vấn DB cho hồ sơ lâm sàng: đợt bệnh, fact theo phạm vi (hồ sơ / đợt), nhật ký nguồn, giả thuyết AI."""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical import ClinicalFact, ClinicalProvenance
from app.models.episode import AiHypothesis, ClinicalEpisode
from app.models.file import File
from app.models.message import Message

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
