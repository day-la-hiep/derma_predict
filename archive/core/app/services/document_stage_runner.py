"""Chạy từng bước của pipeline `document_ingest`: đọc/ghi file, gọi hàm thuần trong `pipeline/`."""

import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from app.dto.base.document import DocumentChunk, DocumentTriple
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from app.models.document_profile import Profile
from app.models.document_stage import STAGE_BY_ID
from app.repositories.document_repository import DocumentRepository
from app.services.document_graph_service import DocumentGraphService
from app.services.document_service import DocumentService, get_local_pdf, read_profile
from app.services.file_store_service import FileStoreService
from app.services.graph_schema_service import GraphSchemaService
from pipeline.document_ingest import mapping
from pipeline.document_ingest.graph_link import EntityLexicon, LexEntry
from pipeline.document_ingest.graph_schema import CORE_SCHEMA, GraphSchema
from pipeline.document_ingest.types import DoclingBlock, PageRow, TocAuto, TocDoc
from pipeline.document_ingest.stages import (
    StageCancelled,
    StageError,
    step1_ingest,
    step2_toc,
    step3_chunks,
    step4_index,
    step5_graph,
    step6_graph_index,
)


@dataclass
class StageRunState:
    """Trạng thái một lần chạy bước (do service giữ; pipeline không biết)."""

    document_id: str
    stage_id: str
    options: dict[str, Any]
    profile: Profile
    files: FileStoreService  # đã scope về document/<document_id>/
    llm: LLMClient | None
    progress: Callable[[int, int, str], None]  # ném StageCancelled khi người dùng bấm Dừng
    log: Callable[[str], None]
    get_pdf: Callable[[], Path]  # bản sao PDF trên đĩa, chỉ tải khi stage cần


def get_call_limit(raw: Any) -> int:
    try:
        n = int(raw or 0)
    except (TypeError, ValueError):
        raise StageError(f"Số lượt thử phải là một số nguyên (vd 20), nhận được {raw!r}.") from None
    if n < 0:
        raise StageError("Số lượt thử không được âm.")
    return n


def _save_figures(files: Any, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ghi ảnh hình minh hoạ ra `figures/` rồi thay bytes bằng `image_key` để part JSON vẫn serialize được."""
    per_page: Counter[int] = Counter()
    for blk in blocks:
        png = blk.pop("image_png", None)
        if blk["label"] != "figure" or png is None:
            continue
        per_page[blk["page"]] += 1
        blk["image_key"] = f"figures/p{blk['page']:05d}_{per_page[blk['page']]:02d}.png"
        files.put_bytes(blk["image_key"], png, "image/png")
    return blocks


class DocumentStageRunner:
    def __init__(self, documents: DocumentService, repository: DocumentRepository, *, docling: DoclingClient | None = None,
                 embedding: EmbeddingClient | None = None, graph: DocumentGraphService | None = None,
                 graph_schema: GraphSchemaService | None = None) -> None:
        self.documents, self._repo = documents, repository
        self._docling, self._embedding = docling, embedding
        self._graph, self._graph_schema = graph, graph_schema

    # ---- trạng thái + phụ thuộc của một lần chạy bước ----
    def make_state(self, document_id: str, stage_id: str, options: dict[str, Any], llm: LLMClient | None = None,
                  cancel: threading.Event | None = None) -> StageRunState:
        profile = read_profile(self._repo, document_id)
        use_llm = STAGE_BY_ID[stage_id]["llm"] and profile.llm.enabled
        if use_llm and llm is None:
            llm = LLMClient(profile.llm.model, cache=self.documents.files.scoped("_cache/llm/"))
        return StageRunState(
            document_id=document_id, stage_id=stage_id, options=options, profile=profile,
            files=self._repo.files_for(document_id), llm=llm if use_llm else None,
            get_pdf=partial(get_local_pdf, self._repo, document_id),
            progress=self._make_progress(document_id, stage_id, cancel or threading.Event()),
            log=lambda message: self._repo.append_log(document_id, stage_id, message),
        )

    def _make_progress(self, document_id: str, stage_id: str, cancel: threading.Event) -> Callable[[int, int, str], None]:
        """Callback tiến độ của bước: kiểm tra Dừng, rồi ghi DB (giới hạn ~2 lần/giây)."""
        lock, last_write = threading.Lock(), [0.0]

        def progress(done: int, total: int, message: str = "") -> None:
            if cancel.is_set():
                raise StageCancelled()
            with lock:
                now = time.monotonic()
                if done < total and now - last_write[0] < 0.5:
                    return
                last_write[0] = now
            self._repo.update_stage(document_id, stage_id, progress={"done": done, "total": total, "message": message})

        return progress

    @staticmethod
    def _need_llm(run: StageRunState) -> LLMClient:
        if run.llm is None:
            raise StageError("Bước này cần LLM nhưng profile đặt llm.enabled=false")
        return run.llm

    def _get_lexicon(self, schema: GraphSchema | None = None) -> EntityLexicon:
        """Từ điển ~70k thực thể (lần đầu nạp mất vài giây). Có `schema` thì thêm thực thể mới đã nạp từ tài liệu trước."""
        lexicon = self._graph.lexicon() if self._graph is not None else None
        if lexicon is None or not len(lexicon):
            raise StageError("Chưa có từ điển thực thể PrimeKG/DermO (chạy `python data_ingest/run.py primekg normalize`).")
        if schema is not None and self._graph is not None and self._graph.configured:
            for n in self._graph.doc_entities():
                if n.get("type") in schema.entity_types:
                    lexicon.add(LexEntry(id=n["id"], name=n["name"], type=n["type"], source="DOC", kg="doc"))
        return lexicon

    def _get_schema(self, stage_id: str) -> GraphSchema:
        # bước graph chỉ trích quan hệ đang bật; graph_index vẫn lưu triple đã duyệt của quan hệ vừa bị tắt
        return self._graph_schema.schema(include_disabled=stage_id != "graph") if self._graph_schema is not None else CORE_SCHEMA

    def _docling_convert(self, run: StageRunState) -> step1_ingest.Convert:
        files, ext = run.files, run.profile.extraction
        if self._docling is None:
            raise StageError("Chưa cấu hình công cụ nhận dạng chữ (Docling).")
        docling, pdf = self._docling, run.get_pdf()
        key = f"force_ocr={ext.docling_force_ocr};tables={ext.docling_tables}"
        if files.get_text("docling_parts/key.txt") not in (None, key):
            files.delete_prefix("docling_parts/")  # cấu hình đổi: kết quả cũ không dùng lại được
            files.delete_prefix("figures/")
        files.put_text("docling_parts/key.txt", key)

        def convert(first: int, last: int) -> list[DoclingBlock]:
            part = f"docling_parts/part_{first:05d}_{last:05d}.json"
            if files.exists(part):  # đã đọc ở lần chạy trước (dừng/làm lại không mất)
                return [DoclingBlock.model_validate(b) for b in files.read_json(part, [])]
            blocks = _save_figures(files, docling.convert_pages(pdf, first, last, force_ocr=ext.docling_force_ocr, tables=ext.docling_tables))
            files.write_json(part, blocks)
            return [DoclingBlock.model_validate(b) for b in blocks]

        return convert

    def run_ingest(self, run: StageRunState) -> dict[str, Any]:
        files, ext = run.files, run.profile.extraction
        if not files.exists("source.pdf"):
            raise StageError("Không tìm thấy file PDF của sách.")
        convert = self._docling_convert(run) if ext.engine == "docling" else None
        if convert is None:
            files.delete_prefix("figures/")  # pdftotext không trích ảnh; xoá ảnh của lần chạy docling trước (nếu có)
        rows, figures, summary = step1_ingest.extract_pages(
            run.get_pdf(), ext, document_id=run.document_id, pages_opt=run.options.get("pages"),
            convert=convert, on_progress=run.progress, on_log=run.log,
        )
        files.write_jsonl("pages.jsonl", [r.model_dump() for r in rows])
        files.write_json("figures.json", [
            {**f.model_dump(exclude={"image_key"}),
             "image_file": {"file_name": f.image_key.split("/")[-1], "storage_key": files.key(f.image_key), "content_type": "image/png"}}
            for f in figures
        ])
        return summary

    def run_toc(self, run: StageRunState) -> dict[str, Any]:
        llm = self._need_llm(run)
        auto = step2_toc.read_toc(
            run.get_pdf, self._read_pages(run), run.profile.extraction, llm, self._docling,
            run.options.get("pages"), run.progress, run.log,
        )
        run.files.write_json("toc.auto.json", auto.model_dump())
        return self.reapply_toc(run)

    @staticmethod
    def _read_pages(run: StageRunState) -> list[PageRow]:
        return [PageRow.model_validate(r) for r in run.files.read_jsonl("pages.jsonl")]

    def _build_toc_file(self, run: StageRunState, rows: list[PageRow], total: int) -> TocDoc:
        """Áp override + tính độ lệch/neo từ `toc.auto.json`, ghi `toc.json` (dùng cho bước Mục lục và Chia đoạn)."""
        raw = run.files.read_json("toc.auto.json", None)
        if raw is None:
            raise StageError("Chưa đọc mục lục — hãy làm bước Mục lục trước.")
        doc = mapping.build_toc(TocAuto.model_validate(raw), self._repo.overrides.get(run.document_id, "toc"), rows, total)
        run.files.write_json("toc.json", doc.model_dump())
        return doc

    def reapply_toc(self, run: StageRunState) -> dict[str, Any]:
        rows = self._read_pages(run)
        has_text = bool(rows) or run.files.exists("source.pdf")
        doc = self._build_toc_file(run, rows, step2_toc.count_pages(rows, run.get_pdf) if has_text else 0)
        summary = step2_toc.summarize_toc(doc)
        if run.llm is not None:
            summary["llm"] = run.llm.stats
        return summary

    def run_chunks(self, run: StageRunState) -> dict[str, Any]:
        files = run.files
        all_rows = self._read_pages(run)
        rows = [r for r in all_rows if not r.noise]
        if not rows:
            raise StageError("Chưa đọc nội dung sách — hãy làm bước Đọc nội dung trước.")
        if not files.exists("toc.auto.json"):
            raise StageError("Chưa có mục lục — hãy làm bước Mục lục trước.")
        run.progress(0, 2, "tính lại độ lệch + neo")
        doc = self._build_toc_file(run, all_rows, max(r.page for r in rows))  # dữ liệu trang có thể mới hơn lần duyệt mục lục
        chunks, review, summary = step3_chunks.cut_chunks(
            doc, rows, run.profile.chunking, document_id=run.document_id, document_title=self._repo.meta(run.document_id).get("title", ""),
            figure_pages=[(f["figure_id"], f["page"]) for f in files.read_json("figures.json", []) or []], on_progress=run.progress,
        )
        files.write_jsonl("chunks.jsonl", [c.model_dump() for c in chunks])
        files.write_json("review/chunks.json", review)
        return summary

    def index_document_chunks(self, document_id: str, on_progress: Callable[[int, int, str], None] = lambda *_: None) -> dict[str, Any]:
        """Embedding + nạp Qdrant từ `chunks.jsonl`; không ghi trạng thái stage nên reindex dùng lại được."""
        files = self._repo.files_for(document_id)
        chunks = files.read_jsonl("chunks.jsonl")
        if not chunks:
            raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
        if self._embedding is None:
            raise StageError("Chưa cấu hình công cụ tạo vector (embedding).")
        total = len(chunks) * 2
        extra: dict[str, Any] = {
            "document_title": self._repo.meta(document_id).get("title", document_id),
            "source_bucket": files.bucket,
            "source_pdf": files.key("source.pdf"),
        }
        on_progress(0, len(chunks), "chuẩn bị kho tri thức")
        embeddings, dim, model = step4_index.embed_chunks(chunks, self._embedding, lambda done, _t, msg: on_progress(done, total, msg))
        self.documents.ensure_collection(dim)
        self.documents.delete_chunks(document_id)  # bỏ các đoạn cũ của tài liệu (đã đổi hoặc không còn)
        language = read_profile(self._repo, document_id).indexing.text_language
        batch = step4_index.BATCH
        for i in range(0, len(chunks), batch):
            self.documents.upsert_chunks(document_id, chunks[i : i + batch], embeddings[i : i + batch], extra, language=language)
            on_progress(len(chunks) + min(i + batch, len(chunks)), total, "lưu vào Qdrant")
        stored = self.documents.count_chunks(document_id)
        if stored != len(chunks):
            raise StageError(f"Số đoạn đã lưu ({stored}) khác số đoạn cần lưu ({len(chunks)}).")
        info = {"collection": self.documents.collection, "points": stored, "embedding_model": model, "dimension": dim,
                "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")}
        files.write_json("index.json", info)
        return {"points": stored, "collection": info["collection"], "embedding_model": model, "dimension": dim}

    def run_graph(self, run: StageRunState) -> dict[str, Any]:
        files, schema = run.files, self._get_schema(run.stage_id)
        llm = self._need_llm(run)
        lexicon = self._get_lexicon(schema)
        chunks = [DocumentChunk.model_validate(c) for c in files.read_jsonl("chunks.jsonl")]
        if not chunks:
            raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
        triples, units, unmapped, stats = step5_graph.extract_triples(
            chunks, llm, lexicon, schema, document_id=run.document_id,
            allow_new=run.profile.graph.allow_new_entities, chunks_per_call=run.profile.graph.chunks_per_call,
            limit_calls=get_call_limit(run.options.get("limit_calls")), on_progress=run.progress, on_log=run.log,
        )
        files.write_json("graph/units.json", units)
        files.write_json("graph/unmapped.json", unmapped)
        files.write_json("graph/stats.json", {**stats, "llm": llm.stats})
        files.write_jsonl("triples.auto.jsonl", [x.model_dump() for x in triples])
        return self.reapply_graph(run)

    def reapply_graph(self, run: StageRunState) -> dict[str, Any]:
        files, schema = run.files, self._get_schema(run.stage_id)
        auto = [DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.auto.jsonl")]
        if not auto and not files.exists("triples.auto.jsonl"):
            raise StageError("Chưa trích quan hệ — hãy chạy bước Trích quan hệ trước.")
        triples = step5_graph.apply_overrides(auto, self._repo.overrides.get(run.document_id, "graph"), schema)
        files.write_jsonl("triples.jsonl", [t.model_dump() for t in triples])
        return step5_graph.summarize_triples(
            triples, files.read_json("graph/units.json", []) or [], files.read_json("graph/unmapped.json", []) or [],
            files.read_json("graph/stats.json", {}) or {}, schema,
        )

    def run_graph_index(self, run: StageRunState) -> dict[str, Any]:
        if self._graph is None or not self._graph.configured:
            raise StageError("Chưa cấu hình đồ thị tri thức (Neo4j).")
        files, graph, lexicon = run.files, self._graph, self._get_lexicon()
        schema = self._get_schema(run.stage_id)
        # triple đã duyệt (status ok) + trang in của chunk để ghi nguồn
        ok = [t for t in (DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.jsonl")) if t.status == "ok"]
        if not ok:
            raise StageError("Chưa có quan hệ nào đã khớp đủ hai đầu để lưu — hãy duyệt bước Trích quan hệ trước.")
        printed = {c["chunk_id"]: c["page_printed_start"] for c in files.read_jsonl("chunks.jsonl")}  # chỉ cần 2 field: không dựng cả DocumentChunk
        run.progress(0, 3, "kiểm tra nút trong đồ thị")
        existing = graph.existing_nodes(step6_graph_index.get_primekg_pairs(ok))
        nodes, edges, skipped, merged = step6_graph_index.build_graph_payload(
            ok, printed, self._repo.meta(run.document_id).get("title", run.document_id), schema, lexicon, existing,
        )
        run.progress(1, 3, "ghi vào Neo4j")
        graph.replace_document(run.document_id, nodes, edges)
        run.progress(2, 3, "đếm lại cạnh đã lưu")
        stored = graph.count_edges(run.document_id)
        if stored != len(edges):
            raise StageError(f"Số quan hệ đã lưu ({stored}) khác số cần lưu ({len(edges)}) — kiểm tra nút DermO/PrimeKG có trong Neo4j "
                             "(thiếu nút thì cạnh không được tạo).")
        summary = step6_graph_index.summarize_graph_payload(nodes, edges, skipped, merged, stored)
        info = {k: summary[k] for k in ("edges", "nodes_added", "by_relation", "new_entities")}
        files.write_json("graph_index.json", {**info, "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")})
        return summary
