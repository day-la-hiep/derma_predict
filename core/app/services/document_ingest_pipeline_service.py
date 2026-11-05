"""Điều khiển pipeline `document_ingest`"""

import asyncio
import importlib
import json
import threading
import traceback
from collections import Counter
from datetime import UTC, datetime
from collections.abc import Callable
from types import ModuleType
from typing import Any

from app.config.constants import (
    DOCUMENT_CANCEL_KEY,
    DOCUMENT_INGEST_CANCEL_CHANNEL,
    DOCUMENT_INGEST_QUEUE,
)
from app.dto.base.document import DocumentTriple
from app.dto.request.document import TocUpdate, TripleUpdate
from app.dto.response.document import DocumentOutput
from app.exception.errors import (
    ConflictError,
    InvalidError,
    NotFoundError,
    PipelineError,
)
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from app.infra.rabbitmq_client import RabbitMQClient
from app.infra.redis_client import RedisClient
from app.models.document_stage import STAGE_BY_ID
from app.repositories.document_repository import DocumentRepository, now_iso
from app.services.document_graph_service import DocumentGraphService
from app.services.graph_schema_service import GraphSchemaService
from app.services.document_service import DocumentService
from pipeline.document_ingest import mapping
from pipeline.document_ingest.graph_link import EntityLexicon, LexEntry
from pipeline.document_ingest.graph_schema import CORE_SCHEMA
from pipeline.document_ingest.stages import (
    StageCancelled,
    StageContext,
    StageError,
    step1_ingest,
    step2_toc,
    step3_chunks,
    step4_index,
    step5_graph,
    step6_graph_index,
)


_GRAPH_STAGES = {"graph", "graph_index"}


def get_stage_module(stage_id: str) -> ModuleType:
    if stage_id not in STAGE_BY_ID:
        raise NotFoundError(stage_id)
    return importlib.import_module(
        f"pipeline.document_ingest.stages.{STAGE_BY_ID[stage_id]['module']}"
    )


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


class DocumentIngestPipelineService:
    """Điều khiển pipeline tài liệu"""

    def __init__(
        self,
        documentService: DocumentService,
        repository: DocumentRepository,
        *,
        docling: DoclingClient | None = None,
        embedding: EmbeddingClient | None = None,
        rabbitmq: RabbitMQClient | None = None,
        redis: RedisClient | None = None,
        graph: DocumentGraphService | None = None,
        graph_schema: GraphSchemaService | None = None,
    ) -> None:
        """`rabbitmq`/`redis` chỉ Core cần (đẩy yêu cầu chạy + Dừng); ingest worker chỉ gọi `execute` nên để trống."""
        self.documentService, self._repo = documentService, repository
        self._rabbitmq, self._redis = rabbitmq, redis
        self._docling, self._embedding = docling, embedding
        self._graph, self._graph_schema = graph, graph_schema

    def make_ctx(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> StageContext:
        profile = DocumentService.read_profile(self._repo, document_id)
        use_llm = STAGE_BY_ID[stage_id]["llm"] and profile.llm.enabled
        if use_llm and llm is None:
            llm = LLMClient(
                profile.llm.model,
                cache=self.documentService.files.scoped("_cache/llm/"),
            )
        return StageContext(
            document_id=document_id,
            files=self._repo.files_for(document_id),
            profile=profile,
            stage_id=stage_id,
            meta=lambda: self._repo.meta(document_id),
            overrides=lambda stage: self._repo.overrides.get(document_id, stage),
            _append_log=lambda stage, message: self._repo.append_log(document_id, stage, message),
            _update_stage=lambda stage, **fields: self._repo.update_stage(document_id, stage, **fields),
            llm=llm if use_llm else None,
            options=options,
            docling=self._docling,
            embedding=self._embedding,
            vectors=self.documentService,
            # từ điển ~70k thực thể: chỉ nạp khi bước cần (lần đầu mất vài giây)
            lexicon=self._graph.lexicon() if self._graph is not None and stage_id in _GRAPH_STAGES else None,
            graph=self._graph if self._graph is not None and self._graph.configured else None,
            # bước graph chỉ trích quan hệ đang bật; graph_index vẫn lưu triple đã duyệt của quan hệ vừa bị tắt
            schema=self._graph_schema.schema(include_disabled=stage_id != "graph") if self._graph_schema is not None else CORE_SCHEMA,
            pdf=lambda: DocumentService.local_pdf(self._repo, document_id),
            cancel=cancel or threading.Event(),
        )

    # ---- IO của bước thuần (ingest, toc): đọc/ghi file ở đây, hàm biến đổi nằm trong pipeline/ ----
    def get_runner(self, stage_id: str) -> Callable[[StageContext], dict[str, Any]]:
        own = {"ingest": self._run_ingest, "toc": self._run_toc, "chunks": self._run_chunks, "index": self._run_index,
               "graph": self._run_graph, "graph_index": self._run_graph_index}
        return own.get(stage_id) or get_stage_module(stage_id).run

    def get_reapplier(self, stage_id: str) -> Callable[[StageContext], dict[str, Any]]:
        own = {"toc": self._reapply_toc, "graph": self._reapply_graph}
        fn = own.get(stage_id) or getattr(get_stage_module(stage_id), "reapply", None)
        if fn is None:
            raise PipelineError(f"bước {stage_id} không có override")
        return fn

    @staticmethod
    def _docling_convert(ctx: StageContext) -> step1_ingest.Convert:
        files, ext = ctx.files, ctx.profile.extraction
        docling, pdf = ctx.require_docling(), ctx.local_pdf()
        key = f"force_ocr={ext.docling_force_ocr};tables={ext.docling_tables}"
        if files.get_text("docling_parts/key.txt") not in (None, key):
            files.delete_prefix("docling_parts/")  # cấu hình đổi: kết quả cũ không dùng lại được
            files.delete_prefix("figures/")
        files.put_text("docling_parts/key.txt", key)

        def convert(first: int, last: int) -> list[dict[str, Any]]:
            part = f"docling_parts/part_{first:05d}_{last:05d}.json"
            if files.exists(part):  # đã đọc ở lần chạy trước (dừng/làm lại không mất)
                return files.read_json(part, [])
            blocks = docling.convert_pages(pdf, first, last, force_ocr=ext.docling_force_ocr, tables=ext.docling_tables)
            files.write_json(part, _save_figures(files, blocks))
            return blocks

        return convert

    def _run_ingest(self, ctx: StageContext) -> dict[str, Any]:
        files, ext = ctx.files, ctx.profile.extraction
        if not files.exists("source.pdf"):
            raise StageError("Không tìm thấy file PDF của sách.")
        convert = self._docling_convert(ctx) if ext.engine == "docling" else None
        if convert is None:
            files.delete_prefix("figures/")  # pdftotext không trích ảnh; xoá ảnh của lần chạy docling trước (nếu có)
        rows, figures, summary = step1_ingest.extract_pages(
            ctx.local_pdf(), ext, document_id=ctx.document_id, pages_opt=ctx.options.get("pages"),
            convert=convert, on_progress=ctx.progress, on_log=ctx.log,
        )
        files.write_jsonl("pages.jsonl", rows)
        for f in figures:
            key = f.pop("image_key")
            f["image_file"] = {"file_name": key.split("/")[-1], "storage_key": files.key(key), "content_type": "image/png"}
        files.write_json("figures.json", figures)
        return summary

    def _run_toc(self, ctx: StageContext) -> dict[str, Any]:
        llm = ctx.require_llm()
        auto = step2_toc.read_toc(
            ctx.local_pdf, ctx.files.read_jsonl("pages.jsonl"), ctx.profile.extraction, llm, ctx.docling,
            ctx.options.get("pages"), ctx.progress, ctx.log,
        )
        ctx.files.write_json("toc.auto.json", auto)
        return self._reapply_toc(ctx)

    def _build_toc_file(self, ctx: StageContext, rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
        """Áp override + tính độ lệch/neo từ `toc.auto.json`, ghi `toc.json` (dùng cho bước Mục lục và Chia đoạn)."""
        auto = ctx.files.read_json("toc.auto.json", None)
        if auto is None:
            raise StageError("Chưa đọc mục lục — hãy làm bước Mục lục trước.")
        doc = mapping.build_toc(auto, ctx.overrides("toc"), rows, total)
        ctx.files.write_json("toc.json", doc)
        return doc

    def _reapply_toc(self, ctx: StageContext) -> dict[str, Any]:
        rows = ctx.files.read_jsonl("pages.jsonl")
        has_text = bool(rows) or ctx.files.exists("source.pdf")
        doc = self._build_toc_file(ctx, rows, step2_toc.count_pages(rows, ctx.local_pdf) if has_text else 0)
        summary = step2_toc.summarize_toc(doc)
        if ctx.llm is not None:
            summary["llm"] = ctx.llm.stats
        return summary

    def _run_chunks(self, ctx: StageContext) -> dict[str, Any]:
        files = ctx.files
        all_rows = files.read_jsonl("pages.jsonl")
        rows = [r for r in all_rows if not r.get("noise")]
        if not rows:
            raise StageError("Chưa đọc nội dung sách — hãy làm bước Đọc nội dung trước.")
        if not files.exists("toc.auto.json"):
            raise StageError("Chưa có mục lục — hãy làm bước Mục lục trước.")
        ctx.progress(0, 2, "tính lại độ lệch + neo")
        doc = self._build_toc_file(ctx, all_rows, max(r["page"] for r in rows))  # dữ liệu trang có thể mới hơn lần duyệt mục lục
        chunks, review, summary = step3_chunks.cut_chunks(
            doc, rows, ctx.profile.chunking, document_id=ctx.document_id, document_title=ctx.meta().get("title", ""),
            figures=files.read_json("figures.json", []) or [], on_progress=ctx.progress,
        )
        files.write_jsonl("chunks.jsonl", chunks)
        files.write_json("review/chunks.json", review)
        return summary

    def _run_index(self, ctx: StageContext) -> dict[str, Any]:
        return self.index_document_chunks(ctx.document_id, ctx.progress)

    def index_document_chunks(self, document_id: str, on_progress: Callable[[int, int, str], None] = lambda *_: None) -> dict[str, Any]:
        """Embedding + nạp Qdrant từ `chunks.jsonl`; không ghi trạng thái stage nên reindex dùng lại được."""
        files = self._repo.files_for(document_id)
        chunks = files.read_jsonl("chunks.jsonl")
        if not chunks:
            raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
        if self._embedding is None:
            raise StageError("Chưa cấu hình công cụ tạo vector (embedding).")
        vectors, total = self.documentService, len(chunks) * 2
        extra: dict[str, Any] = {
            "document_title": self._repo.meta(document_id).get("title", document_id),
            "source_bucket": files.bucket,
            "source_pdf": files.key("source.pdf"),
        }
        on_progress(0, len(chunks), "chuẩn bị kho tri thức")
        embeddings, dim, model = step4_index.embed_chunks(chunks, self._embedding, lambda done, _t, msg: on_progress(done, total, msg))
        vectors.ensure_collection(dim)
        vectors.delete_chunks(document_id)  # bỏ các đoạn cũ của tài liệu (đã đổi hoặc không còn)
        language = DocumentService.read_profile(self._repo, document_id).indexing.text_language
        batch = step4_index.BATCH
        for i in range(0, len(chunks), batch):
            vectors.upsert_chunks(document_id, chunks[i : i + batch], embeddings[i : i + batch], extra, language=language)
            on_progress(len(chunks) + min(i + batch, len(chunks)), total, "lưu vào Qdrant")
        stored = vectors.count_chunks(document_id)
        if stored != len(chunks):
            raise StageError(f"Số đoạn đã lưu ({stored}) khác số đoạn cần lưu ({len(chunks)}).")
        info = {"collection": vectors.collection, "points": stored, "embedding_model": model, "dimension": dim,
                "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")}
        files.write_json("index.json", info)
        return {"points": stored, "collection": info["collection"], "embedding_model": model, "dimension": dim}

    @staticmethod
    def _load_lexicon(ctx: StageContext) -> EntityLexicon:
        lexicon = ctx.require_lexicon()
        if ctx.graph is not None:  # thực thể mới đã nạp từ tài liệu trước cũng là từ điển để khớp
            for n in ctx.graph.doc_entities():
                if n.get("type") in ctx.schema.entity_types:
                    lexicon.add(LexEntry(id=n["id"], name=n["name"], type=n["type"], source="DOC", kg="doc"))
        return lexicon

    def _run_graph(self, ctx: StageContext) -> dict[str, Any]:
        files = ctx.files
        llm = ctx.require_llm()
        ctx.require_lexicon()
        chunks = files.read_jsonl("chunks.jsonl")
        if not chunks:
            raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
        triples, topics, unmapped, stats = step5_graph.extract_triples(
            chunks, llm, self._load_lexicon(ctx), ctx.schema, document_id=ctx.document_id,
            allow_new=ctx.profile.graph.allow_new_entities, chunks_per_call=ctx.profile.graph.chunks_per_call,
            limit_topics=int(ctx.options.get("limit_topics") or 0), on_progress=ctx.progress, on_log=ctx.log,
        )
        files.write_json("graph/topics.json", topics)
        files.write_json("graph/unmapped.json", unmapped)
        files.write_json("graph/stats.json", {**stats, "llm": llm.stats})
        files.write_jsonl("triples.auto.jsonl", [x.model_dump() for x in triples])
        return self._reapply_graph(ctx)

    def _reapply_graph(self, ctx: StageContext) -> dict[str, Any]:
        files = ctx.files
        auto = [DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.auto.jsonl")]
        if not auto and not files.exists("triples.auto.jsonl"):
            raise StageError("Chưa trích quan hệ — hãy chạy bước Trích quan hệ trước.")
        triples = step5_graph.apply_overrides(auto, ctx.overrides("graph"), ctx.schema)
        files.write_jsonl("triples.jsonl", [t.model_dump() for t in triples])
        return step5_graph.summarize_triples(
            triples, files.read_json("graph/topics.json", []) or [], files.read_json("graph/unmapped.json", []) or [],
            files.read_json("graph/stats.json", {}) or {}, ctx.schema,
        )

    def _run_graph_index(self, ctx: StageContext) -> dict[str, Any]:
        files, graph, lexicon = ctx.files, ctx.require_graph(), ctx.require_lexicon()
        # triple đã duyệt (status ok) + trang in của chunk để ghi nguồn
        ok = [t for t in (DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.jsonl")) if t.status == "ok"]
        if not ok:
            raise StageError("Chưa có quan hệ nào đã khớp đủ hai đầu để lưu — hãy duyệt bước Trích quan hệ trước.")
        printed = {c["chunk_id"]: c["page_printed_start"] for c in files.read_jsonl("chunks.jsonl")}
        ctx.progress(0, 3, "kiểm tra nút trong đồ thị")
        existing = graph.existing_nodes(step6_graph_index.get_primekg_pairs(ok))
        nodes, edges, skipped, merged = step6_graph_index.build_graph_payload(
            ok, printed, ctx.meta().get("title", ctx.document_id), ctx.schema, lexicon, existing,
        )
        ctx.progress(1, 3, "ghi vào Neo4j")
        graph.replace_document(ctx.document_id, nodes, edges)
        ctx.progress(2, 3, "đếm lại cạnh đã lưu")
        stored = graph.count_edges(ctx.document_id)
        if stored != len(edges):
            raise StageError(f"Số quan hệ đã lưu ({stored}) khác số cần lưu ({len(edges)}) — kiểm tra nút DermO/PrimeKG có trong Neo4j "
                             "(thiếu nút thì cạnh không được tạo).")
        summary = step6_graph_index.summarize_graph_payload(nodes, edges, skipped, merged, stored)
        info = {k: summary[k] for k in ("edges", "nodes_added", "by_relation", "new_entities")}
        files.write_json("graph_index.json", {**info, "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")})
        return summary

    # ---- chạy bước: check_runnable -> begin -> execute ----
    def check_runnable(
        self, document_id: str, stage_id: str, *, force: bool = False
    ) -> None:
        """Ném lỗi nếu chưa chạy được"""
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        status = self._repo.status(document_id)["stages"]
        running = [
            sid for sid, s in status.items() if s.get("state") == "running"
        ]
        if running:
            raise ConflictError(
                f"Đang xử lý bước “{STAGE_BY_ID[running[0]]['title']}” — hãy chờ xong hoặc dừng trước."
            )
        block = (
            []
            if force
            else DocumentService.blocking_deps(self._repo, document_id, stage_id, status)
        )
        if block:
            raise PipelineError(
                "Cần xác nhận các bước trước: "
                + ", ".join(STAGE_BY_ID[b]["title"] for b in block)
                + "."
            )
        DocumentService.read_profile(self._repo, document_id)

    def begin(
        self, document_id: str, stage_id: str, options: dict[str, Any]
    ) -> None:
        """Ghi trạng thái `running` (xoá nhật ký cũ, đánh dấu stale các bước hạ nguồn)."""
        self._repo.reset_log(document_id, stage_id)
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(
            document_id,
            stage_id,
            state="running",
            started_at=now_iso(),
            finished_at=None,
            error=None,
            options=options,
            progress={"done": 0, "total": 0, "message": "bắt đầu"},
            summary=None,
            approved_at=None,
        )

    def execute(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        *,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Chạy bước đã `begin`, ghi kết quả `pending_review` / `failed` / `cancelled` cùng nhật ký."""
        try:
            ctx = self.make_ctx(document_id, stage_id, options, llm, cancel)
            ctx.log(f"bắt đầu bước {stage_id} options={options}")
            summary = self.get_runner(stage_id)(ctx)
        except StageCancelled:
            self._repo.append_log(document_id, stage_id, "đã huỷ")
            self._repo.update_stage(
                document_id, stage_id, state="cancelled", finished_at=now_iso()
            )
            raise
        except Exception as e:
            self._repo.append_log(
                document_id,
                stage_id,
                "LỖI: " + "".join(traceback.format_exception(e))[-1500:],
            )
            msg = (
                str(e)
                if isinstance(e, (StageError, InvalidError))
                else f"{type(e).__name__}: {e}"
            )
            self._repo.update_stage(
                document_id, stage_id, state="failed", finished_at=now_iso(), error=msg
            )
            raise
        self._repo.update_stage(
            document_id,
            stage_id,
            state="pending_review",
            finished_at=now_iso(),
            summary=summary,
            error=None,
            progress={"done": 1, "total": 1, "message": "xong"},
        )
        if stage_id == "ingest":  # kết quả bước ingest là `Document.ingested_file` -> ghi thành dòng `files`
            self._repo.set_ingested_file(document_id, "pages.jsonl", "application/x-ndjson")
        ctx.log(f"xong: {summary}")
        return summary

    def run_stage(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any] | None = None,
        *,
        force: bool = False,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Kiểm tra + chạy trọn một bước trong thread hiện tại."""
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        options = options or {}
        self.check_runnable(document_id, stage_id, force=force)
        self.begin(document_id, stage_id, options)
        return self.execute(document_id, stage_id, options, llm=llm, cancel=cancel)

    # ---- API admin: chạy nền / dừng / duyệt / áp lại, trả về trạng thái tài liệu ----
    async def start_stage(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        force: bool,
    ) -> DocumentOutput:
        """Kiểm tra điều kiện, ghi `running` rồi đẩy yêu cầu cho ingest worker; trả về ngay."""
        if self._rabbitmq is None or self._redis is None:
            raise RuntimeError("start_stage cần RabbitMQ + Redis (chỉ Core có)")
        await asyncio.to_thread(self._prepare, document_id, stage_id, options, force)
        await self._redis.delete(DOCUMENT_CANCEL_KEY.format(document_id=document_id, stage_id=stage_id))
        try:
            await self._rabbitmq.publish(
                DOCUMENT_INGEST_QUEUE,
                json.dumps({"document_id": document_id, "stage_id": stage_id, "options": options}).encode(),
            )
        except Exception as e:
            # không đẩy được thì không có ai chạy — đừng để bước kẹt ở `running`
            await asyncio.to_thread(
                self._repo.update_stage, document_id, stage_id,
                state="failed", finished_at=now_iso(), error=f"Không gửi được yêu cầu cho worker: {e}",
            )
            raise
        return await asyncio.to_thread(self.documentService.get_document, document_id)

    def _prepare(self, document_id: str, stage_id: str, options: dict[str, Any], force: bool) -> None:
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        self.check_runnable(document_id, stage_id, force=force)
        self.begin(document_id, stage_id, options)

    async def cancel_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        if self._redis is None:
            raise RuntimeError("cancel_stage cần Redis (chỉ Core có)")
        if not await asyncio.to_thread(self._repo.exists, document_id):
            raise NotFoundError(document_id)
        status = await asyncio.to_thread(self._repo.status, document_id)
        if status["stages"].get(stage_id, {}).get("state") != "running":
            raise ConflictError("Bước này hiện không chạy.")
        # bước có thể còn nằm trong queue (Pub/Sub không replay) nên đặt thêm cờ key; worker kiểm tra cờ khi nhận message
        await self._redis.set_value(
            DOCUMENT_CANCEL_KEY.format(document_id=document_id, stage_id=stage_id), "1", ex_seconds=3600
        )
        await self._redis.publish(DOCUMENT_INGEST_CANCEL_CHANNEL, json.dumps({"document_id": document_id, "stage_id": stage_id}))
        return await asyncio.to_thread(self.documentService.get_document, document_id)

    def approve_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        self.approve(document_id, stage_id)
        return self.documentService.get_document(document_id)

    def reapply_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        self.reapply(document_id, stage_id)
        return self.documentService.get_document(document_id)

    def update_triples(self, document_id: str, body: TripleUpdate) -> DocumentOutput:
        """Lưu duyệt quan hệ rồi áp lại bước `graph` (bước quay về chờ duyệt, `graph_index` thành stale)."""
        if self._graph is None:
            raise PipelineError("Chưa cấu hình đồ thị tri thức.")
        self._graph.update_triples(document_id, body)
        return self.reapply_stage(document_id, "graph")

    def update_toc(
        self, document_id: str, body: TocUpdate
    ) -> DocumentOutput:
        """Lưu chỉnh sửa mục lục rồi áp lại bước `toc` (bước quay về chờ duyệt, các bước sau thành stale)."""
        self.documentService.update_toc(document_id, body)
        return self.reapply_stage(document_id, "toc")

    # ---- duyệt / áp override ----
    def approve(self, document_id: str, stage_id: str) -> dict[str, Any]:
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        st = self._repo.status(document_id)["stages"].get(stage_id)
        if st is None:
            raise NotFoundError(stage_id)
        if st.get("state") != "pending_review":
            raise PipelineError(
                "Chỉ xác nhận được bước đang ở trạng thái chờ xác nhận."
            )
        return self._repo.update_stage(
            document_id, stage_id, state="approved", approved_at=now_iso()
        )

    def reapply(self, document_id: str, stage_id: str) -> dict[str, Any]:
        """Áp lại override của người duyệt (nhanh, không LLM). Dữ liệu bước đổi nên bước quay về chờ duyệt và các bước hạ nguồn thành stale."""
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        reapply_fn = self.get_reapplier(stage_id)
        st = self._repo.status(document_id)["stages"][stage_id]
        if st.get("state") in {"not_started", "running"}:
            raise PipelineError(
                f"bước {stage_id} chưa có kết quả để áp override (hiện: {st.get('state')})"
            )
        summary = reapply_fn(
            self.make_ctx(document_id, stage_id, st.get("options") or {})
        )
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(
            document_id, stage_id, state="pending_review", summary=summary, approved_at=None
        )
        return summary
