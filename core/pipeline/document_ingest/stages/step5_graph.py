import json
import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.dto.base.document import DocumentTriple, GraphNodeRef
from app.infra.llm_client import LLMClient, LLMError

from ..graph_link import EntityLexicon, LexEntry, norm, new_node_id
from ..graph_schema import CORE_SCHEMA, TOPIC_ENTITY_TYPES, TOPIC_TYPES, UNMAPPED_KINDS, GraphSchema, Relation
from ..textutil import sha
from . import StageError

logger = logging.getLogger(__name__)

OnProgress = Callable[[int, int, str], None]
OnLog = Callable[[str], None]

TOPIC_BATCH = 60
PICK_BATCH = 25
CANDIDATES = 8
WORKERS = 4

TOPIC_PROMPT = """Bạn đọc tiêu đề các mục trong mục lục một sách da liễu, kèm đoạn mở đầu của mục (`excerpt`) để biết mục
nói về gì — dựa vào nội dung, đừng đoán từ tiêu đề. Với mỗi mục, xác định mục đó là bài về MỘT BỆNH
cụ thể ("disease"), MỘT THUỐC/nhóm thuốc cụ thể ("drug"), hay mục khác ("other": chương tổng quát, giải phẫu, sinh lý,
kỹ thuật, tiểu mục như "Điều trị", "Chẩn đoán"...). Với disease/drug, ghi tên tiếng Anh theo thuật ngữ y khoa chuẩn
(MONDO/ICD cho bệnh, hoạt chất DrugBank cho thuốc), không dùng tên thông thường (vd "furunculosis", không phải "boils"),
kèm tối đa 3 tên chuẩn đồng nghĩa khác trong `alt` (vd "furuncle").
Trả về JSON: {"topics": [{"id": "<id>", "kind": "disease"|"drug"|"other", "en": "<tên tiếng Anh, rỗng nếu other>",
"alt": ["<tên đồng nghĩa>"]}]}"""

EXTRACT_PROMPT = """Bạn trích quan hệ y khoa từ đoạn sách giáo khoa da liễu để đưa vào đồ thị tri thức.
Dữ liệu vào (JSON) gồm `topic` (chủ đề của mục sách: một bệnh hoặc một thuốc), `slots` (các ô cần điền, mỗi ô có mô tả
và loại thực thể cần ghi) và `chunks` (các đoạn văn, mỗi đoạn có `chunk_id`).
Quy tắc:
- Chỉ trích điều đoạn văn NÓI RÕ về chính chủ đề này. Không suy luận, không thêm kiến thức ngoài đoạn văn.
- Mỗi mục: {"text": "<chữ như trong sách>", "en": "<tên tiếng Anh chuẩn theo mô tả loại thực thể>",
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


# ---------------------------------------------------------------- chủ đề của mục
def get_topic_key(c: dict[str, Any]) -> list[str]:
    path = list(c.get("toc_path") or [])
    t = c.get("topic") or ""
    if t and t in path:
        return path[: path.index(t) + 1]
    return path


def collect_topics(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for c in chunks:
        key = tuple(get_topic_key(c))
        if not key:
            continue
        t = by_key.setdefault(key, {"id": "tp" + sha(*key)[:10], "title": key[-1], "path": list(key[:-1]), "chunk_ids": []})
        t["chunk_ids"].append(c["chunk_id"])
    return list(by_key.values())


def classify_topics(llm: LLMClient, topics: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], on_progress: OnProgress) -> None:
    for i in range(0, len(topics), TOPIC_BATCH):
        part = topics[i : i + TOPIC_BATCH]
        on_progress(i, len(topics), "AI phân loại mục: bệnh / thuốc / khác")
        # chỉ tiêu đề thì LLM dễ dịch nhầm (vd "Nhọt" -> herpes labialis); vài câu đầu của bài giúp xác định đúng bệnh
        payload = [{"id": t["id"], "title": t["title"], "path": " > ".join(t["path"]),
                    "excerpt": " ".join(by_id[t["chunk_ids"][0]]["text"].split())[:300]} for t in part]
        try:
            data = llm.complete_json(TOPIC_PROMPT, "Các mục (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="graph_topics")
        except LLMError as e:
            logger.warning("LLM không phân loại được các mục: %s", e)
            raise StageError(f"AI không phân loại được các mục: {e}") from e
        got = {str(x.get("id")): x for x in (data.get("topics") if isinstance(data, dict) else None) or [] if isinstance(x, dict)}
        for t in part:
            x = got.get(t["id"], {})
            kind = x.get("kind") if x.get("kind") in TOPIC_TYPES else "other"
            t["kind"], t["en"] = kind, str(x.get("en") or "").strip() if kind != "other" else ""
            alt = x.get("alt")
            t["alt"] = [str(a).strip() for a in alt if str(a).strip()][:3] if kind != "other" and isinstance(alt, list) else []


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

    def ref(self, type_: str, text: str, en: str, alt: list[str] | None = None) -> GraphNodeRef:
        k = self.key(type_, text, en)
        if k in self.refs:
            return self.refs[k]
        hit = next((h for q in (en, *(alt or []), text) if q for h in self.lex.exact(type_, q)), None)
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


def build_slot_payload(schema: GraphSchema, kind: str) -> list[dict[str, str]]:
    out = []
    for s in schema.slots_for(kind):
        obj = s.relations[0].object_type
        out.append({"id": s.id, "description": s.hint, "entity": s.entity_hint or schema.entity_types[obj].hint})
    return out


def split_batches(topic: dict[str, Any], size: int) -> list[list[str]]:
    ids = topic["chunk_ids"]
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def extract(llm: LLMClient, schema: GraphSchema, topic: dict[str, Any], chunk_ids: list[str], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "topic": {"kind": topic["kind"], "title": topic["title"], "en": topic["en"], "path": " > ".join(topic["path"])},
        "slots": build_slot_payload(schema, topic["kind"]),
        "chunks": [{"chunk_id": i, "text": by_id[i]["text"]} for i in chunk_ids],
    }
    try:
        data = llm.complete_json(EXTRACT_PROMPT, "Dữ liệu (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="graph_extract")
    except LLMError as e:
        logger.warning("LLM không trích được quan hệ cho mục %r: %s", topic["title"], e)
        return {"error": str(e)[:200], "items": [], "unmapped": []}
    slots = data.get("slots") if isinstance(data, dict) else None
    allowed = {s.id for s in schema.slots_for(topic["kind"])}
    items: list[dict[str, Any]] = []
    for sid, rows in (slots or {}).items() if isinstance(slots, dict) else []:
        if sid not in allowed or not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict) and str(r.get("text") or r.get("en") or "").strip():
                items.append({"slot": sid, "text": str(r.get("text") or "").strip(), "en": str(r.get("en") or "").strip(),
                              "evidence": str(r.get("evidence") or "").strip(), "chunk_id": str(r.get("chunk_id") or "")})
    unmapped = [{"kind": u.get("kind") if u.get("kind") in UNMAPPED_KINDS else "other", "text": str(u.get("text") or "")[:200]}
                for u in (data.get("unmapped") or [] if isinstance(data, dict) else []) if isinstance(u, dict) and u.get("text")]
    return {"items": items, "unmapped": unmapped}


def find_grounded_chunk(item: dict[str, Any], chunk_ids: list[str], by_id: dict[str, dict[str, Any]]) -> str | None:
    """Chunk chứa nguyên văn `evidence`; None = AI bịa / chép sai -> bỏ."""
    ev = normalize_text(item["evidence"])
    if len(ev) < 3:
        return None
    order = [item["chunk_id"]] if item["chunk_id"] in chunk_ids else []
    for cid in order + [c for c in chunk_ids if c not in order]:
        if ev in normalize_text(by_id[cid]["text"]):
            return cid
    return None


def build_triples(document_id: str, topic: dict[str, Any], item: dict[str, Any], cid: str, page: int,
             linker: Linker) -> list[DocumentTriple]:
    slot = linker.schema.slot(item["slot"])
    assert slot is not None
    out = []
    for rel in slot.relations:
        # đầu kia thuộc DermO thì chủ đề cũng phải là nút DermO (cạnh DermO chỉ nối DermoTerm với DermoTerm)
        topic_type = "dermo" if linker.schema.entity_types[rel.object_type].kg == "dermo" else topic["kind"]
        t_ref = linker.final(topic_type, topic["title"], topic["en"])
        o_ref = linker.final(rel.object_type, item["text"], item["en"])
        subj, obj = (t_ref, o_ref) if rel.topic_is_head else (o_ref, t_ref)
        tid = sha(document_id, slot.id, rel.type, topic["id"], norm(item["en"] or item["text"]))[:16]
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


def run_extractions(llm: LLMClient, schema: GraphSchema, jobs: list[tuple[dict[str, Any], list[str]]], by_id: dict[str, dict[str, Any]],
                    on_progress: OnProgress) -> list[tuple[dict[str, Any], list[str], dict[str, Any]]]:
    results: list[tuple[dict[str, Any], list[str], dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(extract, llm, schema, t, ids, by_id): (t, ids) for t, ids in jobs}
        for n, f in enumerate(as_completed(futs), 1):
            t, ids = futs[f]
            results.append((t, ids, f.result()))
            on_progress(n, len(jobs), f"AI trích quan hệ: {t['title']}")
    return results


def extract_triples(chunks: list[dict[str, Any]], llm: LLMClient, lexicon: EntityLexicon, schema: GraphSchema, *, document_id: str,
                    allow_new: bool, chunks_per_call: int, limit_topics: int, on_progress: OnProgress,
                    on_log: OnLog) -> tuple[list[DocumentTriple], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Chunks -> (triple máy trích, chủ đề, thông tin chưa xếp vào ô, thống kê); chưa áp override."""
    by_id = {c["chunk_id"]: c for c in chunks}
    # Bước 1: gom chunk theo mục, LLM phân loại mục là bệnh / thuốc / khác
    topics = collect_topics(chunks)
    classify_topics(llm, topics, by_id, on_progress)
    used = [t for t in topics if t["kind"] in TOPIC_TYPES][: limit_topics or None]  # limit_topics: thử vài mục trước khi chạy cả sách
    on_log(f"{len(topics)} mục, {len(used)} mục bệnh/thuốc được trích")
    # Bước 2: khớp chính xác tên chủ đề vào từ điển
    linker = Linker(lexicon, allow_new, schema)
    for t in used:
        for et in TOPIC_ENTITY_TYPES[t["kind"]]:
            linker.ref(et, t["title"], t["en"], t.get("alt"))
    # Bước 3: LLM điền ô (slot) quan hệ cho từng mục, theo lô chunk, chạy song song
    jobs = [(t, ids) for t in used for ids in split_batches(t, chunks_per_call)]
    results = run_extractions(llm, schema, jobs, by_id, on_progress)
    # Bước 4: giữ mục có evidence nguyên văn trong chunk; khớp thực thể đầu kia
    stats: Counter[str] = Counter()
    unmapped: list[dict[str, Any]] = []
    grounded: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for t, ids, res in results:
        if res.get("error"):
            stats["llm_failed_calls"] += 1
            on_log(f"lỗi trích mục {t['title']!r} ({ids[0]}...): {res['error']}")
        unmapped += [{**u, "topic": t["title"], "chunk_id": ids[0]} for u in res["unmapped"]]
        for it in res["items"]:
            cid = find_grounded_chunk(it, ids, by_id)
            if cid is None:
                stats["evidence_dropped"] += 1
                continue
            grounded.append((t, it, cid))
            slot = schema.slot(it["slot"])
            assert slot is not None  # `extract` chỉ giữ ô có trong schema
            for rel in slot.relations:
                linker.ref(rel.object_type, it["text"], it["en"])
    # Bước 5: LLM chọn nút cho thuật ngữ chưa khớp chính xác
    linker.resolve_pending(llm, on_progress, on_log)
    # Bước 6: dựng triple (gộp trùng)
    triples = merge_triples([tr for t, it, cid in grounded
                             for tr in build_triples(document_id, t, it, cid, by_id[cid]["page_start"], linker)])
    for t in topics:
        t["links"] = {et: linker.final(et, t["title"], t["en"]).model_dump()
                      for et in TOPIC_ENTITY_TYPES.get(t["kind"], ()) if linker.key(et, t["title"], t["en"]) in linker.refs}
    return triples, topics, unmapped, dict(stats)


# ---------------------------------------------------------------- override của người duyệt
def apply_overrides(triples: list[DocumentTriple], ov: dict[str, Any], schema: GraphSchema = CORE_SCHEMA) -> list[DocumentTriple]:
    """`rejected`: loại triple; `relink`: {triple_id: {"subject"|"object": GraphNodeRef}}; `accepted_nodes`: nút mới được chấp nhận."""
    rejected, accepted = set(ov.get("rejected") or []), set(ov.get("accepted_nodes") or [])
    relink: dict[str, dict[str, Any]] = ov.get("relink") or {}
    out = []
    for t in triples:
        t = t.model_copy(deep=True)
        for side, ref in (relink.get(t.triple_id) or {}).items():
            if side in ("subject", "object"):
                setattr(t, side, GraphNodeRef.model_validate(ref))
        sides = (t.subject, t.object)
        # nút mới của loại do bác sĩ định nghĩa tự được chấp nhận (không có từ điển chuẩn để đối chiếu)
        linked = all(s.node_id and (s.link_method != "new" or s.node_id in accepted or is_doc_type(schema, s.type)) for s in sides)
        t.status = "rejected" if t.triple_id in rejected else "ok" if linked else "unlinked"
        out.append(t)
    return out


def is_doc_type(schema: GraphSchema, type_: str) -> bool:
    e = schema.entity_types.get(type_)
    return e is not None and e.kg == "doc"


def summarize_triples(triples: list[DocumentTriple], topics: list[dict[str, Any]], unmapped: list[dict[str, Any]],
                      stats: dict[str, Any], schema: GraphSchema) -> dict[str, Any]:
    status = Counter(t.status for t in triples)
    refs = {(s.type, s.text, s.en): s for t in triples for s in (t.subject, t.object)}
    link: dict[str, list[int]] = {}
    for (type_, _, _), s in refs.items():
        v = link.setdefault(type_, [0, 0])
        v[1] += 1
        v[0] += bool(s.node_id) and s.link_method != "new"
    summary: dict[str, Any] = {
        "topics": len(topics),
        "topics_used": dict(Counter(t.get("kind", "other") for t in topics)),
        "triples": len(triples), "ok": status["ok"], "unlinked": status["unlinked"], "rejected": status["rejected"],
        "by_relation": dict(Counter(t.relation for t in triples if t.status == "ok")),
        "linked": {schema.entity_types[k].title if k in schema.entity_types else k: f"{a}/{b}" for k, (a, b) in link.items()},
        "new_entities": len({s.node_id for t in triples for s in (t.subject, t.object) if s.link_method == "new"}),
        "unmapped": dict(Counter(u["kind"] for u in unmapped)),
        "evidence_dropped": stats.get("evidence_dropped", 0),
    }
    if stats.get("llm_failed_calls"):
        summary["warnings"] = [f"{stats['llm_failed_calls']} lần gọi AI lỗi — các đoạn đó chưa được trích (xem nhật ký)."]
    if stats.get("llm"):
        summary["llm"] = stats["llm"]
    return summary


def relation_of(t: DocumentTriple, schema: GraphSchema = CORE_SCHEMA) -> Relation | None:
    return schema.relation_of(t.slot, t.relation)
