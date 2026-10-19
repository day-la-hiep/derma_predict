"""Đồ thị tri thức trích từ tài liệu: từ điển khớp, ghi Neo4j, duyệt triple"""
import csv
import json
import threading
from pathlib import Path
from collections.abc import Callable
from typing import Any, LiteralString, cast

from app.dto.base.document import DocumentTriple, GraphNodeRef
from app.dto.request.document import TripleUpdate
from app.dto.response.document import GraphNodeOutput, TripleListOutput, TripleOutput
from app.exception.errors import ConflictError, InvalidError, NotFoundError
from app.infra.neo4j_client import Neo4jClient
from app.repositories.document_repository import DocumentRepository
from pipeline.document_ingest.graph_link import EntityLexicon, LexEntry
from pipeline.document_ingest.graph_schema import CORE_SCHEMA, GraphSchema


def load_lexicon(kg_dir: Path) -> EntityLexicon:
    """PrimeKG đầy đủ (bệnh, triệu chứng, thuốc, gen, tác nhân) + DermO; synonym DermO làm alias cho bệnh MONDO cùng tên."""
    lex = EntityLexicon()
    primekg = kg_dir / "primekg" / "entity_lexicon.csv"
    subgraph: set[tuple[str, str]] = set()
    if (kg_dir / "primekg" / "derma_nodes.csv").exists():
        with (kg_dir / "primekg" / "derma_nodes.csv").open(encoding="utf-8", newline="") as f:
            subgraph = {(r["type"], r["id"]) for r in csv.DictReader(f)}
    if primekg.exists():
        with primekg.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                lex.add(LexEntry(id=r["id"], name=r["name"], type=r["type"], source=r["source"], kg="primekg",
                                 rank=int((r["type"], r["id"]) in subgraph)))
    dermo = kg_dir / "dermo" / "dermo_kg.json"
    if dermo.exists():
        for t in json.loads(dermo.read_text(encoding="utf-8")).get("terms", []):
            if t.get("is_obsolete"):
                continue
            syns = [s for s in t.get("synonyms") or [] if not s.startswith("<")]
            lex.add(LexEntry(id=t["id"], name=t["name"], type="dermo", source="DermO", kg="dermo", aliases=syns))
            # MONDO chỉ có một tên; DermO có đồng nghĩa -> dùng chung để khớp tên sách viết khác
            for mondo in {e.id for n in [t["name"], *syns] for e in lex.exact("disease", n)}:
                for s in [t["name"], *syns]:
                    lex.add_alias("disease", mondo, s)
    return lex


def _cypher(q: str) -> LiteralString:
    # label / relationship type ghép vào câu lệnh lấy từ schema (registry `graph_schema.py` + định nghĩa của bác sĩ đã validate regex)
    return cast(LiteralString, q)


def _label(type_: str) -> str:
    return "DermoTerm" if type_ == "dermo" else "Entity"


class DocumentGraphService:
    def __init__(self, repository: DocumentRepository, neo4j: Neo4jClient | None, lexicon_dir: Path,
                 schema: Callable[[], GraphSchema] = lambda: CORE_SCHEMA) -> None:
        self._repo, self._neo4j, self._lexicon_dir = repository, neo4j, lexicon_dir
        self._schema = schema  # luôn gồm cả quan hệ đang tắt: cạnh đã lưu của chúng vẫn phải xoá/đếm được
        self._lexicon: EntityLexicon | None = None
        self._lock = threading.Lock()
        self._indexed: set[str] = set()

    def lexicon(self) -> EntityLexicon:
        with self._lock:
            if self._lexicon is None:
                self._lexicon = load_lexicon(self._lexicon_dir)
            return self._lexicon

    def set_lexicon(self, lexicon: EntityLexicon) -> None:
        self._lexicon = lexicon

    @property
    def configured(self) -> bool:
        return self._neo4j is not None

    @property
    def neo4j(self) -> Neo4jClient:
        if self._neo4j is None:
            raise InvalidError("Chưa cấu hình đồ thị tri thức (Neo4j).")
        return self._neo4j

    # ---- GraphStore (dùng bởi bước graph / graph_index) ----
    def doc_entities(self) -> list[dict[str, Any]]:
        return self.neo4j.run_sync(
            "MATCH (n) WHERE (n:Entity OR n:DermoTerm) AND n.source = 'DOC' "
            "RETURN n.id AS id, n.name AS name, coalesce(n.type, 'dermo') AS type"
        )

    def existing_types(self, ids: list[str]) -> dict[str, str]:
        rows = self.neo4j.run_sync("MATCH (n:Entity) WHERE n.id IN $ids RETURN n.id AS id, n.type AS type", ids=ids)
        return {r["id"]: r["type"] for r in rows}

    def _ensure_indexes(self) -> None:
        # xoá theo tài liệu không được quét toàn bộ cạnh (có ~2,6 triệu DRUG_DRUG) -> index document_id theo từng loại cạnh
        for t in self._schema().relation_types():
            if t not in self._indexed:
                self.neo4j.run_sync(_cypher(f"CREATE INDEX doc_rel_{t.lower()} IF NOT EXISTS FOR ()-[r:{t}]-() ON (r.document_id)"))
                self._indexed.add(t)

    def _delete_statements(self, document_id: str) -> list[tuple[LiteralString, dict[str, Any]]]:
        out: list[tuple[LiteralString, dict[str, Any]]] = [
            (_cypher(f"MATCH ()-[r:{t} {{document_id: $d}}]->() DELETE r"), {"d": document_id}) for t in self._schema().relation_types()
        ]
        # nút do tài liệu thêm (thực thể mới, hoặc nút PrimeKG chưa có trong subgraph): gỡ tài liệu, hết tài liệu + hết cạnh thì xoá
        for label in ("Entity", "DermoTerm"):
            out.append((_cypher(
                f"MATCH (n:{label}) WHERE $d IN coalesce(n.added_by, []) "
                "SET n.added_by = [x IN n.added_by WHERE x <> $d] "
                "WITH n WHERE size(n.added_by) = 0 AND NOT EXISTS { (n)--() } DELETE n"), {"d": document_id}))
        return out

    def replace_document(self, document_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self._ensure_indexes()
        stmts = self._delete_statements(document_id)
        entity_types = self._schema().entity_types
        for type_ in {n["type"] for n in nodes}:
            rows = [n for n in nodes if n["type"] == type_]
            if type_ == "dermo":
                q = ("UNWIND $rows AS row MERGE (n:DermoTerm {id: row.id}) "
                     "ON CREATE SET n.name = row.name, n.source = row.source, n.synonyms = [], n.added_by = [$d] "
                     "ON MATCH SET n.added_by = CASE WHEN n.added_by IS NULL THEN NULL ELSE n.added_by + $d END")
            else:
                q = (f"UNWIND $rows AS row MERGE (n:Entity {{id: row.id}}) "
                     f"ON CREATE SET n:{entity_types[type_].label}, n.name = row.name, n.type = row.type, n.source = row.source, "
                     "n.added_by = [$d] "
                     "ON MATCH SET n.added_by = CASE WHEN n.added_by IS NULL THEN NULL ELSE n.added_by + $d END")
            stmts.append((_cypher(q), {"rows": rows, "d": document_id}))
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for e in edges:
            groups.setdefault((e["relation"], _label(e["x_type"]), _label(e["y_type"])), []).append(e)
        for (rel, xl, yl), rows in groups.items():
            stmts.append((_cypher(
                f"UNWIND $rows AS row MATCH (x:{xl} {{id: row.x}}), (y:{yl} {{id: row.y}}) "
                f"MERGE (x)-[r:{rel} {{document_id: $d}}]->(y) "
                "SET r.display_relation = row.display, r.source = 'DOC', r.evidence = row.evidence, r.chunk_ids = row.chunk_ids, "
                "r.pages = row.pages, r.source_ref = row.source_ref, r.triple_id = row.triple_id"), {"rows": rows, "d": document_id}))
        self.neo4j.write_sync(stmts)

    def count_edges(self, document_id: str) -> int:
        return sum(self.neo4j.run_sync(_cypher(f"MATCH ()-[r:{t} {{document_id: $d}}]->() RETURN count(r) AS c"), d=document_id)[0]["c"]
                   for t in self._schema().relation_types())

    def delete_relation_edges(self, relation_type: str) -> None:
        # chỉ cạnh từ tài liệu; cạnh gốc PrimeKG/DermO cùng loại (nếu có) không bị đụng
        self.neo4j.run_sync(_cypher(f"MATCH ()-[r:{relation_type} {{source: 'DOC'}}]->() DELETE r"))

    def delete_document(self, document_id: str) -> None:
        """Gỡ mọi cạnh/nút tài liệu đã nạp; tài liệu chưa từng nạp graph thì không đụng tới Neo4j."""
        st = self._repo.status(document_id)["stages"].get("graph_index", {})
        if st.get("state", "not_started") == "not_started":
            return
        self.neo4j.write_sync(self._delete_statements(document_id))

    # ---- API duyệt ----
    def _triples(self, document_id: str) -> list[DocumentTriple]:
        files = self._repo.files_for(document_id)
        if not files.exists("triples.jsonl"):
            raise NotFoundError("triples.jsonl")
        return [DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.jsonl")]

    def list_triples(self, document_id: str, q: str, status: str, relation: str, page: int, page_size: int) -> TripleListOutput:
        rows = self._triples(document_id)
        ql = q.strip().lower()
        picked = [t for t in rows
                  if (not status or t.status == status or (status == "new" and "new" in (t.subject.link_method, t.object.link_method)))
                  and (not relation or t.relation == relation)
                  and (not ql or any(ql in x.lower() for x in (t.subject.text, t.subject.name, t.object.text, t.object.name, t.evidence)))]
        start = (max(page, 1) - 1) * page_size
        ov = self._repo.overrides.get(document_id, "graph")
        return TripleListOutput(
            items=[TripleOutput.model_validate(t.model_dump()) for t in picked[start : start + page_size]],
            total=len(picked), page=page, page_size=page_size,
            counts={
                "all": len(rows),
                **{s: sum(1 for t in rows if t.status == s) for s in ("ok", "unlinked", "rejected")},
                "new": sum(1 for t in rows if "new" in (t.subject.link_method, t.object.link_method)),
                "by_relation": {r: sum(1 for t in rows if t.relation == r) for r in sorted({t.relation for t in rows})},
            },
            accepted_nodes=list(ov.get("accepted_nodes") or []),
        )

    def update_triples(self, document_id: str, body: TripleUpdate) -> None:
        """Lưu sửa tay vào override (stage `graph`); caller áp lại bước để `triples.jsonl` và tóm tắt cập nhật."""
        if not (body.rejected or body.restored or body.relink or body.accept_nodes or body.unaccept_nodes):
            raise InvalidError("Không có thay đổi nào để lưu.")
        files = self._repo.files_for(document_id)
        if not files.exists("triples.auto.jsonl"):
            raise ConflictError("Hãy chạy bước Trích quan hệ trước.")
        ids = {x["triple_id"] for x in files.read_jsonl("triples.auto.jsonl")}
        for tid in [*body.rejected, *body.restored, *[r.triple_id for r in body.relink]]:
            if tid not in ids:
                raise NotFoundError(tid)
        ov = self._repo.overrides.get(document_id, "graph")
        ov["rejected"] = sorted((set(ov.get("rejected") or []) | set(body.rejected)) - set(body.restored))
        ov["accepted_nodes"] = sorted((set(ov.get("accepted_nodes") or []) | set(body.accept_nodes)) - set(body.unaccept_nodes))
        relink: dict[str, dict[str, Any]] = dict(ov.get("relink") or {})
        lex = self.lexicon()
        auto = {x["triple_id"]: DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.auto.jsonl")}
        for r in body.relink:
            picked: GraphNodeRef = getattr(auto[r.triple_id], r.side)
            e = lex.get(picked.type, r.node_id) if r.node_id is not None else None
            if r.node_id is not None and e is None:
                raise NotFoundError(f"{picked.type}:{r.node_id}")
            term = (picked.type, picked.text, picked.en)
            # chủ đề của mục xuất hiện ở hàng chục triple (khi là đầu, khi là đuôi): sửa một lần cho tất cả
            targets = [(tid, sd) for tid, t in auto.items() for sd in ("subject", "object")
                       if (r.same_term and (getattr(t, sd).type, getattr(t, sd).text, getattr(t, sd).en) == term)
                       or (tid == r.triple_id and sd == r.side)]
            for tid, sd in targets:
                cur = dict(relink.get(tid) or {})
                if e is None:  # bỏ sửa tay, quay về kết quả máy
                    cur.pop(sd, None)
                else:
                    side: GraphNodeRef = getattr(auto[tid], sd)
                    cur[sd] = side.model_copy(update={"kg": e.kg, "node_id": e.id, "name": e.name, "link_method": "manual"}).model_dump()
                if cur:
                    relink[tid] = cur
                else:
                    relink.pop(tid, None)
        ov["relink"] = relink
        self._repo.overrides.write(document_id, "graph", ov)

    def search_nodes(self, type_: str, q: str, limit: int) -> list[GraphNodeOutput]:
        if type_ not in self._schema().entity_types:
            raise InvalidError(f"Loại thực thể không hợp lệ: {type_}")
        if not q.strip():
            return []
        return [GraphNodeOutput(kg=e.kg, type=e.type, id=e.id, name=e.name, source=e.source)
                for e in self.lexicon().search(type_, q, limit)]
