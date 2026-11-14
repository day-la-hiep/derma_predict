import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any, LiteralString, cast

from app.dto.patient_fact import (
    AppliedLesion,
    ProfileFactItem,
    PatientFactInput,
    PatientFactOutput,
    PatientFactsApplyOutput,
    PatientFactsOutput,
    PatientLesionOutput,
    SkippedFact,
)
from app.infra.neo4j_client import Neo4jClient
from app.pipeline.document_ingest.graph_schema import ENTITY_TYPES
from app.services.onset_resolver import resolve_onset
from app.services.patient_fact_linker import PatientFactLinker

logger = logging.getLogger(__name__)

# Fact cũ hơn mức này mà chưa được nhắc lại thì đánh dấu "chưa xác nhận gần đây" để agent hỏi lại
STALE_AFTER_DAYS = 14

SYMPTOM, MORPHOLOGY, TRIGGER, HISTORY, DRUG, EXPOSURE, ATTRIBUTE = (
    "PT_HAS_SYMPTOM", "PT_HAS_MORPHOLOGY", "PT_TRIGGERED_BY", "PT_HAS_HISTORY", "PT_TAKES_DRUG", "PT_EXPOSED_TO", "PT_HAS_ATTRIBUTE",
)
RELATIONS = (SYMPTOM, MORPHOLOGY, TRIGGER, HISTORY, DRUG, EXPOSURE, ATTRIBUTE)
# Chỉ triệu chứng và hình thái có phủ định ("không ngứa")
_PRESENCE_RELATIONS = (SYMPTOM, MORPHOLOGY)
# Tên thuộc tính chuẩn (nhóm 3); `location` không tạo cạnh mà ghi vào `PtLesion.site_text`. Bảng alias phòng khi model viết tiếng Việt.
LOCATION = "location"
_ATTRIBUTE_ALIASES = {"vị trí": LOCATION, "vi tri": LOCATION, "phân bố": "distribution", "sắp xếp": "arrangement", "diễn biến": "course"}
# Scope đặc biệt: fact thuộc về cả người bệnh (sốt, kết quả xét nghiệm), không gắn tổn thương nào
BODY_SCOPE = "body"
_PRIMARY_SECONDARY = ("primary", "secondary")
_TRIGGER_EFFECTS = ("trigger", "aggravate", "relieve")
_DRUG_KINDS = ("taking", "allergy")
_HISTORY_HOLDERS = ("self", "family")
_SCOPES = ("skin", "mucosa", "nail", "hair", "organ")

_SUBJECT_LABELS = ("Patient", "PtLesion")
_KG_LABELS = ("Disease", "EffectPhenotype", "Drug", "Exposure", "GeneProtein")
_TARGET_MATCH: dict[str, str] = {
    **{label: f"MATCH (o:Entity:{label} {{id: $node_id}})" for label in _KG_LABELS},
    "DermoTerm": "MATCH (o:DermoTerm {id: $node_id})",
    "literal": "MERGE (o:PtLiteral {key: $key}) ON CREATE SET o.text = $text",
}
_OBJECT_TYPE_BY_LABEL = {
    **{e.label: e.id for e in ENTITY_TYPES.values() if e.kg == "primekg"},
    "DermoTerm": "dermo",
}

_SCHEMA_STATEMENTS: tuple[LiteralString, ...] = (
    "CREATE CONSTRAINT pt_lesion_id IF NOT EXISTS FOR (l:PtLesion) REQUIRE l.id IS UNIQUE",
    "CREATE CONSTRAINT pt_literal_key IF NOT EXISTS FOR (l:PtLiteral) REQUIRE l.key IS UNIQUE",
    "CREATE INDEX patient_id IF NOT EXISTS FOR (p:Patient) ON (p.id)",
)

_MERGE_PATIENT: LiteralString = "MERGE (p:Patient {id: $pid})"

_CREATE_LESION: LiteralString = """
MATCH (p:Patient {id: $pid})
MERGE (l:PtLesion {id: $id}) ON CREATE SET l.created_at = $now, l.scope = $scope, l.site_text = $site_text
MERGE (p)-[:PT_HAS_LESION]->(l)
"""

_FIND_LESION: LiteralString = "MATCH (:Patient {id: $pid})-[:PT_HAS_LESION]->(l:PtLesion {id: $id}) RETURN l.id AS id"

_LESION_EXISTS: LiteralString = "MATCH (l:PtLesion {id: $id}) RETURN l.id AS id"

_SET_SITE: LiteralString = "MATCH (l:PtLesion {id: $id}) SET l.site_text = $site_text, l.updated_at = $now"

_READ_LESIONS: LiteralString = """
MATCH (:Patient {id: $pid})-[:PT_HAS_LESION]->(l:PtLesion)
RETURN l.id AS id, coalesce(l.site_text, '') AS site_text, coalesce(l.scope, 'skin') AS scope
ORDER BY l.created_at
"""

_READ_FACTS: LiteralString = """
MATCH (p:Patient {id: $pid})
MATCH (s)-[r]->(o)
WHERE (s = p OR (p)-[:PT_HAS_LESION]->(s)) AND type(r) IN $relations AND r.status IN $statuses
RETURN CASE WHEN s = p THEN null ELSE s.id END AS lesion_id, type(r) AS relation, properties(r) AS props,
       coalesce(r.id, elementId(r)) AS fid, elementId(r) AS rid,
       labels(o) AS labels, o.id AS node_id, coalesce(o.name, o.text) AS label
ORDER BY r.observed_at
"""

LONG_TERM_FACT_TYPES = ("history", "medication", "allergy")


def derive_fact_type(category: int | None, object_type: str, kind: str, effect: str = "", on_body: bool = False) -> str:
    """Loại fact cũ (symptom, lesion, ...) suy từ nhóm, để UI và snapshot dùng chung từ vựng với dữ liệu cũ."""
    if category == 1:
        return "symptom"
    if category == 2 or (category == 3 and not on_body):
        return "lesion"
    if category == 5:
        if object_type == "drug":
            return "allergy" if kind == "allergy" else "medication"
        return "history"
    if category == 4 and not effect:
        return "history"
    return "other"


_MARK_STATUS: LiteralString = "UNWIND $rids AS rid MATCH ()-[r]->() WHERE elementId(r) = rid SET r += $props"


class PatientFactError(ValueError):
    """Fact không ghi được vì dữ liệu của chính nó (loại sai, thiếu tổn thương...): bỏ fact đó, log, các fact khác vẫn ghi."""


@dataclass(frozen=True)
class RelationSpec:
    relation: str
    subject: str  # "lesion" | "patient"
    single_valued: bool = False
    props: dict[str, str] = field(default_factory=dict[str, str])


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _check_choice(value: str, allowed: tuple[str, ...], default: str, field_name: str) -> str:
    chosen = value or default
    if chosen not in allowed:
        raise PatientFactError(f"`{field_name}` phải là một trong {', '.join(allowed)} (nhận '{chosen}')")
    return chosen


def resolve_spec(fact: PatientFactInput) -> RelationSpec | None:
    """Nhóm → quan hệ trong graph; None cho vị trí (nhóm 3, `name=location`) vì vị trí là thuộc tính của tổn thương, không phải cạnh."""
    c = fact.category
    subject = "patient" if fact.scope == BODY_SCOPE else "lesion"
    if c == 1:
        return RelationSpec(SYMPTOM, subject)
    if c == 2:
        return RelationSpec(MORPHOLOGY, "lesion", props={"kind": _check_choice(fact.kind, _PRIMARY_SECONDARY, "primary", "kind")})
    if c == 3:
        name = get_attribute_name(fact)
        if name == LOCATION:
            return None
        return RelationSpec(ATTRIBUTE, subject, True, {"name": name})
    if c == 4:  # có `effect` = yếu tố làm xuất hiện/nặng/đỡ của tổn thương; không có = phơi nhiễm của người bệnh
        if fact.effect:
            return RelationSpec(TRIGGER, "lesion", props={"effect": _check_choice(fact.effect, _TRIGGER_EFFECTS, "trigger", "effect")})
        return RelationSpec(EXPOSURE, "patient")
    if fact.object_type == "drug":
        return RelationSpec(DRUG, "patient", props={"kind": _check_choice(fact.kind, _DRUG_KINDS, "taking", "kind")})
    return RelationSpec(HISTORY, "patient", props={"of": _check_choice(fact.of, _HISTORY_HOLDERS, "self", "of")})


def get_attribute_name(fact: PatientFactInput) -> str:
    name = _normalize(fact.name)
    if not name:
        raise PatientFactError("nhóm 3 cần `name` (tên thuộc tính)")
    return _ATTRIBUTE_ALIASES.get(name, name)


@cache
def build_upsert_query(subject_label: str, relation: str, target: str) -> LiteralString:
    # Loại quan hệ và nhãn không tham số hoá được trong Cypher nên ghép chuỗi; chỉ nhận giá trị trong bảng đóng ở trên
    if subject_label not in _SUBJECT_LABELS or relation not in RELATIONS or target not in _TARGET_MATCH:
        raise ValueError(f"không được phép: {subject_label} {relation} {target}")
    return cast(
        LiteralString,
        f"MATCH (s:{subject_label} {{id: $sid}}) {_TARGET_MATCH[target]} MERGE (s)-[r:{relation}]->(o) "
        "ON CREATE SET r += $created SET r += $updated RETURN count(r) AS n",
    )


@cache
def build_attribute_queries(subject_label: str) -> tuple[LiteralString, LiteralString]:
    if subject_label not in _SUBJECT_LABELS:
        raise ValueError(f"không được phép: {subject_label}")
    current = cast(
        LiteralString,
        f"MATCH (s:{subject_label} {{id: $sid}})-[r:{ATTRIBUTE} {{name: $name, status: 'current'}}]->(o:PtLiteral) "
        "RETURN elementId(r) AS rid, o.key AS key",
    )
    create = cast(
        LiteralString,
        f"MATCH (s:{subject_label} {{id: $sid}}) MERGE (o:PtLiteral {{key: $key}}) ON CREATE SET o.text = $text "
        f"CREATE (s)-[r:{ATTRIBUTE}]->(o) SET r += $props",
    )
    return current, create


def _literal_key(patient_id: str, label: str) -> str:
    # Gắn theo bệnh nhân để hai bệnh nhân không dùng chung một nút chữ
    return f"{patient_id}|{_normalize(label)}"


def _get_target(fact: PatientFactInput) -> str:
    if not fact.kg_node_id:
        return "literal"
    if fact.object_type == "dermo":
        return "DermoTerm"
    entity = ENTITY_TYPES.get(fact.object_type)
    return entity.label if entity is not None and entity.kg == "primekg" else "literal"


def _as_utc(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(UTC)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class PatientFactGraphService:
    def __init__(self, neo4j: Neo4jClient, linker: PatientFactLinker | None = None) -> None:
        self._neo4j = neo4j
        self._linker = linker
        self._schema_ready = False

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in _SCHEMA_STATEMENTS:
            await self._neo4j.run(statement)
        self._schema_ready = True

    async def apply_facts(self, patient_id: str, facts: list[PatientFactInput]) -> PatientFactsApplyOutput:
        if not facts:
            return PatientFactsApplyOutput(applied=0, skipped=[], lesions=[])
        await self._ensure_schema()
        if self._linker is not None:
            await self._linker.link_facts(facts)
        await self._neo4j.run(_MERGE_PATIENT, pid=patient_id)
        lesion_ids: dict[str, str] = {}
        skipped: list[SkippedFact] = []
        applied = 0
        for index, fact in enumerate(facts):
            try:
                await self._apply_fact(patient_id, fact, lesion_ids)
                applied += 1
            except PatientFactError as exc:
                logger.warning("patient-facts %s: bỏ fact #%d (nhóm %d, '%s'): %s", patient_id, index, fact.category, fact.label, exc)
                skipped.append(SkippedFact(index=index, reason=str(exc)))
        return PatientFactsApplyOutput(
            applied=applied, skipped=skipped, lesions=[AppliedLesion(key=k, id=v) for k, v in lesion_ids.items()]
        )

    async def _apply_fact(self, patient_id: str, fact: PatientFactInput, lesion_ids: dict[str, str]) -> None:
        moment = _as_utc(fact.observed_at)
        now = moment.isoformat()
        spec = resolve_spec(fact)
        lesion_id: str | None = None
        if spec is None or spec.subject == "lesion":
            lesion_id = await self._resolve_lesion(patient_id, fact, lesion_ids, now)
        if spec is None:
            assert lesion_id is not None
            await self._neo4j.run(_SET_SITE, id=lesion_id, site_text=fact.label.strip(), now=now)
            return
        subject_label, subject_id = ("PtLesion", lesion_id) if spec.subject == "lesion" and lesion_id else ("Patient", patient_id)
        onset_at = resolve_onset(fact.onset_text, moment.date()) if fact.onset_text.strip() else None
        if spec.single_valued:
            await self._apply_attribute(patient_id, subject_label, subject_id, fact, spec, now)
        else:
            await self._apply_edge(patient_id, subject_label, subject_id, fact, spec, now, onset_at)

    async def _resolve_lesion(self, patient_id: str, fact: PatientFactInput, lesion_ids: dict[str, str], now: str) -> str:
        if fact.lesion_id:
            if await self._neo4j.run(_FIND_LESION, pid=patient_id, id=fact.lesion_id):
                return fact.lesion_id
            if await self._neo4j.run(_LESION_EXISTS, id=fact.lesion_id):
                raise PatientFactError(f"tổn thương {fact.lesion_id} thuộc bệnh nhân khác")
            await self._create_lesion(patient_id, fact.lesion_id, fact, now)  # id mới do agent sinh, chưa có trong graph
            return fact.lesion_id
        if not fact.lesion_key:
            raise PatientFactError("thiếu tổn thương: cần `lesion_id` (đã có) hoặc `lesion_key` (tạo mới)")
        if fact.lesion_key in lesion_ids:
            return lesion_ids[fact.lesion_key]
        new_id = uuid.uuid4().hex
        await self._create_lesion(patient_id, new_id, fact, now)
        lesion_ids[fact.lesion_key] = new_id
        return new_id

    async def _create_lesion(self, patient_id: str, lesion_id: str, fact: PatientFactInput, now: str) -> None:
        scope = _check_choice(fact.scope, _SCOPES, "skin", "scope")
        site_text = fact.label.strip() if fact.category == 3 and get_attribute_name(fact) == LOCATION else fact.site_text.strip()
        await self._neo4j.run(_CREATE_LESION, pid=patient_id, id=lesion_id, now=now, scope=scope, site_text=site_text)

    def _build_edge_props(
        self, spec: RelationSpec, fact: PatientFactInput, now: str, onset_at: date | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        created: dict[str, Any] = {"id": uuid.uuid4().hex, "category": fact.category, "observed_at": now, "link_method": fact.link_method, "object_type": fact.object_type, **spec.props}
        updated: dict[str, Any] = {"last_confirmed_at": now, "status": "resolved" if fact.resolved else "current", "text": fact.label.strip()}
        if fact.detail.strip():
            updated["detail"] = fact.detail.strip()
        if spec.relation in _PRESENCE_RELATIONS:
            updated["present"] = fact.present
        if fact.onset_text.strip():
            updated["onset_text"] = fact.onset_text.strip()
        if onset_at is not None:
            updated["onset_at"] = onset_at.isoformat()
        if fact.source_message_id:
            updated["source_message_id"] = fact.source_message_id
        return created, updated

    async def _apply_edge(
        self, patient_id: str, subject_label: str, subject_id: str, fact: PatientFactInput, spec: RelationSpec, now: str, onset_at: date | None
    ) -> None:
        created, updated = self._build_edge_props(spec, fact, now, onset_at)
        target = _get_target(fact)
        params: dict[str, Any] = {"sid": subject_id, "created": created, "updated": updated}
        if target == "literal":
            params |= {"key": _literal_key(patient_id, fact.label), "text": fact.label.strip()}
        else:
            params["node_id"] = fact.kg_node_id
        rows = await self._neo4j.run(build_upsert_query(subject_label, spec.relation, target), **params)
        if rows and rows[0]["n"] > 0:
            return
        # nút đã khớp không còn trong đồ thị nền (nạp lại, đổi phiên bản): giữ fact dạng chữ thay vì mất
        logger.warning("patient-facts %s: nút %s '%s' (%s) không có trong đồ thị, lưu dạng chữ", patient_id, fact.kg_node_id, fact.label, target)
        created["link_method"] = "none"
        params = {"sid": subject_id, "created": created, "updated": updated, "key": _literal_key(patient_id, fact.label), "text": fact.label.strip()}
        await self._neo4j.run(build_upsert_query(subject_label, spec.relation, "literal"), **params)

    async def _apply_attribute(
        self, patient_id: str, subject_label: str, subject_id: str, fact: PatientFactInput, spec: RelationSpec, now: str
    ) -> None:
        find_current, create = build_attribute_queries(subject_label)
        name, key = spec.props["name"], _literal_key(patient_id, fact.label)
        current = await self._neo4j.run(find_current, sid=subject_id, name=name)
        same = [r["rid"] for r in current if r["key"] == key]
        if same:
            await self._neo4j.run(_MARK_STATUS, rids=same, props={"last_confirmed_at": now})
            return
        if current:
            await self._neo4j.run(_MARK_STATUS, rids=[r["rid"] for r in current], props={"status": "superseded", "superseded_at": now})
        props: dict[str, Any] = {
            "id": uuid.uuid4().hex, "category": fact.category, "observed_at": now, "last_confirmed_at": now, "status": "current", "link_method": "none", **spec.props,
        }
        if fact.source_message_id:
            props["source_message_id"] = fact.source_message_id
        if fact.detail.strip():
            props["detail"] = fact.detail.strip()
        await self._neo4j.run(create, sid=subject_id, key=key, text=fact.label.strip(), props=props)

    async def get_current_facts(self, patient_id: str, include_history: bool = False) -> PatientFactsOutput:
        await self._ensure_schema()
        statuses = ["current", "resolved", "superseded"] if include_history else ["current"]
        lesions = await self._neo4j.run(_READ_LESIONS, pid=patient_id)
        rows = await self._neo4j.run(_READ_FACTS, pid=patient_id, relations=list(RELATIONS), statuses=statuses)
        threshold = datetime.now(UTC) - timedelta(days=STALE_AFTER_DAYS)
        return PatientFactsOutput(
            lesions=[PatientLesionOutput(**row) for row in lesions],
            facts=[self._build_output(row, threshold) for row in rows],
        )

    def _build_output(self, row: dict[str, Any], stale_before: datetime) -> PatientFactOutput:
        props: dict[str, Any] = row["props"]
        labels: list[str] = row["labels"]
        literal = "PtLiteral" in labels
        # nút chữ không có loại nút nên lấy gợi ý đã lưu trên cạnh (thuốc hay bệnh) để suy `fact_type`
        object_type = props.get("object_type", "") if literal else next((_OBJECT_TYPE_BY_LABEL[x] for x in labels if x in _OBJECT_TYPE_BY_LABEL), "")
        last_confirmed = props.get("last_confirmed_at")
        stale = last_confirmed is not None and datetime.fromisoformat(last_confirmed) < stale_before
        onset = props.get("onset_at")
        return PatientFactOutput(
            id=row["fid"],
            fact_type=derive_fact_type(props.get("category"), object_type, props.get("kind", ""), props.get("effect", ""), row["lesion_id"] is None),
            lesion_id=row["lesion_id"],
            category=props.get("category"),
            relation=row["relation"],
            label=props.get("text") or row["label"] or "",
            kg_name="" if literal else (row["label"] or ""),
            detail=props.get("detail", ""),
            object_type=object_type,
            kg_node_id=None if literal else row["node_id"],
            present=props.get("present"),
            status=props.get("status", "current"),
            name=props.get("name", ""),
            kind=props.get("kind", ""),
            effect=props.get("effect", ""),
            of=props.get("of", ""),
            onset_text=props.get("onset_text", ""),
            onset_at=date.fromisoformat(onset) if onset else None,
            observed_at=props.get("observed_at"),
            last_confirmed_at=last_confirmed,
            stale=stale,
            source_message_id=props.get("source_message_id"),
            link_method=props.get("link_method", "none"),
        )

    async def get_long_term_facts(self, patient_ids: list[str]) -> dict[str, list[PatientFactOutput]]:
        """Fact dài hạn (dị ứng, tiền sử, thuốc, yếu tố nguy cơ) của từng hồ sơ; hồ sơ chưa có thì danh sách rỗng."""
        return {
            pid: [f for f in (await self.get_current_facts(pid)).facts if f.fact_type in LONG_TERM_FACT_TYPES]
            for pid in dict.fromkeys(patient_ids)
        }

    async def replace_profile_facts(self, patient_id: str, items: list[ProfileFactItem]) -> list[PatientFactOutput]:
        """Form hồ sơ là danh sách ĐẦY ĐỦ fact dài hạn: thêm/sửa theo nhãn, mục không còn trong form chuyển `resolved` (kể cả mục agent trích từ chat)."""
        inputs = [self._build_profile_fact(item) for item in items if item.label.strip()]
        await self.apply_facts(patient_id, inputs)
        types = [derive_fact_type(f.category, f.object_type, f.kind, f.effect) for f in inputs]
        wanted_labels = {(t, _normalize(f.label)) for t, f in zip(types, inputs)}
        wanted_nodes = {(t, f.kg_node_id) for t, f in zip(types, inputs) if f.kg_node_id}
        rows = await self._neo4j.run(_READ_FACTS, pid=patient_id, relations=list(RELATIONS), statuses=["current"])
        stale: list[str] = []
        for row in rows:
            fact = self._build_output(row, datetime.now(UTC))
            if fact.fact_type not in LONG_TERM_FACT_TYPES:
                continue
            if (fact.fact_type, _normalize(fact.label)) in wanted_labels or (fact.fact_type, fact.kg_node_id) in wanted_nodes:
                continue
            stale.append(row["rid"])
        if stale:
            logger.info("patient-facts %s: form hồ sơ bỏ %d fact dài hạn", patient_id, len(stale))
            await self._neo4j.run(_MARK_STATUS, rids=stale, props={"status": "resolved", "last_confirmed_at": datetime.now(UTC).isoformat()})
        return (await self.get_long_term_facts([patient_id]))[patient_id]

    @staticmethod
    def _build_profile_fact(item: ProfileFactItem) -> PatientFactInput:
        drug = item.fact_type in ("allergy", "medication")
        return PatientFactInput(
            category=5,
            label=item.label.strip(),
            detail=item.detail.strip(),
            object_type="drug" if drug else "disease",
            kind=("allergy" if item.fact_type == "allergy" else "taking") if drug else "",
        )
