"""Lưu quan hệ đã duyệt vào đồ thị tri thức (Neo4j)"""
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.dto.base.document import DocumentTriple, GraphNodeRef

from . import StageContext, StageError
from .graph import relation_of


def _pages_label(pages: list[int]) -> str:
    return ", ".join(str(p) for p in pages[:5]) + ("…" if len(pages) > 5 else "")


def run(ctx: StageContext) -> dict:
    graph, lexicon = ctx.require_graph(), ctx.require_lexicon()
    triples = [DocumentTriple.model_validate(x) for x in ctx.files.read_jsonl("triples.jsonl")]
    ok = [t for t in triples if t.status == "ok"]
    if not ok:
        raise StageError("Chưa có quan hệ nào đã khớp đủ hai đầu để lưu — hãy duyệt bước Trích quan hệ trước.")
    printed = {c["chunk_id"]: c["page_printed_start"] for c in ctx.files.read_jsonl("chunks.jsonl")}
    title = ctx.meta().get("title", ctx.document_id)
    ctx.progress(0, 3, "kiểm tra nút trong đồ thị")

    # Nút PrimeKG: id chỉ duy nhất trong từng loại, trong khi Neo4j ràng buộc `Entity.id` duy nhất cho mọi loại.
    # Id đã có nhưng thuộc loại khác thì không nạp (nếu nạp, cạnh sẽ nối nhầm vào nút kia).
    primekg_ids = sorted({s.node_id for t in ok for s in (t.subject, t.object) if s.kg == "primekg" and s.node_id})
    existing = graph.existing_types(primekg_ids)
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    def node_ok(s: GraphNodeRef) -> bool:
        assert s.node_id is not None
        if s.kg == "dermo":
            return True  # DermO đã nạp đủ cả ontology
        if s.kg == "primekg":
            have = existing.get(s.node_id)
            if have is not None:
                return have == s.type
            e = lexicon.get(s.type, s.node_id)
            if e is None:
                return False
            nodes[(s.type, s.node_id)] = {"id": e.id, "name": e.name, "type": s.type, "source": e.source}
            return True
        nodes[(s.type, s.node_id)] = {"id": s.node_id, "name": s.name or s.en or s.text, "type": s.type, "source": "DOC"}
        return True

    # Neo4j gộp cạnh theo (loại quan hệ, hai đầu, tài liệu): hai quan hệ cùng cặp nút (nhắc ở hai chunk) chỉ ra một cạnh, nên gộp
    # ở đây để số cạnh cần lưu khớp với số đếm lại và không mất trích dẫn của quan hệ ghi trước.
    by_key: dict[tuple[str, str, str | None, str, str | None], dict[str, Any]] = {}
    pages_of: dict[tuple[str, str, str | None, str, str | None], set[int]] = {}
    merged = 0
    for t in ok:
        rel = relation_of(t)
        if rel is None:
            skipped["không rõ quan hệ"] += 1
            continue
        if t.subject.node_id == t.object.node_id and t.subject.type == t.object.type:
            skipped["hai đầu trùng nút (tự trỏ về chính nó)"] += 1
            continue
        if not (node_ok(t.subject) and node_ok(t.object)):
            skipped["trùng id khác loại trong Neo4j"] += 1
            continue
        key = (t.relation, t.subject.type, t.subject.node_id, t.object.type, t.object.node_id)
        printed_pages = {printed[c] for c in t.chunk_ids if c in printed}
        if key in by_key:
            e = by_key[key]
            if t.evidence not in e["evidence"].split("\n"):
                e["evidence"] += "\n" + t.evidence
            e["chunk_ids"] = [*e["chunk_ids"], *(c for c in t.chunk_ids if c not in e["chunk_ids"])]
            e["pages"] = sorted({*e["pages"], *t.pages})
            pages_of[key] |= printed_pages
            merged += 1
            continue
        pages_of[key] = set(printed_pages)
        by_key[key] = {
            "relation": t.relation, "display": rel.display, "triple_id": t.triple_id,
            "x": t.subject.node_id, "x_type": t.subject.type, "y": t.object.node_id, "y_type": t.object.type,
            "evidence": t.evidence, "chunk_ids": list(t.chunk_ids), "pages": list(t.pages), "source_ref": "",
        }
        edges.append(by_key[key])
    for key, e in by_key.items():
        pages = sorted(pages_of[key])
        e["source_ref"] = f"{title}, tr. {_pages_label(pages)}" if pages else title
    ctx.progress(1, 3, "ghi vào Neo4j")
    graph.replace_document(ctx.document_id, list(nodes.values()), edges)
    ctx.progress(2, 3, "đếm lại cạnh đã lưu")
    stored = graph.count_edges(ctx.document_id)
    if stored != len(edges):
        raise StageError(f"Số quan hệ đã lưu ({stored}) khác số cần lưu ({len(edges)}) — kiểm tra nút DermO/PrimeKG có trong Neo4j "
                         "(thiếu nút thì cạnh không được tạo).")
    info = {
        "edges": stored, "nodes_added": len(nodes), "by_relation": dict(Counter(e["relation"] for e in edges)),
        "new_entities": sum(1 for n in nodes.values() if n["source"] == "DOC"),
        "indexed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    ctx.files.write_json("graph_index.json", info)
    summary: dict[str, Any] = {k: v for k, v in info.items() if k != "indexed_at"}
    warnings = [f"Bỏ qua {n} quan hệ: {why}." for why, n in skipped.items()]
    if skipped:
        summary["skipped"] = dict(skipped)
    if merged:
        summary["merged"] = merged
        warnings.append(f"Gộp {merged} quan hệ trùng cặp nút vào cạnh đã có (giữ đủ câu trích và trang).")
    if warnings:
        summary["warnings"] = warnings
    return summary
