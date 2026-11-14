from datetime import datetime, timezone
from typing import Any

from app.state.v3.facts import Fact

_NODE_TYPES = ("effect/phenotype", "disease", "drug", "exposure", "dermo")


def build_node_id(object_type: str, node_id: str | None) -> str | None:
    return f"{object_type}:{node_id}" if node_id and object_type in _NODE_TYPES else None


def _slot(fact: dict[str, Any]) -> str:
    if fact.get("object_type") in ("drug", "disease"):
        return str(fact["object_type"])
    return {1: "symptom", 2: "morphology"}.get(fact.get("category") or 0) or fact.get("name") or "other"


def _time(fact: dict[str, Any], now: datetime) -> datetime:
    for key in ("observed_at", "last_confirmed_at"):
        try:
            if fact.get(key):
                moment = datetime.fromisoformat(fact[key])
                return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return now


def load_history(graph_facts: list[dict[str, Any]], now: datetime) -> tuple[list[Fact], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fact hiện hành của graph theo dõi (`GET /internal/patient-facts/{id}`) → fact v3, bệnh tiền sử (khối 1), thuốc đang dùng (red flag)."""
    facts: list[Fact] = []
    diseases: list[dict[str, Any]] = []
    drugs: list[dict[str, Any]] = []
    for raw in graph_facts:
        object_type = raw.get("object_type") or ""
        node_id = build_node_id(object_type, raw.get("kg_node_id"))
        if raw.get("present") is False:
            assertion = "absent"
        elif raw.get("of") == "family":
            assertion = "family"
        elif object_type == "disease":
            assertion = "history"
        else:
            assertion = "present"
        fact = Fact(
            slot=_slot(raw), text=raw.get("label") or "", node_id=node_id, node_name=raw.get("kg_name") or None, source="history",
            assertion=assertion, time=_time(raw, now), provenance=[raw["id"]] if raw.get("id") else [],
        )
        facts.append(fact)
        if object_type == "disease" and assertion == "history":
            diseases.append({"disease_id": node_id, "name": fact.text, "time": fact.time.isoformat()})
        if object_type == "drug" and raw.get("kind") != "allergy" and assertion == "present":
            drugs.append({"drug_id": node_id, "name": fact.text, "time": fact.time.isoformat()})
    return facts, diseases, drugs
