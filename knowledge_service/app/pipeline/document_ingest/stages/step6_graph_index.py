from collections import Counter
from typing import Any

from app.dto.base.document import DocumentTriple, GraphNodeRef

from ..graph_link import EntityLexicon
from ..graph_schema import GraphSchema
from .step5_graph import relation_of


def build_pages_label(pages: list[int]) -> str:
    return ", ".join(str(p) for p in pages[:5]) + ("…" if len(pages) > 5 else "")


def get_primekg_pairs(triples: list[DocumentTriple]) -> list[tuple[str, str]]:
    """Nút PrimeKG: id chỉ duy nhất trong từng loại (HPO 972 và NCBI 972 là hai nút), nên nút được nhận diện bằng cặp (loại, id)."""
    return sorted({(s.type, s.node_id) for t in triples for s in (t.subject, t.object) if s.kg == "primekg" and s.node_id})


def build_graph_payload(ok: list[DocumentTriple], printed: dict[str, int], title: str, schema: GraphSchema, lexicon: EntityLexicon,
                        existing: set[tuple[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str], int]:
    """Triple đã duyệt -> (nút cần nạp, cạnh, lý do bỏ qua, số quan hệ đã gộp). `existing` = nút PrimeKG đang có trong Neo4j."""
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    def is_node_ok(s: GraphNodeRef) -> bool:
        assert s.node_id is not None
        if s.kg == "dermo":
            return True  # DermO đã nạp đủ cả ontology
        if s.kg == "primekg":
            if (s.type, s.node_id) in existing:
                return True
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
        rel = relation_of(t, schema)
        if rel is None:
            skipped["quan hệ đã bị xoá khỏi danh mục"] += 1
            continue
        if t.subject.node_id == t.object.node_id and t.subject.type == t.object.type:
            skipped["hai đầu trùng nút (tự trỏ về chính nó)"] += 1
            continue
        if not (is_node_ok(t.subject) and is_node_ok(t.object)):
            skipped["thực thể không có trong đồ thị lẫn từ điển"] += 1
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
    # ghi nguồn trích dẫn (tên sách + trang in) cho từng cạnh
    for key, e in by_key.items():
        pages = sorted(pages_of[key])
        e["source_ref"] = f"{title}, tr. {build_pages_label(pages)}" if pages else title
    return list(nodes.values()), edges, skipped, merged


def summarize_graph_payload(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], skipped: Counter[str], merged: int,
                            stored: int) -> dict[str, Any]:
    """Summary cho người duyệt (và nội dung `graph_index.json`, chưa có `indexed_at`)."""
    summary: dict[str, Any] = {
        "edges": stored, "nodes_added": len(nodes), "by_relation": dict(Counter(e["relation"] for e in edges)),
        "new_entities": sum(1 for n in nodes if n["source"] == "DOC"),
    }
    warnings = [f"Bỏ qua {n} quan hệ: {why}." for why, n in skipped.items()]
    if skipped:
        summary["skipped"] = dict(skipped)
    if merged:
        summary["merged"] = merged
        warnings.append(f"Gộp {merged} quan hệ trùng cặp nút vào cạnh đã có (giữ đủ câu trích và trang).")
    if warnings:
        summary["warnings"] = warnings
    return summary
