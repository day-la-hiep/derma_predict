import json
import logging
from functools import cache
from pathlib import Path
from typing import Any

from app.deps import get_knowledge_client
from app.state.v3.diagnosis import Hypothesis
from app.state.v3.facts import Fact
from app.tools.v3.ids import to_node_ref

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parents[3] / "data" / "v3" / "red_flags.json"
URGENT_TOP_N = 3
_LEVEL = {"routine": 0, "soon": 1, "urgent": 2}


@cache
def load_rules() -> dict[str, Any]:
    return json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def _group_hit(group: dict[str, Any], facts: list[Fact]) -> bool:
    ids = set(group.get("ids") or [])
    keywords = [k.lower() for k in group.get("keywords") or []]
    return any(
        f.assertion == "present" and (f.node_id in ids or any(k in f"{f.text} {f.text_en}".lower() for k in keywords))
        for f in facts
    )


def check_red_flags(facts: list[Fact], hypotheses: list[Hypothesis], recent_drugs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Luật cứng, không LLM: bệnh nguy hiểm lọt top đầu, hoặc đủ một tổ hợp dấu hiệu."""
    rules = load_rules()
    flags: list[dict[str, str]] = []
    urgent = {d["id"]: d["name"] for d in rules["urgent_diseases"]}
    for hyp in hypotheses[:URGENT_TOP_N]:
        if hyp.disease_id in urgent:
            flags.append({"name": f"nghi {urgent[hyp.disease_id]}", "reason": f"{hyp.name} nằm trong {URGENT_TOP_N} giả thuyết đầu", "urgency": "urgent"})
    has_drug = bool(recent_drugs) or any(f.slot == "drug" and f.assertion == "present" for f in facts)
    hits = {name: _group_hit(group, facts) for name, group in rules["symptom_groups"].items()} | {"recent_drug": has_drug}
    for combo in rules["combos"]:
        if all(hits.get(part, False) for part in combo["all"]):
            flags.append({"name": combo["name"], "reason": " + ".join(combo["all"]), "urgency": combo["urgency"]})
    return flags


async def get_drug_flags(facts: list[Fact], recent_drugs: list[dict[str, Any]], hypotheses: list[Hypothesis]) -> list[dict[str, str]]:
    """Thuốc đang dùng có thể gây triệu chứng hiện có hoặc chống chỉ định với bệnh ứng viên (theo đồ thị): mức `soon`, không phải cấp cứu."""
    drug_ids = [d["drug_id"] for d in recent_drugs if d.get("drug_id")] + [f.node_id for f in facts if f.slot == "drug" and f.assertion == "present" and f.node_id]
    drugs = [ref for d in dict.fromkeys(drug_ids) if (ref := to_node_ref(d))]
    if not drugs:
        return []
    symptoms = [ref for f in facts if f.assertion == "present" and f.node_id and f.node_id.startswith("effect/phenotype:") and (ref := to_node_ref(f.node_id))]
    notes = await get_knowledge_client().get_drug_notes(drugs, symptoms, [h.name for h in hypotheses[:URGENT_TOP_N]])
    return [{"name": "lưu ý thuốc", "reason": note, "urgency": "soon"} for note in notes]


def get_urgency(flags: list[dict[str, str]]) -> str:
    return max((f["urgency"] for f in flags), key=lambda u: _LEVEL.get(u, 0), default="routine")
