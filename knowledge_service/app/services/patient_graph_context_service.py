import logging
from typing import Any, LiteralString

from app.dto.patient_fact import (
    BookEvidence,
    CandidateDisease,
    DiscriminatingQuestion,
    MatchedFact,
    PatientFactOutput,
    PatientGraphContextOutput,
)
from app.services.document_graph_service import DocumentGraphService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.patient_fact_graph_service import DRUG, HISTORY, PatientFactGraphService
from app.services.patient_fact_relations import get_expansion_relations

logger = logging.getLogger(__name__)

MAX_SEEDS = 20
POOL = 12  # số ứng viên lấy từ graph trước khi trừ điểm phủ định
# Mỗi triệu chứng người bệnh nói KHÔNG có mà bệnh thường có thì trừ chừng này (bằng khoảng một triệu chứng đặc hiệu); trừ điểm chứ không loại hẳn
# vì cạnh phủ định của đồ thị nền thưa.
ABSENT_PENALTY = 2.0
BOOK_EVIDENCE_PER_DISEASE = 3
_PRIMEKG_TYPES = ("effect/phenotype", "disease", "drug", "exposure")
# Mở rộng từ dữ kiện bệnh nhân luôn dùng cả cạnh trích từ sách (không phụ thuộc `KG_EDGE_SOURCES` toàn cục, mặc định chỉ "KG"): chỉ PrimeKG thì ứng viên
# toàn bệnh hiếm không thuộc da liễu (đo 2026-11-12: ngứa + ban đỏ + mụn nước ra epidermolysis bullosa, Hennekam-Beemer; thêm cạnh sách ra dermatitis herpetiformis, atopic dermatitis, scabies).
EDGE_SOURCES = ["KG", "DOC"]

_RESOLVE_SEEDS: LiteralString = """
UNWIND $pairs AS p
MATCH (n:Entity {type: p.type, id: p.id})
RETURN elementId(n) AS eid, n.type AS type, n.id AS id, n.name AS name
"""

# Mở rộng theo cạnh viết thẳng trong pattern (không `type(r) IN ...`) để Neo4j chỉ duyệt đúng loại cạnh; cạnh `PT_*` của bệnh nhân không bao giờ khớp.
# Trọng số như `kg_intent_service._CANDIDATE_QUERY` (`3 / ln(2 + degree)`: triệu chứng nối ít bệnh thì đặc hiệu hơn), thêm nhánh tiếp xúc.
_CANDIDATES: LiteralString = """
UNWIND $seed_ids AS sid
MATCH (s:Entity) WHERE elementId(s) = sid
WITH collect(s) AS seeds
CALL (seeds) {
  UNWIND seeds AS s
  WITH s WHERE s.type = 'effect/phenotype'
  MATCH (s)-[e:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'}) WHERE coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 3.0 / log(2.0 + COUNT { (s)-[x:DISEASE_PHENOTYPE_POSITIVE]-() WHERE coalesce(x.source, 'KG') IN $edge_sources }) AS w,
         'triệu chứng: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'disease'
  MATCH (s)-[e:DISEASE_DISEASE]-(d:Entity {type: 'disease'}) WHERE d <> s AND coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 1.0 AS w, 'liên quan tới bệnh nền/tiền sử: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'drug'
  MATCH (s)-[e:INDICATION]-(d:Entity {type: 'disease'}) WHERE coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 1.0 AS w, 'thuốc đang dùng ' + s.name + ' chỉ định cho bệnh này' AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'exposure'
  MATCH (s)-[e:EXPOSURE_DISEASE]-(d:Entity {type: 'disease'}) WHERE coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 1.0 AS w, 'tiếp xúc: ' + s.name AS via
}
WITH d, seeds, sum(w) AS score, collect(DISTINCT via)[..4] AS why
WHERE NOT d IN seeds
RETURN d.id AS id, d.name AS name, score, why
ORDER BY score DESC
LIMIT $pool
"""

_ABSENT_PHENOTYPES: LiteralString = """
UNWIND $absent_ids AS aid
MATCH (p:Entity) WHERE elementId(p) = aid
MATCH (p)-[e:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'}) WHERE d.name IN $names AND coalesce(e.source, 'KG') IN $edge_sources
RETURN d.name AS name, collect(DISTINCT p.name) AS absent
"""

_DRUG_EFFECTS: LiteralString = """
MATCH (d:Entity) WHERE elementId(d) IN $drug_ids
MATCH (p:Entity) WHERE elementId(p) IN $symptom_ids
MATCH (d)-[e:DRUG_EFFECT]-(p) WHERE coalesce(e.source, 'KG') IN $edge_sources
RETURN DISTINCT d.name AS drug, p.name AS symptom
"""

_CONTRAINDICATIONS: LiteralString = """
MATCH (d:Entity) WHERE elementId(d) IN $drug_ids
MATCH (c:Entity {type: 'disease'}) WHERE c.name IN $names
MATCH (d)-[e:CONTRAINDICATION]-(c) WHERE coalesce(e.source, 'KG') IN $edge_sources
RETURN DISTINCT d.name AS drug, c.name AS disease
"""


async def resolve_node_pairs(kg: KnowledgeGraphService, pairs: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(type, id) → nút đồ thị (có `eid`); cặp không còn trong đồ thị thì vắng mặt."""
    rows = await kg.run(_RESOLVE_SEEDS, pairs=pairs) if pairs else []
    return {(r["type"], r["id"]): r for r in rows}


async def rank_diseases(kg: KnowledgeGraphService, positive_eids: list[str], absent_eids: list[str], top_k: int) -> list[dict[str, Any]]:
    """Bệnh ứng viên từ nút đã khớp: điểm đặc hiệu `3 / ln(2 + degree)`, trừ `ABSENT_PENALTY` mỗi triệu chứng bị phủ định; dùng chung cho tab bác sĩ và agent v3."""
    if not positive_eids:
        return []
    rows = await kg.run(_CANDIDATES, edge_sources=EDGE_SOURCES, seed_ids=positive_eids, pool=POOL)
    absent_by_disease: dict[str, list[str]] = {}
    if absent_eids and rows:
        for r in await kg.run(_ABSENT_PHENOTYPES, edge_sources=EDGE_SOURCES, absent_ids=absent_eids, names=[r["name"] for r in rows]):
            absent_by_disease[r["name"]] = r["absent"]
    scored = [
        {"id": r.get("id"), "name": r["name"], "score": round(r["score"] - ABSENT_PENALTY * len(absent_by_disease.get(r["name"], [])), 3),
         "why": r["why"], "absent": absent_by_disease.get(r["name"], [])}
        for r in rows
    ]
    return sorted((c for c in scored if c["score"] > 0), key=lambda c: c["score"], reverse=True)[:top_k]


async def get_drug_notes(kg: KnowledgeGraphService, drug_eids: list[str], symptom_eids: list[str], diseases: list[str]) -> list[str]:
    """Thuốc đang dùng có thể gây triệu chứng đang có, hoặc chống chỉ định với bệnh ứng viên (theo tên)."""
    if not drug_eids:
        return []
    notes: list[str] = []
    if symptom_eids:
        for r in await kg.run(_DRUG_EFFECTS, edge_sources=EDGE_SOURCES, drug_ids=drug_eids, symptom_ids=symptom_eids):
            notes.append(f"Thuốc đang dùng {r['drug']} có thể gây {r['symptom']} (tác dụng phụ ghi trong đồ thị).")
    if diseases:
        for r in await kg.run(_CONTRAINDICATIONS, edge_sources=EDGE_SOURCES, drug_ids=drug_eids, names=diseases):
            notes.append(f"Thuốc đang dùng {r['drug']} chống chỉ định với {r['disease']} (bệnh ứng viên).")
    return notes


def _is_taking_drug(fact: PatientFactOutput) -> bool:
    return fact.relation == DRUG and fact.kind != "allergy"


class PatientGraphContextService:
    def __init__(self, facts: PatientFactGraphService, kg: KnowledgeGraphService, docs: DocumentGraphService) -> None:
        self._facts = facts
        self._kg = kg
        self._docs = docs

    async def get_context(self, patient_id: str, top_k: int = 5) -> PatientGraphContextOutput:
        """Từ fact `current` đã khớp nút → bệnh ứng viên, triệu chứng nên hỏi tiếp, ghi chú thuốc và trích dẫn sách. Chỉ là gợi ý, không phải chẩn đoán."""
        state = await self._facts.get_current_facts(patient_id)
        notes: list[str] = []
        usable = [
            f for f in state.facts
            if f.kg_node_id and f.object_type in _PRIMEKG_TYPES and (get_expansion_relations(f.relation, f.present is not False))
            and (f.relation != DRUG or _is_taking_drug(f)) and not (f.relation == HISTORY and f.of == "family")
        ]
        unmatched = [f.label for f in state.facts if not f.kg_node_id and f.relation != "PT_HAS_ATTRIBUTE"]
        matched = [
            MatchedFact(label=f.label, kg_name=f.kg_name, object_type=f.object_type, present=f.present is not False, relation=f.relation) for f in usable
        ]
        if len(usable) > MAX_SEEDS:
            notes.append(f"Chỉ dùng {MAX_SEEDS}/{len(usable)} dữ kiện mới nhất để mở rộng.")
            usable = usable[-MAX_SEEDS:]
        nodes = await self._resolve_nodes(usable)
        if not nodes:
            notes.append("Chưa có dữ kiện nào khớp nút đồ thị tri thức nên chưa mở rộng được.")
            return PatientGraphContextOutput(matched=matched, unmatched=unmatched, candidates=[], questions=[], drug_notes=[], book_evidence=[], notes=notes)

        positive = [n for f, n in nodes if f.present is not False]
        absent = [n for f, n in nodes if f.present is False and f.object_type == "effect/phenotype"]
        candidates = await self._get_candidates(positive, absent, top_k)
        names = [c.name for c in candidates]
        symptoms = [n for f, n in nodes if f.present is not False and f.object_type == "effect/phenotype"]
        drugs = [n for f, n in nodes if f.object_type == "drug"]
        return PatientGraphContextOutput(
            matched=matched,
            unmatched=unmatched,
            candidates=candidates,
            questions=await self._get_questions(names[:3], [n["id"] for _, n in nodes if n["type"] == "effect/phenotype"]),
            drug_notes=await self._get_drug_notes(drugs, symptoms, names),
            book_evidence=await self._get_book_evidence(names[:3]),
            notes=notes,
        )

    async def _resolve_nodes(self, facts: list[PatientFactOutput]) -> list[tuple[PatientFactOutput, dict[str, Any]]]:
        by_key = await resolve_node_pairs(self._kg, [{"type": f.object_type, "id": f.kg_node_id} for f in facts if f.kg_node_id])
        resolved = [(f, by_key[(f.object_type, f.kg_node_id)]) for f in facts if f.kg_node_id and (f.object_type, f.kg_node_id) in by_key]
        for f in facts:
            if (f.object_type, f.kg_node_id) not in by_key:
                logger.warning("patient-graph-context: nút %s (%s) của fact '%s' không còn trong đồ thị", f.kg_node_id, f.object_type, f.label)
        return resolved

    async def _get_candidates(self, positive: list[dict[str, Any]], absent: list[dict[str, Any]], top_k: int) -> list[CandidateDisease]:
        ranked = await rank_diseases(self._kg, [n["eid"] for n in positive], [n["eid"] for n in absent], top_k)
        return [CandidateDisease(name=c["name"], score=c["score"], why=c["why"], absent=c["absent"]) for c in ranked]

    async def _get_questions(self, diseases: list[str], known_phenotype_ids: list[str]) -> list[DiscriminatingQuestion]:
        if len(diseases) < 2:
            return []
        result = await self._kg.discriminating_questions(diseases, known_phenotype_ids, top_k=3)
        return [DiscriminatingQuestion(phenotype=q["phenotype"], present_in=q["present_in"], absent_in=q["absent_in"]) for q in result["questions"]]

    async def _get_drug_notes(self, drugs: list[dict[str, Any]], symptoms: list[dict[str, Any]], diseases: list[str]) -> list[str]:
        return await get_drug_notes(self._kg, [d["eid"] for d in drugs], [s["eid"] for s in symptoms], diseases)

    async def _get_book_evidence(self, diseases: list[str]) -> list[BookEvidence]:
        evidence: list[BookEvidence] = []
        for name in diseases:
            rows = await self._docs.query_document_graph(name, None, BOOK_EVIDENCE_PER_DISEASE)
            for r in rows:
                if r.get("evidence"):
                    evidence.append(
                        BookEvidence(
                            disease=name, relation=str(r.get("display") or r.get("relation") or ""), object=str(r.get("object") or ""),
                            evidence=str(r["evidence"]), pages=list(r.get("pages") or []), document_id=r.get("document_id"),
                        )
                    )
        return evidence
