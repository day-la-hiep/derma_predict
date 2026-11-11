import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any, LiteralString

from app.dto.api import CaseInput, GraphEdgeOutput, GraphNodeOutput, PatientJourneyGraphOutput
from app.infra.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Nối phiên mới vào chuỗi thời gian NEXT với phiên liền trước
_UPSERT_SESSION: LiteralString = """
MERGE (p:Patient {id: $patient_id})
ON CREATE SET p.gender = $gender, p.dob = $dob
MERGE (s:ConsultationSession {id: $session_id})
ON CREATE SET s.date = $session_date
MERGE (p)-[:HAD_SESSION]->(s)
WITH p, s
OPTIONAL MATCH (p)-[:HAD_SESSION]->(prev:ConsultationSession)
WHERE prev.id <> s.id AND prev.date < s.date
WITH s, prev ORDER BY prev.date DESC LIMIT 1
FOREACH (_ IN CASE WHEN prev IS NOT NULL THEN [1] ELSE [] END |
    MERGE (prev)-[:NEXT]->(s)
)
"""

_UPSERT_FACTS: LiteralString = """
MATCH (s:ConsultationSession {id: $session_id})
UNWIND $facts AS f
MERGE (fact:ClinicalFact {id: f.id})
SET fact.name = f.label, fact.type = f.fact_type, fact.detail = f.detail, fact.status = 'active'
MERGE (s)-[r:REPORTED_FACT]->(fact)
SET r.fact_type = f.fact_type
WITH fact
OPTIONAL MATCH (d:DermoTerm)
WHERE NOT d.is_obsolete AND toLower(d.name) = toLower(fact.name)
FOREACH (_ IN CASE WHEN d IS NOT NULL THEN [1] ELSE [] END |
    MERGE (fact)-[:MAPS_TO]->(d)
)
"""

_RESOLVE_SESSION: LiteralString = """
MATCH (s:ConsultationSession {id: $session_id})
SET s.status = 'resolved', s.notes = $notes, s.resolved_at = $resolved_at
WITH s
FOREACH (_ IN CASE WHEN $condition <> '' THEN [1] ELSE [] END |
    MERGE (c:SuspectedCondition {name: $condition})
    MERGE (s)-[:SUSPECTED_CONDITION {by_doctor_id: $doctor_id}]->(c)
)
"""

_UPSERT_ADVICE: LiteralString = """
MATCH (s:ConsultationSession {id: $session_id})
UNWIND $instructions AS inst
MERGE (a:Advice {content: inst})
MERGE (s)-[:RECOMMENDED_ADVICE]->(a)
"""

_UPSERT_IMAGES: LiteralString = """
MATCH (s:ConsultationSession {id: $session_id})
UNWIND $images AS img
MERGE (pi:PatientImage {id: img.file_id})
SET pi.body_site = coalesce(img.body_site, pi.body_site, ''),
    pi.description = coalesce(img.description, pi.description, ''),
    pi.confirmed_label = img.confirmed_label
MERGE (s)-[:HAS_IMAGE]->(pi)
WITH pi, img
FOREACH (_ IN CASE WHEN img.confirmed_label IS NOT NULL AND img.confirmed_label <> '' THEN [1] ELSE [] END |
    MERGE (c:SuspectedCondition {name: img.confirmed_label})
    MERGE (pi)-[:CONFIRMED_AS]->(c)
)
"""

_HISTORY_HINTS: LiteralString = """
MATCH (:Patient {id: $patient_id})-[:HAD_SESSION]->(s:ConsultationSession)
OPTIONAL MATCH (s)-[:SUSPECTED_CONDITION]->(c:SuspectedCondition)
OPTIONAL MATCH (s)-[:RECOMMENDED_ADVICE]->(a:Advice)
WITH s, collect(DISTINCT c.name) AS conditions, collect(DISTINCT a.content) AS advice
ORDER BY s.resolved_at DESC
RETURN conditions, advice
"""

_JOURNEY: LiteralString = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (p)-[r_sess:HAD_SESSION]->(s:ConsultationSession)
OPTIONAL MATCH (s)-[r_next:NEXT]->(s_next:ConsultationSession)
OPTIONAL MATCH (s)-[r_fact:REPORTED_FACT]->(f:ClinicalFact)
OPTIONAL MATCH (f)-[r_dermo:MAPS_TO]->(d:DermoTerm)
OPTIONAL MATCH (s)-[r_cond:SUSPECTED_CONDITION]->(c:SuspectedCondition)
OPTIONAL MATCH (s)-[r_adv:RECOMMENDED_ADVICE]->(a:Advice)
OPTIONAL MATCH (s)-[r_img:HAS_IMAGE]->(img:PatientImage)
OPTIONAL MATCH (img)-[r_evi:EVIDENCES]->(img_fact:ClinicalFact)
OPTIONAL MATCH (img)-[r_conf:CONFIRMED_AS]->(img_cond:SuspectedCondition)
RETURN p, s, s_next, f, d, c, a, img, img_fact, img_cond,
       r_sess, r_next, r_fact, r_dermo, r_cond, r_adv, r_img, r_evi, r_conf
"""


def get_stable_id(prefix: str, content: str) -> str:
    return f"{prefix}-{hashlib.sha256(content.encode()).hexdigest()[:12]}"


def get_node_name(raw: dict[str, Any], label: str, node_id: str) -> str:
    if label == "ConsultationSession":
        date_part = str(raw.get("date") or "").split("T")[0]
        return str(raw.get("name") or (f"Phiên {date_part}" if date_part else "Phiên tư vấn"))
    if label == "Patient":
        name = str(raw.get("name") or raw.get("full_name") or "")
        return name if name and not name.startswith("pp-") else "Bệnh nhân"
    if label == "PatientImage":
        parts = [p for p in (raw.get("body_site"), raw.get("confirmed_label")) if p]
        return f"Ảnh da ({', '.join(parts)})" if parts else "Ảnh da"
    return str(raw.get("name") or raw.get("content") or raw.get("summary") or node_id)


class JourneyGraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNodeOutput] = {}
        self.edges: dict[str, GraphEdgeOutput] = {}
        self._images_by_session: dict[str, list[dict[str, Any]]] = {}
        self._next_pairs: set[tuple[str, str]] = set()

    def add_node(self, raw: dict[str, Any] | None, label: str) -> None:
        node_id = str((raw or {}).get("id") or (raw or {}).get("content") or (raw or {}).get("name") or "")
        if raw and node_id and node_id not in self.nodes:
            self.nodes[node_id] = GraphNodeOutput(id=node_id, label=label, name=get_node_name(raw, label, node_id), properties=raw)

    def add_edge(self, source: str, target: str, rel_type: str, props: dict[str, Any] | None = None) -> None:
        edge_id = f"{source}-{rel_type}-{target}"
        if source and target and edge_id not in self.edges:
            self.edges[edge_id] = GraphEdgeOutput(id=edge_id, source=source, target=target, type=rel_type, properties=props or {})

    def add_named_node(self, prefix: str, label: str, name: str) -> str:
        node_id = get_stable_id(prefix, name)
        self.add_node({"id": node_id, "name": name}, label)
        return node_id

    def add_row(self, row: dict[str, Any]) -> None:
        p, s, s_next, f, d = (row.get(k) for k in ("p", "s", "s_next", "f", "d"))
        c, a, img, img_fact, img_cond = (row.get(k) for k in ("c", "a", "img", "img_fact", "img_cond"))
        s_id = str(s.get("id")) if s else ""

        self.add_node(p, "Patient")
        if s:
            self.add_node(s, "ConsultationSession")
            if p:
                self.add_edge(str(p.get("id")), s_id, "HAD_SESSION")
        if s and s_next:
            self.add_node(s_next, "ConsultationSession")
            self.add_edge(s_id, str(s_next.get("id")), "NEXT")
            self._next_pairs.add((s_id, str(s_next.get("id"))))
        if s and f:
            fact_type = f.get("type", "symptom")
            self.add_node(f, {"symptom": "Symptom", "lesion": "Lesion"}.get(fact_type, "ClinicalFact"))
            self.add_edge(s_id, str(f.get("id")), "REPORTED_FACT", {"fact_type": fact_type})
        if f and d:
            self.add_node(d, "DermoTerm")
            self.add_edge(str(f.get("id")), str(d.get("id") or d.get("name")), "MAPS_TO")
        if s and c:
            self.add_edge(s_id, self.add_named_node("cond", "SuspectedCondition", str(c.get("name") or "")), "SUSPECTED_CONDITION")
        if s and a:
            self.add_edge(s_id, self.add_named_node("adv", "Advice", str(a.get("content") or "")), "RECOMMENDED_ADVICE")
        if s and img:
            self.add_node(dict(img), "PatientImage")
            self.add_edge(s_id, str(img.get("id")), "HAS_IMAGE")
            images = self._images_by_session.setdefault(s_id, [])
            if not any(i.get("id") == img.get("id") for i in images):
                images.append(dict(img))
        if img and img_fact:
            self.add_edge(str(img.get("id")), str(img_fact.get("id")), "EVIDENCES")
        if img and img_cond:
            self.add_edge(str(img.get("id")), self.add_named_node("cond", "SuspectedCondition", str(img_cond.get("name") or "")), "CONFIRMED_AS")

    def add_progress_edges(self) -> None:
        """Nối FOLLOWS giữa các ảnh cùng vị trí cơ thể ở hai phiên kế tiếp."""
        for prev_id, next_id in self._next_pairs:
            for prev_img in self._images_by_session.get(prev_id, []):
                site = (prev_img.get("body_site") or "").strip().lower()
                for next_img in self._images_by_session.get(next_id, []):
                    if site and site == (next_img.get("body_site") or "").strip().lower():
                        self.add_edge(str(prev_img.get("id")), str(next_img.get("id")), "FOLLOWS", {"body_site": site})


class PatientJourneyService:
    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    async def sync_case(self, case: CaseInput) -> None:
        """Ghi một ca đã chốt vào đồ thị trong một transaction; MERGE nên gọi lại nhiều lần vẫn an toàn."""
        if not case.patient_profile_id:
            return
        patient, assessment = case.snapshot.patient_profile, case.snapshot.assessment
        session_id = case.visit_id
        facts = [
            {"id": f"{session_id}:{i}", "label": f.label or "Dữ kiện lâm sàng", "fact_type": f.fact_type, "detail": f.detail}
            for i, f in enumerate(case.snapshot.clinical_facts)
        ]
        instructions = [i.strip() for i in assessment.instructions if i and i.strip()]
        images = [
            {"file_id": i.file_id, "body_site": i.body_site, "description": i.description, "confirmed_label": i.confirmed_label or ""}
            for i in case.images if i.file_id
        ]
        statements: list[tuple[LiteralString, dict[str, Any]]] = [
            (_UPSERT_SESSION, {
                "patient_id": case.patient_profile_id, "gender": patient.gender, "dob": patient.dob.isoformat() if patient.dob else "",
                "session_id": session_id, "session_date": case.created_at.isoformat(),
            }),
            (_RESOLVE_SESSION, {
                "session_id": session_id, "doctor_id": case.doctor_id or "", "condition": case.diagnosis.strip(),
                "notes": case.notes.strip(), "resolved_at": datetime.now(UTC).isoformat(),
            }),
        ]
        if facts:
            statements.insert(1, (_UPSERT_FACTS, {"session_id": session_id, "facts": facts}))
        if instructions:
            statements.append((_UPSERT_ADVICE, {"session_id": session_id, "instructions": instructions}))
        if images:
            statements.append((_UPSERT_IMAGES, {"session_id": session_id, "images": images}))
        await asyncio.to_thread(self._neo4j.write_sync, statements)

    async def get_history_hints(self, patient_id: str) -> tuple[list[str], list[str]]:
        """(nhận định, lời khuyên) bác sĩ đã chốt ở các phiên trước, mới nhất trước."""
        rows = await self._neo4j.run(_HISTORY_HINTS, patient_id=patient_id)
        return (
            list(dict.fromkeys(c for r in rows for c in r["conditions"])),
            list(dict.fromkeys(a for r in rows for a in r["advice"])),
        )

    async def get_journey_graph(self, patient_id: str) -> PatientJourneyGraphOutput:
        try:
            rows = await self._neo4j.run(_JOURNEY, patient_id=patient_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lỗi truy vấn đồ thị bệnh nhân %s từ Neo4j: %s", patient_id, exc)
            rows = []
        builder = JourneyGraphBuilder()
        for row in rows:
            builder.add_row(row)
        builder.add_progress_edges()
        return PatientJourneyGraphOutput(patient_id=patient_id, nodes=list(builder.nodes.values()), edges=list(builder.edges.values()))
