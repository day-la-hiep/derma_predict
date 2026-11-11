"""Điều khiển pipeline `document_ingest`"""

import asyncio
import json
import threading
import logging
from collections.abc import Callable
from typing import Any

from derma_shared.constants import (
    DOCUMENT_CANCEL_KEY,
    DOCUMENT_INGEST_CANCEL_CHANNEL,
    DOCUMENT_INGEST_QUEUE,
)
from app.dto.api import DocumentOutput, TocUpdate, TripleUpdate
from derma_shared.errors import (
    ConflictError,
    InvalidError,
    NotFoundError,
    PipelineError,
)
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from derma_shared.rabbitmq_client import RabbitMQClient
from derma_shared.redis_client import RedisClient
from app.models.document_stage import STAGE_BY_ID, get_blocking_deps
from app.repositories.document_repository import now_iso
from app.services.document_graph_service import DocumentGraphService
from app.services.document_service import DocumentService, read_profile
from app.services.document_stage_runner import DocumentStageRunner, StageRunState
from app.services.graph_schema_service import GraphSchemaService
from app.pipeline.document_ingest.stages import StageCancelled, StageError

logger = logging.getLogger(__name__)


class DocumentIngestPipelineService:
    """Điều khiển pipeline tài liệu"""

    def __init__(
        self,
        documentService: DocumentService,
        *,
        docling: DoclingClient | None = None,
        embedding: EmbeddingClient | None = None,
        rabbitmq: RabbitMQClient | None = None,
        redis: RedisClient | None = None,
        graph: DocumentGraphService | None = None,
        graph_schema: GraphSchemaService | None = None,
    ) -> None:
        """`rabbitmq`/`redis` chỉ API knowledge cần (đẩy yêu cầu chạy + Dừng); ingest worker chỉ gọi `execute` nên để trống."""
        self.documentService, self._repo = documentService, documentService.repo
        self._rabbitmq, self._redis = rabbitmq, redis
        self._graph = graph
        self.runner = DocumentStageRunner(documentService, docling=docling, embedding=embedding, graph=graph, graph_schema=graph_schema)
        run = self.runner
        self._runners: dict[str, Callable[[StageRunState], dict[str, Any]]] = {
            "ingest": run.run_ingest, "toc": run.run_toc, "chunks": run.run_chunks,
            "index": lambda state: run.index_document_chunks(state.document_id, state.progress),
            "graph": run.run_graph, "graph_index": run.run_graph_index,
        }
        self._reappliers: dict[str, Callable[[StageRunState], dict[str, Any]]] = {"toc": run.reapply_toc, "graph": run.reapply_graph}

    # ---- chạy bước: _prepare (kiểm tra + ghi running) -> execute ----
    def _prepare(self, document_id: str, stage_id: str, options: dict[str, Any], force: bool) -> None:
        """Ném lỗi nếu chưa chạy được; không thì ghi `running` (xoá nhật ký cũ, đánh dấu stale các bước hạ nguồn)."""
        self._require_document(document_id)
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        status = self._repo.status(document_id)["stages"]
        running = next((sid for sid, s in status.items() if s.get("state") == "running"), None)
        if running:
            raise ConflictError(f"Đang xử lý bước “{STAGE_BY_ID[running]['title']}” — hãy chờ xong hoặc dừng trước.")
        block = [] if force else get_blocking_deps(stage_id, status)
        if block:
            raise PipelineError("Cần xác nhận các bước trước: " + ", ".join(STAGE_BY_ID[b]["title"] for b in block) + ".")
        read_profile(self._repo, document_id)
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(
            document_id, stage_id, state="running", started_at=now_iso(), finished_at=None, error=None, options=options,
            progress={"done": 0, "total": 0, "message": "bắt đầu"}, summary=None, approved_at=None,
        )

    def _require_document(self, document_id: str) -> None:
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)

    def execute(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        *,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Chạy bước đã `begin`, ghi kết quả `pending_review` / `failed` / `cancelled`."""
        try:
            run = self.runner.make_state(document_id, stage_id, options, llm, cancel)
            run.log(f"bắt đầu bước {stage_id} options={options}")
            summary = self._runners[stage_id](run)
        except StageCancelled:
            logger.info("[%s/%s] đã huỷ", document_id, stage_id)
            self._repo.update_stage(
                document_id, stage_id, state="cancelled", finished_at=now_iso()
            )
            raise
        except Exception as e:
            logger.exception("[%s/%s] bước thất bại", document_id, stage_id)
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
        run.log(f"xong: {summary}")
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
        options = options or {}
        self._prepare(document_id, stage_id, options, force)
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
            raise RuntimeError("start_stage cần RabbitMQ + Redis (chỉ API knowledge có)")
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

    async def cancel_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        if self._redis is None:
            raise RuntimeError("cancel_stage cần Redis (chỉ API knowledge có)")
        await asyncio.to_thread(self._require_document, document_id)
        status = await asyncio.to_thread(self._repo.status, document_id)
        if status["stages"].get(stage_id, {}).get("state") != "running":
            raise ConflictError("Bước này hiện không chạy.")
        # bước có thể còn nằm trong queue (Pub/Sub không replay) nên đặt thêm cờ key; worker kiểm tra cờ khi nhận message
        await self._redis.set_value(
            DOCUMENT_CANCEL_KEY.format(document_id=document_id, stage_id=stage_id), "1", ex_seconds=3600
        )
        await self._redis.publish(DOCUMENT_INGEST_CANCEL_CHANNEL, json.dumps({"document_id": document_id, "stage_id": stage_id}))
        return await asyncio.to_thread(self.documentService.get_document, document_id)

    def update_triples(self, document_id: str, body: TripleUpdate) -> DocumentOutput:
        """Lưu duyệt quan hệ rồi áp lại bước `graph` (bước quay về chờ duyệt, `graph_index` thành stale)."""
        if self._graph is None:
            raise PipelineError("Chưa cấu hình đồ thị tri thức.")
        self._graph.update_triples(document_id, body)
        return self.reapply(document_id, "graph")

    def update_toc(
        self, document_id: str, body: TocUpdate
    ) -> DocumentOutput:
        """Lưu chỉnh sửa mục lục rồi áp lại bước `toc` (bước quay về chờ duyệt, các bước sau thành stale)."""
        self.documentService.update_toc(document_id, body)
        return self.reapply(document_id, "toc")

    # ---- duyệt / áp override ----
    def approve(self, document_id: str, stage_id: str) -> DocumentOutput:
        self._require_document(document_id)
        st = self._repo.status(document_id)["stages"].get(stage_id)
        if st is None:
            raise NotFoundError(stage_id)
        if st.get("state") != "pending_review":
            raise PipelineError("Chỉ xác nhận được bước đang ở trạng thái chờ xác nhận.")
        self._repo.update_stage(document_id, stage_id, state="approved", approved_at=now_iso())
        return self.documentService.get_document(document_id)

    def reapply(self, document_id: str, stage_id: str) -> DocumentOutput:
        """Áp lại override của người duyệt (nhanh, không LLM). Dữ liệu bước đổi nên bước quay về chờ duyệt và các bước hạ nguồn thành stale."""
        self._require_document(document_id)
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        reapply_fn = self._reappliers.get(stage_id)
        if reapply_fn is None:
            raise PipelineError(f"bước {stage_id} không có override")
        st = self._repo.status(document_id)["stages"][stage_id]
        if st.get("state") in {"not_started", "running"}:
            raise PipelineError(f"bước {stage_id} chưa có kết quả để áp override (hiện: {st.get('state')})")
        summary = reapply_fn(self.runner.make_state(document_id, stage_id, st.get("options") or {}))
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(document_id, stage_id, state="pending_review", summary=summary, approved_at=None)
        return self.documentService.get_document(document_id)
