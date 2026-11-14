import logging
from typing import Any

from app.deps import get_knowledge_client
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact
from app.tools.v3.ids import split_node_id

logger = logging.getLogger(__name__)

DISCRIMINATE_TOP = 3
# shortcut: lọc theo từ khoá các phenotype HPO người bệnh không tự trả lời được (di truyền, mô bệnh học, xét nghiệm, giải phẫu bất thường).
_NOT_ASKABLE = ("inheritance", "abnormal", "concentration", "infiltrate", "morphology", "level", "hyperkeratosis", "parakeratosis",
                "orthokeratosis", "hypergranulosis", "acanthosis", "spongiosis", "histolog", "biopsy",
                # phenotype thần kinh / phát triển của bệnh hiếm do KG đưa lên (đo thật: hỏi người bệnh vảy nến về "khả năng học tập")
                "intellectual", "developmental", "delay", "disability", "seizure", "growth", "infantile", "congenital")


def is_askable(name: str) -> bool:
    lowered = name.lower()
    return not any(k in lowered for k in _NOT_ASKABLE)


async def select_discriminator(
    facts: list[Fact], ambiguous: list[dict[str, Any]], hypotheses: list[Hypothesis], evidence: list[EvidenceRow], asked: list[str],
) -> dict[str, Any] | None:
    """Câu hỏi tiếp theo, theo thứ tự: mâu thuẫn ảnh/lời kể > link chưa chắc > phenotype phân biệt (đồ thị) > dấu hiệu còn thiếu của bệnh đầu."""
    asked_set = set(asked)
    for fact in facts:
        key = f"conflict:{fact.slot}:{fact.node_id or fact.text}"
        if fact.conflict and key not in asked_set:
            return {"node_id": key, "text": f"{fact.slot}: {fact.text}", "kind": "conflict"}
    for item in ambiguous:
        key = f"ambiguous:{item.get('node_id') or item.get('text')}"
        if key not in asked_set:
            return {"node_id": key, "text": f"{item['text']} (có phải là {item.get('node_name')}?)", "kind": "ambiguous"}
    top = [h.disease_id for h in hypotheses[:DISCRIMINATE_TOP]]
    if len(top) >= 2:
        known = [split_node_id(f.node_id)[1] for f in facts if f.node_id and f.node_id.startswith("effect/phenotype:")]
        known += [split_node_id(a)[1] for a in asked if a.startswith("effect/phenotype:")]
        try:
            data = await get_knowledge_client().get_discriminating_questions_by_ids([split_node_id(d)[1] for d in top], known, top_k=5)
        except Exception as exc:  # noqa: BLE001  # đồ thị lỗi: vẫn còn dấu hiệu thiếu của bệnh đầu
            logger.warning("select_discriminator: không lấy được câu hỏi phân biệt: %s", exc)
            data = {"questions": []}
        for q in data.get("questions", []):
            node_id = f"effect/phenotype:{q['primekg_id']}"
            if node_id not in asked_set and is_askable(q["phenotype"]):
                return {"node_id": node_id, "text": q["phenotype"], "kind": "discriminate",
                        "present_in": [f"disease:{d}" for d in q.get("present_in", [])], "absent_in": [f"disease:{d}" for d in q.get("absent_in", [])]}
    row = next((r for r in evidence if hypotheses and r.disease_id == hypotheses[0].disease_id), None)
    for node_id in (row.missing if row else []):
        if node_id not in asked_set and row and is_askable(row.names.get(node_id, "")):
            return {"node_id": node_id, "text": row.names.get(node_id, node_id) if row else node_id, "kind": "missing"}
    return None
