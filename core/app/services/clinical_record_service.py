"""Ghi kết quả lâm sàng của một lượt chat (fact, giả thuyết, dự đoán ảnh) vào đợt bệnh theo vùng."""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constant import (
    LONG_TERM_FACT_TYPES,
    BodySite,
    ClinicalFactType,
    DiagnosisCode,
    EpisodeStatus,
    HypothesisConfidence,
    ProvenanceKind,
)
from app.config.settings import settings
from app.dto.request.patient_profile import ProfileFactInput
from app.models.clinical import ClinicalFact, ClinicalProvenance
from app.models.episode import AiHypothesis, ClinicalEpisode
from app.repositories.clinical_record_repository import ClinicalRecordRepository
from app.repositories.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)

QUOTE_MAX_CHARS = 500
DETAIL_MAX_CHARS = 300
_LONG_TERM = {t.value for t in LONG_TERM_FACT_TYPES}
_FACT_TYPES = {t.value for t in ClinicalFactType if t is not ClinicalFactType.IMAGE_FINDING}


def long_term_text(facts: list[ClinicalFact], fact_type: ClinicalFactType) -> str:
    """Gộp fact dài hạn thành một dòng cho các chỗ còn hiển thị dạng chuỗi (thẻ bệnh nhân, snapshot, payload Qdrant)."""
    return "; ".join(f"{f.label} ({f.detail})" if f.detail else f.label for f in facts if f.fact_type == fact_type.value)


def _site(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    return raw if raw in BodySite._value2member_map_ else None


class ClinicalRecordService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ClinicalRecordRepository(db)
        self._conversations = ConversationRepository(db)

    @property
    def repo(self) -> ClinicalRecordRepository:
        return self._repo

    async def apply_turn(
        self,
        conversation_id: str,
        facts: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        images: list[dict[str, Any]],
    ) -> None:
        """Không commit; caller commit. Lỗi dữ liệu của một mục chỉ bỏ mục đó (kèm log), không làm hỏng cả lượt."""
        if not (facts or hypotheses or images):
            return
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            logger.warning("[clinical] không thấy hội thoại %s, bỏ kết quả lâm sàng của lượt", conversation_id)
            return
        turn = _Turn(self._repo, conversation.patient_profile_id, conversation_id, datetime.now(UTC))

        # giả thuyết đi trước: chúng mở đợt theo vùng, fact / ảnh chưa rõ vùng mới có chỗ để gắn
        by_site: dict[str, list[dict[str, Any]]] = {}
        for h in hypotheses:
            site = _site(h.get("body_site")) or await turn.fallback_site()
            if site is None:
                logger.warning("[clinical] bỏ giả thuyết %r: chưa rõ vùng, hội thoại chưa có đợt nào", h.get("disease"))
                continue
            by_site.setdefault(site, []).append(h)
        for site, items in by_site.items():
            await self._save_hypotheses(await turn.episode(site), items)

        for f in facts:
            await self._save_fact(turn, f)

        if images:
            codes = {site: {str(h.get("code") or "") for h in items} for site, items in by_site.items()}
            await self._save_images(turn, images, codes)

    async def replace_long_term_facts(self, patient_profile_id: str, items: list[ProfileFactInput]) -> list[ClinicalFact]:
        """Form hồ sơ là danh sách đầy đủ: thêm / sửa theo (loại, nhãn), xoá mục không còn. Không commit."""
        now = datetime.now(UTC)
        wanted: dict[tuple[str, str], tuple[str, str]] = {}
        for item in items:
            label = " ".join(item.label.split())[:255]
            if label:
                wanted[(item.fact_type, label.lower())] = (label, item.detail.strip())
        existing = (await self._repo.long_term_facts([patient_profile_id]))[patient_profile_id]
        by_key = {(f.fact_type, f.label.lower()): f for f in existing}

        removed = [f for key, f in by_key.items() if key not in wanted]
        if removed:
            logger.info("[clinical] hồ sơ %s: xoá %d fact dài hạn qua form", patient_profile_id, len(removed))
            await self._repo.delete_facts(removed)

        logs: list[ClinicalProvenance] = []
        for (fact_type, _), (label, detail) in wanted.items():
            fact = by_key.get((fact_type, label.lower()))
            if fact is None:
                fact = await self._repo.add_fact(
                    ClinicalFact(
                        patient_profile_id=patient_profile_id,
                        fact_type=fact_type,
                        label=label,
                        detail=detail,
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif (label, detail) != (fact.label, fact.detail):
                if detail != fact.detail:
                    fact.verified_at = None  # giá trị mới chưa ai kiểm chứng
                    fact.verified_by_id = None
                fact.label, fact.detail, fact.updated_at = label, detail, now
            else:
                continue
            logs.append(
                ClinicalProvenance(
                    fact_id=fact.id,
                    kind=ProvenanceKind.PROFILE.value,
                    quote=f"{label}: {detail}" if detail else label,
                    detail=detail,
                    created_at=now,
                )
            )
        await self._repo.add_provenances(logs)
        return (await self._repo.long_term_facts([patient_profile_id]))[patient_profile_id]

    async def _save_hypotheses(self, episode: ClinicalEpisode, items: list[dict[str, Any]]) -> None:
        if episode.status != EpisodeStatus.OPEN.value:
            logger.info("[clinical] đợt %s đang %s, giả thuyết đã khoá — bỏ cập nhật", episode.id, episode.status)
            return
        rows: list[AiHypothesis] = []
        for h in items:
            code = str(h.get("code") or "")
            confidence = str(h.get("confidence") or "")
            if code not in DiagnosisCode._value2member_map_ or confidence not in HypothesisConfidence._value2member_map_:
                logger.warning("[clinical] bỏ giả thuyết %r: mã %r / độ tin cậy %r không hợp lệ", h.get("disease"), code, confidence)
                continue
            rows.append(
                AiHypothesis(
                    episode_id=episode.id,
                    rank=len(rows) + 1,
                    diagnosis_code=code,
                    disease=str(h.get("disease") or "")[:255],
                    confidence=confidence,
                    evidence=list(h.get("evidence") or []),
                    missing=list(h.get("missing") or []),
                )
            )
        await self._repo.replace_hypotheses(episode.id, rows)

    async def _save_fact(self, turn: "_Turn", f: dict[str, Any]) -> None:
        fact_type = str(f.get("fact_type") or "")
        label = " ".join(str(f.get("template_label") or f.get("label") or "").split())[:255]
        detail = str(f.get("detail") or "").strip()[:DETAIL_MAX_CHARS]
        if fact_type not in _FACT_TYPES or not label:
            logger.warning("[clinical] bỏ fact loại %r nhãn %r: không hợp lệ", fact_type, label)
            return
        episode_id: str | None = None
        if fact_type not in _LONG_TERM:
            site = _site(f.get("body_site")) or await turn.fallback_site()
            if site is None:
                # agent giữ fact này trong state và gửi lại ở lượt sau, khi hội thoại đã có đợt
                logger.info("[clinical] fact %r chưa rõ vùng, chưa lưu", label)
                return
            episode_id = (await turn.episode(site)).id

        fact = await self._repo.find_fact(turn.profile_id, episode_id, fact_type, label)
        if fact is None:
            fact = await self._repo.add_fact(
                ClinicalFact(
                    patient_profile_id=turn.profile_id,
                    episode_id=episode_id,
                    fact_type=fact_type,
                    label=label,
                    detail=detail,
                    created_at=turn.now,
                    updated_at=turn.now,
                )
            )
        elif detail and detail != fact.detail:
            fact.detail = detail
            fact.updated_at = turn.now
            fact.verified_at = None  # giá trị mới chưa ai kiểm chứng
            fact.verified_by_id = None

        sources = [str(m) for m in (f.get("source_messages") or []) if m]
        known = await self._repo.provenance_messages([fact.id])
        contents = await self._repo.message_contents([m for m in sources if (fact.id, m) not in known])
        await self._repo.add_provenances(
            [
                ClinicalProvenance(
                    fact_id=fact.id,
                    kind=ProvenanceKind.CHAT.value,
                    message_id=mid,
                    quote=content[:QUOTE_MAX_CHARS],
                    detail=fact.detail,
                    created_at=turn.now,
                )
                for mid, content in contents.items()
            ]
        )

    async def _save_images(self, turn: "_Turn", images: list[dict[str, Any]], codes: dict[str, set[str]]) -> None:
        file_ids = await self._repo.file_ids_by_storage_key([str(i.get("storage_key") or "") for i in images])
        for img in images:
            file_id = file_ids.get(str(img.get("storage_key") or ""))
            if file_id is None:
                logger.warning("[clinical] bỏ dự đoán ảnh %r: không thấy file", img.get("storage_key"))
                continue
            top_k = list(img.get("top_k") or [])
            # lượt chạm nhiều vùng: ảnh thuộc đợt có giả thuyết trùng nhãn top-1 của CNN
            top = str(top_k[0].get("label") or "") if top_k else ""
            matched = [site for site, cs in codes.items() if top and top in cs]
            site = matched[0] if len(matched) == 1 else turn.only_touched_site() or await turn.fallback_site()
            if site is None:
                logger.warning("[clinical] bỏ dự đoán ảnh %r: không xác định được đợt", img.get("storage_key"))
                continue
            episode = await turn.episode(site)
            by_file = {str(p.get("file_id")): p for p in (episode.image_predictions or [])}
            by_file[file_id] = {"file_id": file_id, "top_k": top_k}
            episode.image_predictions = list(by_file.values())  # gán list mới để SQLAlchemy thấy JSONB đổi


class _Turn:
    """Các đợt đã chạm trong một lượt, để fact / ảnh chưa rõ vùng gắn được vào đúng đợt."""

    def __init__(self, repo: ClinicalRecordRepository, profile_id: str, conversation_id: str, now: datetime) -> None:
        self.repo = repo
        self.profile_id = profile_id
        self.conversation_id = conversation_id
        self.now = now
        self.touched: dict[str, ClinicalEpisode] = {}

    async def episode(self, site: str) -> ClinicalEpisode:
        """Đợt đang hoạt động của vùng; quá hạn thì đóng `expired` và mở đợt mới."""
        if site in self.touched:
            return self.touched[site]
        episode = await self.repo.active_episode(self.profile_id, site)
        if episode is not None and self._expired(episode):
            episode.status = EpisodeStatus.EXPIRED.value
            episode.closed_at = self.now
            await self.repo.flush()  # nhả unique index "1 đợt hoạt động / vùng" trước khi mở đợt mới
            logger.info("[clinical] đợt %s (%s) hết hạn, mở đợt mới", episode.id, site)
            episode = None
        if episode is None:
            episode = await self.repo.add_episode(
                ClinicalEpisode(patient_profile_id=self.profile_id, body_site=site, opened_at=self.now, updated_at=self.now)
            )
        episode.last_conversation_id = self.conversation_id
        episode.updated_at = self.now
        self.touched[site] = episode
        return episode

    def _expired(self, episode: ClinicalEpisode) -> bool:
        # TODO(đợt 4): đợt gắn lịch hẹn đang hoạt động không hết hạn
        limit = timedelta(days=settings.CLINICAL_EPISODE_EXPIRE_DAYS)
        return episode.status == EpisodeStatus.OPEN.value and self.now - episode.updated_at > limit

    def only_touched_site(self) -> str | None:
        return next(iter(self.touched)) if len(self.touched) == 1 else None

    async def fallback_site(self) -> str | None:
        """Vùng cho mục chưa rõ vùng: đợt duy nhất lượt này đã chạm, hoặc đợt mở duy nhất của hội thoại."""
        site = self.only_touched_site()
        if site is not None:
            return site
        if self.touched:
            return None
        episodes = [e for e in await self.repo.open_episodes_of_conversation(self.conversation_id) if not self._expired(e)]
        return episodes[0].body_site if len(episodes) == 1 else None
