import logging
import re
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher
from functools import cache
from typing import Any, LiteralString, cast

from app.dto.patient_fact import PatientFactInput
from app.infra.neo4j_client import Neo4jClient
from app.pipeline.document_ingest.graph_schema import ENTITY_TYPES
from app.services.knowledge_graph_service import name_variants

logger = logging.getLogger(__name__)

# Loại nút mà fact bệnh nhân có thể khớp vào; không có loại nào khác thì fact giữ dạng chữ
LINKABLE_TYPES = ("effect/phenotype", "disease", "drug", "exposure", "dermo")
_LABEL_BY_TYPE = {**{e.id: e.label for e in ENTITY_TYPES.values() if e.kg == "primekg"}, "dermo": "DermoTerm"}

# (nhãn người bệnh, loại nút) → tên tiếng Anh chuẩn; nhãn không dịch được thì vắng mặt
Translator = Callable[[list[tuple[str, str]]], Awaitable[dict[str, str]]]
# (nhãn, loại nút, tên các nút ứng viên) → {vị trí mục (từ 0): số ứng viên được chọn}; mục không có ứng viên đúng nghĩa thì vắng mặt
Chooser = Callable[[list[tuple[str, str, list[str]]]], Awaitable[dict[int, int]]]
_CANDIDATE_LIMIT = 6
# Khớp chứa chuỗi chỉ là gợi ý nên trần 0.6; độ giống tên (difflib, thư viện chuẩn thay rapidfuzz chưa cài) để xếp và so top-1/top-2.
_LOOSE_MAX_SCORE = 0.6
_HPO_XREF = re.compile(r"^HP:(\d+)")
_DERMO_XREFS: LiteralString = "MATCH (n:DermoTerm {id: $id}) RETURN n.xrefs AS xrefs"
_PHENOTYPE_BY_IDS: LiteralString = "MATCH (p:Entity {type: 'effect/phenotype'}) WHERE p.id IN $ids RETURN p.id AS id, p.name AS name ORDER BY p.id LIMIT 1"


def get_loose_score(query: str, name: str) -> float:
    return round(_LOOSE_MAX_SCORE * SequenceMatcher(None, query.lower(), name.lower()).ratio(), 3)


@cache
def build_exact_query(object_type: str) -> LiteralString:
    # Nhãn Neo4j không tham số hoá được: chỉ nhận loại trong bảng đóng
    if object_type == "dermo":
        return (
            "MATCH (n:DermoTerm) WHERE NOT coalesce(n.is_obsolete, false) "
            "AND (toLower(n.name) IN $names OR any(s IN coalesce(n.synonyms, []) WHERE toLower(s) IN $names)) "
            "RETURN n.id AS id, n.name AS name ORDER BY n.id LIMIT 1"
        )
    label = _LABEL_BY_TYPE.get(object_type)
    if label is None:
        raise ValueError(f"không được phép: {object_type}")
    return cast(LiteralString, f"MATCH (n:Entity:{label}) WHERE toLower(n.name) IN $names RETURN n.id AS id, n.name AS name ORDER BY n.id LIMIT 1")


@cache
def build_loose_query(object_type: str) -> LiteralString:
    if object_type == "dermo":
        return (
            "MATCH (n:DermoTerm) WHERE NOT coalesce(n.is_obsolete, false) "
            "AND (toLower(n.name) CONTAINS $name OR any(s IN coalesce(n.synonyms, []) WHERE toLower(s) CONTAINS $name)) "
            "RETURN n.id AS id, n.name AS name ORDER BY size(n.name), n.id LIMIT $limit"
        )
    label = _LABEL_BY_TYPE.get(object_type)
    if label is None:
        raise ValueError(f"không được phép: {object_type}")
    return cast(
        LiteralString, f"MATCH (n:Entity:{label}) WHERE toLower(n.name) CONTAINS $name RETURN n.id AS id, n.name AS name ORDER BY size(n.name), n.id LIMIT $limit"
    )


def _needs_link(fact: PatientFactInput) -> bool:
    return fact.kg_node_id is None and fact.object_type in LINKABLE_TYPES


class PatientFactLinker:
    def __init__(self, neo4j: Neo4jClient, translate: Translator | None = None, choose: Chooser | None = None) -> None:
        self._neo4j = neo4j
        self._translate = translate
        self._choose = choose

    async def _find_exact(self, object_type: str, name: str) -> str | None:
        names = sorted({v.strip().lower() for v in name_variants(name) if v.strip()})
        if not names:
            return None
        rows = await self._neo4j.run(build_exact_query(object_type), names=names)
        return rows[0]["id"] if rows else None

    async def find_link_candidates(self, text: str, text_en: str, object_type: str, limit: int = _CANDIDATE_LIMIT) -> dict[str, Any]:
        """Ứng viên nút cho một mention, không ghi gì. Điểm: khớp chính xác 1.0; chứa chuỗi tối đa 0.6, xếp theo độ giống tên."""
        for name in (text_en, text):
            names = sorted({v.strip().lower() for v in name_variants(name) if v.strip()}) if name else []
            if names:
                rows = await self._neo4j.run(build_exact_query(object_type), names=names)
                if rows:
                    exact = {"id": rows[0]["id"], "name": rows[0]["name"], "score": 1.0}
                    xref = await self._find_hpo_xref(rows[0]["id"]) if object_type == "dermo" else None
                    return {"exact": exact, "candidates": [exact], "xref": xref}
        query = (text_en or text).strip().lower()
        rows = await self._neo4j.run(build_loose_query(object_type), name=query, limit=limit) if query else []
        candidates = [{"id": r["id"], "name": r["name"], "score": get_loose_score(query, r["name"])} for r in rows]
        return {"exact": None, "candidates": sorted(candidates, key=lambda c: c["score"], reverse=True), "xref": None}

    async def _find_hpo_xref(self, dermo_id: str) -> dict[str, str] | None:
        """Term DermO có xref HPO mà PrimeKG có node phenotype tương ứng (id PrimeKG = số HPO bỏ số 0 đầu)."""
        rows = await self._neo4j.run(_DERMO_XREFS, id=dermo_id)
        hpo = [str(int(m.group(1))) for x in (rows[0]["xrefs"] if rows else None) or [] if (m := _HPO_XREF.match(str(x)))]
        if not hpo:
            return None
        found = await self._neo4j.run(_PHENOTYPE_BY_IDS, ids=hpo)
        return {"type": "effect/phenotype", "id": found[0]["id"], "name": found[0]["name"]} if found else None

    async def link_facts(self, facts: list[PatientFactInput]) -> int:
        """Điền `kg_node_id` cho fact khớp được; trả số fact vừa khớp. Chỉ khớp chính xác tên (trực tiếp, hoặc sau khi LLM dịch sang tên chuẩn): không khớp thì để trống, không đoán."""
        pending = [f for f in facts if _needs_link(f)]
        unmatched: list[PatientFactInput] = []
        linked = 0
        for fact in pending:
            node_id = await self._find_exact(fact.object_type, fact.label)
            if node_id is None:
                unmatched.append(fact)
                continue
            fact.kg_node_id, fact.link_method = node_id, "exact"
            linked += 1
        if unmatched and self._translate is not None:
            linked += await self._link_by_translation(unmatched)
        if pending:
            logger.info("patient-facts: khớp %d/%d fact vào đồ thị tri thức", linked, len(pending))
        return linked

    async def _link_by_translation(self, facts: list[PatientFactInput]) -> int:
        assert self._translate is not None
        try:
            english = await self._translate([(f.label, f.object_type) for f in facts])
        except Exception:  # noqa: BLE001  # LLM lỗi: fact giữ dạng chữ, không làm hỏng việc ghi
            logger.error("patient-facts: không dịch được %d nhãn để khớp nút", len(facts), exc_info=True)
            return 0
        linked = 0
        loose: list[tuple[PatientFactInput, list[dict[str, str]]]] = []
        for fact in facts:
            name = english.get(fact.label)
            node_id = await self._find_exact(fact.object_type, name) if name else None
            if node_id is not None:
                fact.kg_node_id, fact.link_method = node_id, "llm"
                linked += 1
                continue
            candidates = await self._find_candidates(fact.object_type, name) if name else []
            if candidates:
                loose.append((fact, candidates))
            else:
                logger.info("patient-facts: '%s' (%s) không khớp nút nào (dịch: %s)", fact.label, fact.object_type, name or "không có")
        if loose and self._choose is not None:
            linked += await self._link_by_choice(loose)
        return linked

    async def _find_candidates(self, object_type: str, name: str) -> list[dict[str, str]]:
        return await self._neo4j.run(build_loose_query(object_type), name=name.strip().lower(), limit=_CANDIDATE_LIMIT)

    async def _link_by_choice(self, loose: list[tuple[PatientFactInput, list[dict[str, str]]]]) -> int:
        assert self._choose is not None
        try:
            picked = await self._choose([(f.label, f.object_type, [c["name"] for c in cands]) for f, cands in loose])
        except Exception:  # noqa: BLE001  # LLM lỗi: fact giữ dạng chữ
            logger.error("patient-facts: không chọn được nút cho %d nhãn", len(loose), exc_info=True)
            return 0
        linked = 0
        for position, (fact, candidates) in enumerate(loose):
            index = picked.get(position)
            if index is None or not 0 <= index < len(candidates):
                logger.info("patient-facts: '%s' (%s) không có ứng viên đúng nghĩa trong %s", fact.label, fact.object_type, [c["name"] for c in candidates])
                continue
            fact.kg_node_id, fact.link_method = candidates[index]["id"], "llm"
            linked += 1
        return linked
