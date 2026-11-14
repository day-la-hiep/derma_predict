import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.context.agent_context import AgentContext
from app.deps import get_knowledge_client
from app.prompt.v3.pre_diagnosis_prompts import LINK_CHOOSE
from app.reasoning.structured_llm_calls import invoke_structured_with_retry
from app.tools.v3.extract_slots import Slot

logger = logging.getLogger(__name__)

ACCEPT_CONFIDENCE = 0.7
# Hai ứng viên đầu có điểm khớp tên sát nhau thì vẫn nhận lựa chọn của LLM nhưng đánh dấu để khối hỏi thêm hỏi lại.
AMBIGUOUS_GAP = 0.1
_OBJECT_TYPE = {
    "symptom": "effect/phenotype", "morphology": "effect/phenotype", "color": "effect/phenotype", "scale": "effect/phenotype",
    "distribution": "effect/phenotype", "drug": "drug", "disease": "disease",
}
# DermO là phương án cuối; term DermO có xref HPO thì knowledge đổi sang node phenotype PrimeKG.
_DERMO_FALLBACK = ("symptom", "morphology", "color", "scale", "distribution", "disease")


@dataclass(frozen=True)
class Link:
    node_id: str | None
    node_name: str | None
    confidence: float
    ambiguous: bool = False


NIL = Link(None, None, 0.0)


class LinkChoice(BaseModel):
    mention_index: int = Field(description="Số thứ tự mục như đầu vào (từ 1)")
    candidate_id: str | None = Field(default=None, description="id ứng viên đúng nghĩa, chép đúng trong ngoặc vuông; trống nếu không có")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class LinkChoices(BaseModel):
    """Bản ghi nội bộ: ứng viên được chọn cho từng mục."""

    items: list[LinkChoice] = Field(default_factory=lambda: list[LinkChoice]())


# shortcut: cache trong RAM của process, không giới hạn kích thước và mất khi restart; đổi sang Redis nếu chạy nhiều worker.
_cache: dict[tuple[str, str], Link] = {}


def _cache_key(slot: Slot) -> tuple[str, str]:
    return (slot.text_en or slot.text).strip().lower(), slot.slot


def decide_link(candidates: list[dict[str, Any]], object_type: str, candidate_id: str | None, confidence: float) -> Link:
    """LLM chọn trong danh sách (id lạ → NIL); dưới ngưỡng → NIL giữ chữ; top-1/top-2 điểm khớp tên sát nhau → nhận nhưng ambiguous."""
    chosen = next((c for c in candidates if str(c["id"]) == str(candidate_id)), None) if candidate_id else None
    if chosen is None or confidence < ACCEPT_CONFIDENCE:
        return NIL
    scores = sorted((float(c.get("score", 0.0)) for c in candidates), reverse=True)
    ambiguous = len(scores) > 1 and scores[0] - scores[1] < AMBIGUOUS_GAP
    return Link(f"{object_type}:{chosen['id']}", str(chosen["name"]), confidence, ambiguous)


def _from_exact(object_type: str, result: dict[str, Any]) -> Link | None:
    xref = result.get("xref")
    if isinstance(xref, dict):
        return Link(f"{xref['type']}:{xref['id']}", str(xref["name"]), 1.0)
    exact = result.get("exact")
    return Link(f"{object_type}:{exact['id']}", str(exact["name"]), 1.0) if isinstance(exact, dict) else None


async def _fetch(pending: list[tuple[int, str, Slot]]) -> list[dict[str, Any]]:
    mentions = [{"text": s.text, "text_en": s.text_en, "object_type": t} for _, t, s in pending]
    return await get_knowledge_client().get_link_candidates(mentions)


# shortcut: chưa link lên node cha `IS_A` khi dưới ngưỡng (giữ NIL); thêm khi có truy vấn cha trong knowledge.
async def link_entities(ctx: AgentContext, slots: list[Slot]) -> list[Link]:
    """Một Link cho mỗi slot, cùng thứ tự. Khớp chính xác thì nhận luôn; còn lại một lượt LLM chọn trong danh sách ứng viên."""
    links: list[Link] = [NIL] * len(slots)
    pending: list[tuple[int, str, Slot]] = []
    for i, slot in enumerate(slots):
        object_type = _OBJECT_TYPE.get(slot.slot)
        if object_type is None:
            continue
        cached = _cache.get(_cache_key(slot))
        if cached is not None:
            links[i] = cached
        else:
            pending.append((i, object_type, slot))
    if not pending:
        return links

    to_choose: list[tuple[int, str, Slot, list[dict[str, Any]]]] = []
    dermo: list[tuple[int, str, Slot]] = []
    for (i, object_type, slot), result in zip(pending, await _fetch(pending), strict=True):
        link = _from_exact(object_type, result)
        if link is not None:
            links[i] = _cache.setdefault(_cache_key(slot), link)
        elif result.get("candidates"):
            to_choose.append((i, object_type, slot, list(result["candidates"])))
        elif slot.slot in _DERMO_FALLBACK:
            dermo.append((i, "dermo", slot))

    if dermo:
        for (i, object_type, slot), result in zip(dermo, await _fetch(dermo), strict=True):
            link = _from_exact(object_type, result)
            if link is not None:
                links[i] = _cache.setdefault(_cache_key(slot), link)

    if not to_choose:
        return links
    blocks = "\n".join(
        f"mention_index {n}: {slot.text} / {slot.text_en or '-'} (loại: {object_type})\n" + "\n".join(f"    [{c['id']}] {c['name']}" for c in cands)
        for n, (_, object_type, slot, cands) in enumerate(to_choose, 1)
    )
    try:
        choices = await invoke_structured_with_retry(ctx, LinkChoices, [SystemMessage(content=LINK_CHOOSE), HumanMessage(content=blocks)])
    except Exception as exc:  # noqa: BLE001  # LLM lỗi: các mục này giữ dạng chữ, không làm hỏng lượt
        logger.warning("không chọn được node cho %d mention: %s", len(to_choose), exc)
        return links
    picked = {c.mention_index: c for c in choices.items}
    for n, (i, object_type, slot, cands) in enumerate(to_choose, 1):
        choice = picked.get(n)
        if choice is None:
            logger.warning("LLM bỏ sót mục '%s' khi chọn node", slot.text)
            continue
        if choice.candidate_id and not any(str(c["id"]) == choice.candidate_id for c in cands):
            logger.warning("LLM chọn id '%s' ngoài danh sách cho '%s'", choice.candidate_id, slot.text)
        links[i] = _cache.setdefault(_cache_key(slot), decide_link(cands, object_type, choice.candidate_id, choice.confidence))
    return links
