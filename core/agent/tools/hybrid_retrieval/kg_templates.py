"""Template truy vấn đồ thị tri thức theo intent (mỗi intent ↔ đúng nhóm quan hệ cần cho mục đích đó)"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, LiteralString, get_args

from app.api.deps import get_knowledge_graph_service
from app.services.knowledge_graph_service import base_name, name_variants

from agent.tools.hybrid_retrieval.kg import extract_entities

logger = logging.getLogger(__name__)

Intent = Literal[
    "disease_overview",
    "symptoms_of_disease",
    "diseases_with_symptom",
    "differential",
    "treatments",
    "contraindications",
    "drug_profile",
    "red_flags_risk",
]
INTENTS: tuple[str, ...] = get_args(Intent)

MAX_ENTITIES = 6
_SHARED_CAP = 2.0  # trần điểm 2-hop: bệnh nhiều triệu chứng chung (toàn thân) không được lấn át tín hiệu trực tiếp
_POOL = 12  # số ứng viên lấy từ graph trước khi lọc bỏ chính bệnh đầu vào
_CANDIDATES = 8

# Nhãn trung tính về chiều vì truy vấn không phân biệt chiều cạnh; thứ tự khoá = thứ tự ưu tiên khi cắt `top_k`.
RELATION_LABELS = {
    "DISEASE_PHENOTYPE_POSITIVE": "bệnh–triệu chứng (có)",
    "DISEASE_TYPICAL_LOCATION": "bệnh–vị trí thường gặp",
    "DISEASE_RISK_FACTOR": "bệnh–yếu tố nguy cơ",
    "DISEASE_RED_FLAG": "bệnh–dấu hiệu cảnh báo (cờ đỏ)",
    "DISEASE_DISEASE": "bệnh liên quan",
    "INDICATION": "thuốc–bệnh (chỉ định)",
    "CONTRAINDICATION": "thuốc–bệnh (chống chỉ định)",
    "DISEASE_PHENOTYPE_NEGATIVE": "bệnh–triệu chứng (không có)",
    "OFF_LABEL_USE": "thuốc–bệnh (dùng ngoài chỉ định)",
    "DRUG_EFFECT": "thuốc–tác dụng phụ/hiệu ứng",
    "DRUG_DRUG": "thuốc–thuốc (tương tác)",
}
_RELATION_ORDER = {name: i for i, name in enumerate(RELATION_LABELS)}

# `edge_sources` (KnowledgeGraphService tự truyền, `settings.KG_EDGE_SOURCES`): cạnh gốc không có `source` = "KG", cạnh trích từ
# sách = "DOC"; `refs` = trang sách của cạnh DOC để agent trích nguồn.
# Cạnh viết thẳng trong pattern (không `type(r) IN $...`) để Neo4j chỉ duyệt đúng loại cạnh: thuốc có hàng nghìn cạnh DRUG_DRUG.
# `ORDER BY m.name` trước `collect` để phần cắt `[..$per_relation]` ổn định giữa các lần chạy.
_DISEASE_OVERVIEW = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:DISEASE_PHENOTYPE_POSITIVE|DISEASE_TYPICAL_LOCATION|DISEASE_RISK_FACTOR|DISEASE_RED_FLAG|DISEASE_DISEASE]-(m:Entity)
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

_SYMPTOMS_OF_DISEASE = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:DISEASE_PHENOTYPE_POSITIVE|DISEASE_PHENOTYPE_NEGATIVE]-(m:Entity)
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

_RED_FLAGS_RISK = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:DISEASE_RED_FLAG|DISEASE_RISK_FACTOR|DISEASE_TYPICAL_LOCATION]-(m:Entity)
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

_TREATMENTS = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:INDICATION|OFF_LABEL_USE]-(m:Entity)
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

_CONTRAINDICATIONS = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:CONTRAINDICATION]-(m:Entity)
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

# Hỏi ≥2 thuốc thì chỉ giữ tương tác GIỮA các thuốc đó, không liệt kê mọi thuốc tương tác với từng cái.
_DRUG_PROFILE = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
MATCH (s)-[r:INDICATION|CONTRAINDICATION|OFF_LABEL_USE|DRUG_EFFECT|DRUG_DRUG]-(m:Entity)
WHERE type(r) <> 'DRUG_DRUG' OR size($sids) < 2 OR elementId(m) IN $sids
WITH s, r, m WHERE coalesce(r.source, 'KG') IN $edge_sources
WITH s, type(r) AS relation, m, [x IN collect(DISTINCT r.source_ref) WHERE x IS NOT NULL] AS refs ORDER BY m.name
WITH s, relation, collect({m: m, refs: refs})[..$per_relation] AS ms
UNWIND ms AS x
RETURN s.name AS subject, s.type AS subject_type, relation, x.m.name AS object, x.m.type AS object_type, x.refs AS refs
"""

# Trọng số (heuristic). `3 / ln(2 + degree)`: triệu chứng nối với ít bệnh thì đặc hiệu hơn, đóng góp nhiều điểm hơn. Degree chỉ
# đếm cạnh bệnh–triệu chứng: nút phenotype còn nối thuốc (drug_effect) và phenotype khác nên đếm mọi cạnh sẽ làm mọi triệu
# chứng trông "phổ biến".
_CANDIDATE_QUERY = """
UNWIND $seed_ids AS sid
MATCH (s:Entity) WHERE elementId(s) = sid
WITH collect(s) AS seeds
CALL (seeds) {
  UNWIND seeds AS s
  WITH s WHERE s.type = 'effect/phenotype'
  MATCH (s)-[e:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'}) WHERE cand improved case result formattingoalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 3.0 / log(2.0 + COUNT { (s)-[x:DISEASE_PHENOTYPE_POSITIVE]-() WHERE coalesce(x.source, 'KG') IN $edge_sources }) AS w,
         'direct' AS kind, 'triệu chứng: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'disease'
  MATCH (s)-[e:DISEASE_DISEASE]-(d:Entity {type: 'disease'}) WHERE d <> s AND coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 1.0 AS w, 'direct' AS kind, 'bệnh liên quan tới: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'disease'
  MATCH (s)-[e1:DISEASE_PHENOTYPE_POSITIVE]-(p:Entity {type: 'effect/phenotype'})
        -[e2:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'})
  WHERE d <> s AND coalesce(e1.source, 'KG') IN $edge_sources AND coalesce(e2.source, 'KG') IN $edge_sources
  RETURN d, 1.5 / log(2.0 + COUNT { (p)-[x:DISEASE_PHENOTYPE_POSITIVE]-() WHERE coalesce(x.source, 'KG') IN $edge_sources }) AS w,
         'shared' AS kind,
         'chung triệu chứng ' + p.name + ' với ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'drug'
  MATCH (s)-[e:INDICATION]-(d:Entity {type: 'disease'}) WHERE coalesce(e.source, 'KG') IN $edge_sources
  RETURN d, 1.0 AS w, 'direct' AS kind, 'thuốc ' + s.name + ' chỉ định cho bệnh này' AS via
}
WITH d, seeds,
     sum(CASE kind WHEN 'direct' THEN w ELSE 0 END) AS direct,
     sum(CASE kind WHEN 'shared' THEN w ELSE 0 END) AS shared,
     collect(DISTINCT via)[..4] AS why
WHERE NOT d IN seeds
WITH d, why, direct + CASE WHEN shared > $shared_cap THEN $shared_cap ELSE shared END AS score
RETURN d.name AS name, score, why
ORDER BY score DESC
LIMIT $pool
"""


# Nút bệnh BYT (cờ đỏ, vị trí, nguy cơ) và nút PrimeKG (triệu chứng, thuốc) của cùng một bệnh nối nhau bằng cạnh "mapped to primekg";
# chỉ khớp tên thì mỗi bên chỉ thấy một nửa dữ liệu.
_EXPAND_MAPPED = """
MATCH (s:Entity) WHERE elementId(s) IN $sids
OPTIONAL MATCH (s)-[r:DISEASE_DISEASE]-(m:Entity) WHERE r.display_relation = 'mapped to primekg'
RETURN collect(DISTINCT elementId(s)) AS own, collect(DISTINCT elementId(m)) AS mapped
"""


@dataclass(frozen=True)
class _Template:
    seed_types: tuple[str, ...]
    cypher: (
        LiteralString | None
    )  # None: intent chạy bằng đường riêng (ứng viên / phân biệt)
    per_relation: int
    needs: str  # mô tả loại thực thể cần, dùng trong thông báo khi không khớp


_DISEASE = ("disease",)
_DRUG = ("drug",)
_SYMPTOM = ("effect/phenotype",)

TEMPLATES: dict[str, _Template] = {
    "disease_overview": _Template(_DISEASE, _DISEASE_OVERVIEW, 4, "bệnh"),
    "symptoms_of_disease": _Template(
        _DISEASE, _SYMPTOMS_OF_DISEASE, 10, "bệnh"
    ),
    "red_flags_risk": _Template(_DISEASE, _RED_FLAGS_RISK, 6, "bệnh"),
    "treatments": _Template(_DISEASE, _TREATMENTS, 10, "bệnh"),
    "contraindications": _Template(
        _DISEASE + _DRUG, _CONTRAINDICATIONS, 10, "bệnh hoặc thuốc"
    ),
    "drug_profile": _Template(_DRUG, _DRUG_PROFILE, 5, "thuốc"),
    "diseases_with_symptom": _Template(_SYMPTOM, None, 0, "triệu chứng"),
    "differential": _Template(_DISEASE, None, 0, "bệnh"),
}


def _fact(intent: str, row: dict[str, Any]) -> dict[str, str]:
    label = RELATION_LABELS.get(row["relation"], row["relation"])
    text = f"{row['subject']} ({row['subject_type']}) — {label} — {row['object']} ({row['object_type']})"
    if row.get("refs"):
        text += f" [theo sách: {'; '.join(row['refs'][:2])}]"
    return {"intent": intent, "relation": row["relation"], "text": text}


async def _candidate_facts(
    intent: str, seeds: list[dict[str, Any]], seed_dermo_ids: set[str]
) -> list[dict[str, str]]:
    svc = get_knowledge_graph_service()
    pool = await svc.run(
        _CANDIDATE_QUERY,
        seed_ids=[s["id"] for s in seeds],
        pool=_POOL,
        shared_cap=_SHARED_CAP,
    )
    pool = list(await asyncio.gather(*(svc.attach_dermo_id(c) for c in pool)))
    # PrimeKG có nút trùng cho cùng một bệnh (vd "atopic dermatitis" / "dermatitis, atopic")
    input_names = {base_name(s["name"]) for s in seeds}
    pool = [
        c
        for c in pool
        if c["dermo_id"] not in seed_dermo_ids
        and not input_names & {base_name(v) for v in name_variants(c["name"])}
    ]
    return [
        {
            "intent": intent,
            "relation": "CANDIDATE",
            "text": f"Bệnh ứng viên theo đồ thị tri thức: {c['name']} (điểm đồ thị {c['score']:.2f}; {'; '.join(c['why'])})",
        }
        for c in pool[:_CANDIDATES]
    ]


async def _differential_facts(names: list[str]) -> list[dict[str, str]]:
    # Truyền tên người hỏi, không phải tên nút: một bệnh có thể có vài nút PrimeKG/BYT, `discriminating_questions` tự gộp chúng.
    if len(names) < 2:
        return []
    result = await get_knowledge_graph_service().discriminating_questions(
        names, top_k=5
    )
    return [
        {
            "intent": "differential",
            "relation": "DISCRIMINATING_PHENOTYPE",
            "text": f"Triệu chứng phân biệt: {q['phenotype']} — có ở: {', '.join(q['present_in'])}; không có ở: {', '.join(q['absent_in'])}",
        }
        for q in result["questions"]
    ]


async def _resolve(
    entities: list[str],
    notes: list[str],
    translated_out: list[str],
    translate: bool = True,
) -> tuple[list[dict[str, Any]], set[str]]:
    svc = get_knowledge_graph_service()
    # PrimeKG đảo tên kiểu "dermatitis, atopic" cho "atopic dermatitis" nhưng không phải lúc nào DermO cũng có đồng nghĩa đó.
    flipped = [
        f"{w[1]}, {w[0]}"
        for e in entities
        if len(w := e.split()) == 2 and "," not in e
    ]
    seeds, unmatched, dermo_ids = await svc.resolve_seeds([*entities, *flipped])
    unmatched = [u for u in unmatched if u in entities]
    if unmatched and translate:
        # Tên không khớp thường là tiếng Việt / viết tắt: nhờ LLM dịch sang tên y khoa chuẩn rồi thử lại một lần.
        try:
            translated = [
                e.text
                for e in await extract_entities(", ".join(unmatched))
                if e.text
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[knowledge_graph_query] không dịch được tên thực thể %s: %s",
                unmatched,
                exc,
                exc_info=True,
            )
            notes.append(
                f"Không dịch được tên thực thể ({type(exc).__name__})."
            )
            translated = []
        if translated:
            translated_out.extend(translated)
            more, unmatched, more_dermo = await svc.resolve_seeds(translated)
            seeds = list({s["id"]: s for s in [*seeds, *more]}.values())
            dermo_ids |= more_dermo
    if unmatched:
        notes.append("Không có trong đồ thị: " + ", ".join(unmatched))
    return seeds, dermo_ids


async def run_intent(
    intent: str, entities: list[str], limit: int, translate: bool = True
) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
    """Trả (dữ kiện `{intent, relation, text}` đã xếp theo ưu tiên quan hệ, ghi chú cho agent, thực thể sau khi khớp/dịch)."""
    notes: list[str] = []
    template = TEMPLATES.get(intent)
    if template is None:
        return (
            [],
            [
                f"intent '{intent}' không hợp lệ — chọn một trong: {', '.join(INTENTS)}."
            ],
            {},
        )
    names = list(dict.fromkeys(e.strip() for e in entities if e.strip()))[
        :MAX_ENTITIES
    ]
    if not names:
        return (
            [],
            ["Thiếu `entities`: nêu tên bệnh / triệu chứng / thuốc cần tra."],
            {},
        )

    translated: list[str] = []
    seeds, dermo_ids = await _resolve(names, notes, translated, translate)
    resolved: dict[str, Any] = {
        "matched_nodes": [f"{s['name']} ({s['type']})" for s in seeds]
    }
    if translated:
        resolved["llm_translated"] = translated
    usable = [s for s in seeds if s["type"] in template.seed_types]
    if not usable:
        found = sorted({s["type"] for s in seeds})
        if found:
            notes.append(
                f"Intent `{intent}` cần thực thể là {template.needs}, nhưng chỉ khớp loại: {', '.join(found)}."
            )
        return [], notes, resolved

    sids = [s["id"] for s in usable]
    if any(s["type"] == "disease" for s in usable):
        row = (
            await get_knowledge_graph_service().run(_EXPAND_MAPPED, sids=sids)
        )[0]
        sids = list(dict.fromkeys([*row["own"], *row["mapped"]]))

    if intent == "diseases_with_symptom":
        facts = await _candidate_facts(intent, usable, dermo_ids)
    elif intent == "differential":
        facts = [
            *await _differential_facts(names),
            *await _candidate_facts(intent, usable, dermo_ids),
        ]
    else:
        assert template.cypher is not None
        rows = await get_knowledge_graph_service().run(
            template.cypher, sids=sids, per_relation=template.per_relation
        )
        facts = [_fact(intent, r) for r in rows]
        # Hỏi nhiều thuốc cùng lúc thì tương tác giữa chúng là thứ người hỏi cần nhất.
        first = (
            "DRUG_DRUG" if intent == "drug_profile" and len(usable) > 1 else ""
        )
        facts.sort(
            key=lambda f: (
                f["relation"] != first,
                _RELATION_ORDER.get(f["relation"], len(_RELATION_ORDER)),
            )
        )

    unique = list({f["text"]: f for f in facts}.values())
    if not unique:
        notes.append("Đồ thị không có quan hệ phù hợp cho thực thể này.")
    return unique[:limit], notes, resolved
