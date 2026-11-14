from typing import Any

from app.deps import get_knowledge_client
from app.state.v3.facts import Fact
from app.tools.v3.ids import to_node_ref


async def kg_rank_diseases(facts: list[Fact], top_k: int = 12) -> list[dict[str, Any]]:
    """Fact có node PrimeKG: present làm seed, absent trừ điểm; family / history không đưa vào (không phải triệu chứng hiện tại)."""
    present = [ref for f in facts if f.assertion == "present" and f.node_id and (ref := to_node_ref(f.node_id))]
    absent = [ref for f in facts if f.assertion == "absent" and f.node_id and (ref := to_node_ref(f.node_id))]
    if not present:
        return []
    rows = await get_knowledge_client().rank_diseases(present, absent, top_k)
    return [{"disease_id": f"disease:{r['id']}", "name": r["name"], "score": r["score"], "why": r.get("why", [])} for r in rows if r.get("id")]
