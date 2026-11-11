import json
import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.dto.base.document import DocumentChunk, DocumentTriple, GraphNodeRef
from app.infra.llm_client import LLMClient, LLMError

from ..graph_link import EntityLexicon, LexEntry, norm, new_node_id
from ..graph_schema import CORE_SCHEMA, TOPIC_ENTITY_TYPES, TOPIC_TYPES, UNMAPPED_KINDS, GraphSchema, Relation
from ..textutil import sha

logger = logging.getLogger(__name__)

OnProgress = Callable[[int, int, str], None]
OnLog = Callable[[str], None]

PICK_BATCH = 25
CANDIDATES = 8
WORKERS = 4

EXTRACT_PROMPT = """Bạn trích quan hệ y khoa từ đoạn sách giáo khoa da liễu để đưa vào đồ thị tri thức.
Dữ liệu vào (JSON) gồm `context` (đường dẫn mục lục chứa các đoạn, chỉ để biết đoạn nói về gì), `subject_names` (cách ghi tên
chủ thể theo loại), `slots` (các ô cần điền; `subject` là loại chủ thể của ô: disease = bệnh, drug = thuốc) và `chunks`
(các đoạn văn, mỗi đoạn có `chunk_id`).
Quy tắc:
- Mỗi quan hệ nối MỘT chủ thể (bệnh hoặc thuốc) với một thực thể khác. Chủ thể lấy từ chính đoạn văn: chỉ ghi khi đoạn nói rõ
  quan hệ đó thuộc về bệnh/thuốc nào. Đoạn dùng đại từ ("bệnh này", "nó") mà không nêu tên thì chỉ nhận tên trong `context`
  khi `context` đúng là tên bệnh/thuốc đó. Không đoán chủ thể.
- Chỉ trích điều đoạn văn NÓI RÕ. Không suy luận, không thêm kiến thức ngoài đoạn văn.
- Mỗi mục: {"subject": {"text": "<tên chủ thể như trong sách>", "en": "<tên tiếng Anh chuẩn theo subject_names>"},
  "text": "<chữ như trong sách>", "en": "<tên tiếng Anh chuẩn theo mô tả loại thực thể>",
  "evidence": "<câu/cụm trích NGUYÊN VĂN từ đoạn, tối đa 200 ký tự>", "chunk_id": "<id đoạn chứa evidence>"}.
- Một mục chỉ là MỘT thực thể (tách "ngứa và đỏ da" thành 2 mục).
- Thông tin có trong sách nhưng không thuộc ô nào (vị trí tổn thương, yếu tố nguy cơ, dấu hiệu cảnh báo, chẩn đoán
  phân biệt, điều trị không dùng thuốc...) đưa vào "unmapped": [{"kind": "<một trong: KINDS>", "text": "..."}].
- Ô không có thông tin thì để [].
Trả về JSON: {"slots": {"<slot id>": [...]}, "unmapped": [...]}""".replace("KINDS", ", ".join(UNMAPPED_KINDS))

PICK_PROMPT = """Bạn khớp thuật ngữ y khoa trong sách vào nút của đồ thị tri thức. Mỗi mục có `text` (chữ trong sách), `en`
(tên tiếng Anh) và `candidates` (các nút ứng viên). Chọn `id` của nút CÙNG NGHĨA; nếu không có nút nào cùng nghĩa thì
trả null (đừng chọn nút rộng hơn, hẹp hơn hay chỉ liên quan).
Trả về JSON: {"choices": [{"key": "<key>", "id": "<id hoặc null>"}]}"""


# ---------------------------------------------------------------- lô đọc
def split_units(chunks: list[DocumentChunk], size: int) -> list[dict[str, Any]]:
    # lô không vượt ranh giới mục nhỏ nhất (toc_path đầy đủ) để câu trích không lẫn giữa hai mục
    units: list[dict[str, Any]] = []
    prev: tuple[str, ...] | None = None
    for c in chunks:
        key = tuple(c.toc_path)
        if key != prev or len(units[-1]["chunk_ids"]) >= size:
            units.append({"id": f"u{len(units) + 1:05d}", "path": list(key), "chunk_ids": []})
            prev = key
        units[-1]["chunk_ids"].append(c.chunk_id)
    return units


def pick_units(units: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    # chạy thử: lấy rải đều khắp sách, không lấy từ đầu (đầu sách thường là phần tổng quát)
    if not limit or limit >= len(units):
        return units
    return [units[i * len(units) // limit] for i in range(limit)]


# ---------------------------------------------------------------- khớp thực thể
class Linker:
    """Khớp chính xác ngay; chưa khớp thì gom lại cho LLM chọn trong ứng viên (một lượt cuối, theo lô)."""

    def __init__(self, lexicon: EntityLexicon, allow_new: bool, schema: GraphSchema) -> None:
        self.lex, self.allow_new, self.schema = lexicon, allow_new, schema
        self.refs: dict[tuple[str, str, str], GraphNodeRef] = {}
        self.pending: dict[tuple[str, str, str], list[LexEntry]] = {}

    def key(self, type_: str, text: str, en: str) -> tuple[str, str, str]:
        cs = self.schema.entity_types[type_].case_sensitive
        return type_, norm(en, cs), norm(text, cs)

    def ref(self, type_: str, text: str, en: str) -> GraphNodeRef:
        k = self.key(type_, text, en)
        if k in self.refs:
            return self.refs[k]
        hit = next((h for q in (en, text) if q for h in self.lex.exact(type_, q)), None)
        if hit is not None:
            r = self._linked(type_, text, en, hit, "exact")
        else:
            r = GraphNodeRef(kg=self.schema.entity_types[type_].kg, type=type_, text=text, en=en)
            cands = self.lex.candidates(type_, en or text, CANDIDATES)
            if cands:
                self.pending[k] = cands
        self.refs[k] = r
        return r

    @staticmethod
    def _linked(type_: str, text: str, en: str, e: LexEntry, method: str) -> GraphNodeRef:
        return GraphNodeRef(kg=e.kg, type=type_, text=text, en=en, node_id=e.id, name=e.name, link_method=method)  # pyright: ignore[reportArgumentType]

    def resolve_pending(self, llm: LLMClient | None, on_progress: OnProgress, on_log: OnLog) -> None:
        items = list(self.pending.items())
        if items and llm is not None:
            for i in range(0, len(items), PICK_BATCH):
                part = items[i : i + PICK_BATCH]
                on_progress(i, len(items), "AI chọn nút khớp cho thuật ngữ chưa khớp chính xác")
                payload = [{"key": str(n), "type": self.schema.entity_types[k[0]].title, "text": self.refs[k].text, "en": self.refs[k].en,
                            "candidates": [{"id": e.id, "name": e.name} for e in cands]} for n, (k, cands) in enumerate(part)]
                try:
                    data = llm.complete_json(PICK_PROMPT, "Các mục (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="graph_pick")
                except LLMError as e:
                    logger.warning("LLM không chọn được nút cho lô %s: %s", i, e)
                    on_log(f"AI không chọn được nút cho lô {i}: {str(e)[:120]}")
                    continue
                choices = {str(c.get("key")): c.get("id") for c in (data.get("choices") if isinstance(data, dict) else None) or [] if isinstance(c, dict)}
                for n, (k, cands) in enumerate(part):
                    picked = next((e for e in cands if e.id == str(choices.get(str(n)))), None)
                    if picked is not None:
                        old = self.refs[k]
                        self.refs[k] = self._linked(k[0], old.text, old.en, picked, "llm")
        for k, r in self.refs.items():
            # loại do bác sĩ định nghĩa không có từ điển chuẩn: thực thể chưa có nút luôn là nút mới
            if r.node_id is None and (self.allow_new or self.schema.entity_types[k[0]].kg == "doc"):
                    name = r.en or r.text
                    self.refs[k] = r.model_copy(update={"kg": "doc", "node_id": new_node_id(k[0], name), "name": name, "link_method": "new"})

    def final(self, type_: str, text: str, en: str) -> GraphNodeRef:
        return self.refs[self.key(type_, text, en)]


# ---------------------------------------------------------------- trích
def normalize_text(s: str) -> str:
    return " ".join(s.lower().replace("“", '"').replace("”", '"').replace("’", "'").split())


def build_slot_payload(schema: GraphSchema) -> list[dict[str, str]]:
    out = []
    for s in schema.slots:
        obj = s.relations[0].object_type
        out.append({"id": s.id, "subject": s.topic, "description": s.hint, "entity": s.entity_hint or schema.entity_types[obj].hint})
    return out


def extract(llm: LLMClient, schema: GraphSchema, unit: dict[str, Any], by_id: dict[str, DocumentChunk]) -> dict[str, Any]:
    payload = {
        "context": " > ".join(unit["path"]),
        "subject_names": {k: schema.entity_types[k].hint for k in TOPIC_TYPES if k in schema.entity_types},
        "slots": build_slot_payload(schema),
        "chunks": [{"chunk_id": i, "text": by_id[i].text} for i in unit["chunk_ids"]],
    }
    try:
        data = llm.complete_json(EXTRACT_PROMPT, "Dữ liệu (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="graph_extract")
    except LLMError as e:
        logger.warning("LLM không trích được quan hệ cho lô %s (%s): %s", unit["id"], payload["context"], e)
        return {"error": str(e)[:200], "items": [], "unmapped": [], "subject_missing": 0}
    slots = data.get("slots") if isinstance(data, dict) else None
    allowed = {s.id for s in schema.slots}
    items: list[dict[str, Any]] = []
    missing = 0
    for sid, rows in (slots or {}).items() if isinstance(slots, dict) else []:
        if sid not in allowed or not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict) or not str(r.get("text") or r.get("en") or "").strip():
                continue
            raw = r.get("subject")
            subj: dict[str, Any] = raw if isinstance(raw, dict) else {}
            subject = {"text": str(subj.get("text") or "").strip(), "en": str(subj.get("en") or "").strip()}
            if not (subject["text"] or subject["en"]):
                missing += 1
                continue
            items.append({"slot": sid, "subject": subject, "text": str(r.get("text") or "").strip(), "en": str(r.get("en") or "").strip(),
                          "evidence": str(r.get("evidence") or "").strip(), "chunk_id": str(r.get("chunk_id") or "")})
    if missing:
        logger.warning("Lô %s (%s): bỏ %d quan hệ vì AI không nêu chủ thể", unit["id"], payload["context"], missing)
    unmapped = [{"kind": u.get("kind") if u.get("kind") in UNMAPPED_KINDS else "other", "text": str(u.get("text") or "")[:200]}
                for u in (data.get("unmapped") or [] if isinstance(data, dict) else []) if isinstance(u, dict) and u.get("text")]
    return {"items": items, "unmapped": unmapped, "subject_missing": missing}


def find_grounded_chunk(item: dict[str, Any], chunk_ids: list[str], by_id: dict[str, DocumentChunk]) -> str | None:
    """Chunk chứa nguyên văn `evidence`; None = AI bịa / chép sai -> bỏ."""
    ev = normalize_text(item["evidence"])
    if len(ev) < 3:
        return None
    order = [item["chunk_id"]] if item["chunk_id"] in chunk_ids else []
    for cid in order + [c for c in chunk_ids if c not in order]:
        if ev in normalize_text(by_id[cid].text):
            return cid
    return None


def build_triples(document_id: str, item: dict[str, Any], cid: str, page: int, linker: Linker) -> list[DocumentTriple]:
    slot = linker.schema.slot(item["slot"])
    assert slot is not None
    subject = item["subject"]
    out = []
    for rel in slot.relations:
        # đầu kia thuộc DermO thì chủ thể cũng phải là nút DermO (cạnh DermO chỉ nối DermoTerm với DermoTerm)
        subject_type = "dermo" if linker.schema.entity_types[rel.object_type].kg == "dermo" else slot.topic
        t_ref = linker.final(subject_type, subject["text"], subject["en"])
        o_ref = linker.final(rel.object_type, item["text"], item["en"])
        subj, obj = (t_ref, o_ref) if rel.topic_is_head else (o_ref, t_ref)
        tid = sha(document_id, slot.id, rel.type, norm(subject["en"] or subject["text"]), norm(item["en"] or item["text"]))[:16]
        out.append(DocumentTriple(triple_id=tid, document_id=document_id, slot=slot.id, relation=rel.type, subject=subj, object=obj,
                                  evidence=item["evidence"], chunk_ids=[cid], pages=[page], status="unlinked"))
    return out


def merge_triples(rows: list[DocumentTriple]) -> list[DocumentTriple]:
    by_id: dict[str, DocumentTriple] = {}
    for t in rows:
        cur = by_id.get(t.triple_id)
        if cur is None:
            by_id[t.triple_id] = t
        else:
            cur.chunk_ids = sorted({*cur.chunk_ids, *t.chunk_ids})
            cur.pages = sorted({*cur.pages, *t.pages})
    return list(by_id.values())


def run_extractions(llm: LLMClient, schema: GraphSchema, units: list[dict[str, Any]], by_id: dict[str, DocumentChunk],
                    on_progress: OnProgress) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(extract, llm, schema, u, by_id): u for u in units}
        for n, f in enumerate(as_completed(futs), 1):
            u = futs[f]
            results.append((u, f.result()))
            on_progress(n, len(units), f"AI trích quan hệ: {u['path'][-1] if u['path'] else '(ngoài mục lục)'}")
    return results


def extract_triples(chunks: list[DocumentChunk], llm: LLMClient, lexicon: EntityLexicon, schema: GraphSchema, *, document_id: str,
                    allow_new: bool, chunks_per_call: int, limit_calls: int, on_progress: OnProgress,
                    on_log: OnLog) -> tuple[list[DocumentTriple], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Chunks -> (triple máy trích, lô đã đọc, thông tin chưa xếp vào ô, thống kê); chưa áp override."""
    by_id = {c.chunk_id: c for c in chunks}
    # Bước 1: chia chunk thành lô theo mục nhỏ nhất; chạy thử thì chỉ đọc `limit_calls` lô rải đều
    all_units = split_units(chunks, chunks_per_call)
    units = pick_units(all_units, limit_calls)
    on_log(f"{len(chunks)} đoạn chia thành {len(all_units)} lô, đọc {len(units)} lô")
    # Bước 2: LLM đọc từng lô, tự nêu chủ thể (bệnh/thuốc) của mỗi quan hệ; chạy song song
    linker = Linker(lexicon, allow_new, schema)
    results = run_extractions(llm, schema, units, by_id, on_progress)
    # Bước 3: giữ mục có evidence nguyên văn trong chunk; khớp chủ thể và thực thể đầu kia
    stats: Counter[str] = Counter()
    unmapped: list[dict[str, Any]] = []
    subjects: set[tuple[str, str]] = set()
    grounded: list[tuple[dict[str, Any], str]] = []
    for u, res in results:
        if res.get("error"):
            stats["llm_failed_calls"] += 1
            on_log(f"lỗi trích lô {u['id']} ({u['chunk_ids'][0]}...): {res['error']}")
        stats["subject_missing"] += res["subject_missing"]
        unmapped += [{**x, "topic": u["path"][-1] if u["path"] else "", "chunk_id": u["chunk_ids"][0]} for x in res["unmapped"]]
        for it in res["items"]:
            cid = find_grounded_chunk(it, u["chunk_ids"], by_id)
            if cid is None:
                stats["evidence_dropped"] += 1
                continue
            grounded.append((it, cid))
            slot = schema.slot(it["slot"])
            assert slot is not None  # `extract` chỉ giữ ô có trong schema
            subj = it["subject"]
            for et in TOPIC_ENTITY_TYPES[slot.topic]:
                linker.ref(et, subj["text"], subj["en"])
            for rel in slot.relations:
                linker.ref(rel.object_type, it["text"], it["en"])
            subjects.add((slot.topic, norm(subj["en"] or subj["text"])))
    # Bước 4: LLM chọn nút cho thuật ngữ chưa khớp chính xác
    linker.resolve_pending(llm, on_progress, on_log)
    # Bước 5: dựng triple (gộp trùng)
    triples = merge_triples([tr for it, cid in grounded for tr in build_triples(document_id, it, cid, by_id[cid].page_start, linker)])
    return triples, units, unmapped, {**stats, "units_total": len(all_units), "subjects": dict(Counter(k for k, _ in subjects))}


# ---------------------------------------------------------------- override của người duyệt
def apply_overrides(triples: list[DocumentTriple], ov: dict[str, Any], schema: GraphSchema = CORE_SCHEMA) -> list[DocumentTriple]:
    """`rejected`: loại triple."""
    rejected = set(ov.get("rejected") or [])
    out = []
    for t in triples:
        t = t.model_copy(deep=True)
        # nút mới của loại do bác sĩ định nghĩa tự được chấp nhận (không có từ điển chuẩn để đối chiếu)
        linked = all(s.node_id and (s.link_method != "new" or is_doc_type(schema, s.type)) for s in (t.subject, t.object))
        t.status = "rejected" if t.triple_id in rejected else "ok" if linked else "unlinked"
        out.append(t)
    return out


def is_doc_type(schema: GraphSchema, type_: str) -> bool:
    e = schema.entity_types.get(type_)
    return e is not None and e.kg == "doc"


def summarize_triples(triples: list[DocumentTriple], units: list[dict[str, Any]], unmapped: list[dict[str, Any]],
                      stats: dict[str, Any], schema: GraphSchema) -> dict[str, Any]:
    status = Counter(t.status for t in triples)
    refs = {(s.type, s.text, s.en): s for t in triples for s in (t.subject, t.object)}
    link: dict[str, list[int]] = {}
    for (type_, _, _), s in refs.items():
        v = link.setdefault(type_, [0, 0])
        v[1] += 1
        v[0] += bool(s.node_id) and s.link_method != "new"
    summary: dict[str, Any] = {
        "units": len(units),
        "units_total": stats.get("units_total", len(units)),
        "subjects": stats.get("subjects", {}),
        "triples": len(triples), "ok": status["ok"], "unlinked": status["unlinked"], "rejected": status["rejected"],
        "by_relation": dict(Counter(t.relation for t in triples if t.status == "ok")),
        "linked": {schema.entity_types[k].title if k in schema.entity_types else k: f"{a}/{b}" for k, (a, b) in link.items()},
        "new_entities": len({s.node_id for t in triples for s in (t.subject, t.object) if s.link_method == "new"}),
        "unmapped": dict(Counter(u["kind"] for u in unmapped)),
        "evidence_dropped": stats.get("evidence_dropped", 0),
    }
    warnings = []
    if stats.get("llm_failed_calls"):
        warnings.append(f"{stats['llm_failed_calls']} lần gọi AI lỗi — các đoạn đó chưa được trích (xem nhật ký).")
    if stats.get("subject_missing"):
        warnings.append(f"{stats['subject_missing']} quan hệ bị bỏ vì AI không nêu chủ thể (xem nhật ký).")
    if warnings:
        summary["warnings"] = warnings
    if stats.get("llm"):
        summary["llm"] = stats["llm"]
    return summary


def relation_of(t: DocumentTriple, schema: GraphSchema = CORE_SCHEMA) -> Relation | None:
    return schema.relation_of(t.slot, t.relation)
