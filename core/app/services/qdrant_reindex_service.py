import dataclasses
import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.models.file import File
from app.models.finalize_report import FinalizeReport, PatientImage
from app.models.patient_profile import PatientProfile
from app.repositories.document_repository import DocumentRepository
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService
from app.services.finalize_report_index_service import FinalizeReportIndexService
from pipeline.document_ingest.stages import index as index_stage

logger = logging.getLogger(__name__)

FinalizeBundle = tuple[FinalizeReport, PatientProfile | None, list[tuple[Any, Any]]]

_INDEXED_STATES = ("pending_review", "approved")
_COLLECTION_HINT = " — đặt QDRANT_DOCUMENT_COLLECTION sang tên mới rồi chạy lại (collection cũ không tự xoá)."


@dataclass
class ReindexReport:
    ok: list[str] = field(default_factory=lambda: list[str]())
    skipped: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    failed: dict[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass
class PruneReport:
    removed: dict[str, int] = field(default_factory=lambda: dict[str, int]())  # id mồ côi -> số điểm đã (hoặc sẽ) xoá
    failed: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    refused: str = ""  # lý do từ chối xoá (chốt an toàn)


def load_finalize_report_ids(sessions: sessionmaker[Session]) -> list[str]:
    with sessions() as s:
        return list(s.scalars(select(FinalizeReport.id)))


def load_finalize_bundles(sessions: sessionmaker[Session]) -> Iterator[FinalizeBundle]:
    with sessions() as s:
        for report in s.scalars(select(FinalizeReport)):
            profile = s.get(PatientProfile, report.patient_profile_id)
            images = list(
                s.execute(
                    select(PatientImage, File).join(File, File.id == PatientImage.file_id).where(PatientImage.finalize_report_id == report.id)
                ).tuples()
            )
            yield report, profile, images


class QdrantReindexService:
    def __init__(
        self,
        pipeline: DocumentIngestPipelineService,
        documents: DocumentRepository,
        report_index: FinalizeReportIndexService,
        qdrant: QdrantVectorClient,
        log: Callable[[str], None] = print,
    ) -> None:
        self._pipeline, self._documents, self._report_index, self._qdrant, self._log = pipeline, documents, report_index, qdrant, log

    def reindex_documents(self, document_ids: list[str] | None = None, *, dry_run: bool = False) -> ReindexReport:
        """Chạy lại đúng logic bước `index` nhưng không qua `begin/execute`, nên trạng thái stage của tài liệu giữ nguyên."""
        report = ReindexReport()
        for document_id in document_ids or self._documents.list_ids():
            try:
                self._reindex_document(document_id, dry_run, report)
            except Exception as exc:  # noqa: BLE001  # một tài liệu lỗi không chặn các tài liệu còn lại
                logger.error("[reindex] tài liệu %s lỗi: %s", document_id, exc, exc_info=True)
                hint = _COLLECTION_HINT if str(exc).startswith("Collection ") else ""
                report.failed[document_id] = f"{type(exc).__name__}: {exc}{hint}"
                self._log(f"LỖI {document_id}: {report.failed[document_id]}")
        return report

    def _reindex_document(self, document_id: str, dry_run: bool, report: ReindexReport) -> None:
        if not self._documents.exists(document_id):
            raise LookupError("tài liệu không tồn tại")
        state = self._documents.status(document_id)["stages"]["index"]["state"]
        if state not in _INDEXED_STATES:
            report.skipped[document_id] = f"bước index ở trạng thái {state}"
            self._log(f"bỏ qua {document_id}: {report.skipped[document_id]}")
            return
        chunks = self._documents.files_for(document_id).read_jsonl("chunks.jsonl")
        if not chunks:
            report.skipped[document_id] = "không có chunks.jsonl"
            self._log(f"bỏ qua {document_id}: {report.skipped[document_id]}")
            return
        if dry_run:
            report.ok.append(document_id)
            self._log(f"[dry-run] {document_id}: sẽ nạp lại {len(chunks)} đoạn")
            return
        ctx = self._pipeline.make_ctx(document_id, "index", {})
        # không ghi tiến độ/nhật ký vào DB: sẽ đè trạng thái "xong" mà admin đã duyệt
        ctx = dataclasses.replace(ctx, _update_stage=lambda *a, **k: {}, _append_log=lambda stage, message: None)
        summary = index_stage.run(ctx)
        report.ok.append(document_id)
        self._log(f"đã nạp {document_id}: {summary['points']} đoạn → {summary['collection']}")

    def reindex_finalize_reports(self, bundles: Iterable[FinalizeBundle], *, dry_run: bool = False) -> ReindexReport:
        report = ReindexReport()
        for fr, profile, images in bundles:
            try:
                if dry_run:
                    self._log(f"[dry-run] ca {fr.id}: sẽ nạp lại")
                else:
                    self._report_index.index_report_sync(fr, profile, images)
                    self._log(f"đã nạp ca {fr.id}")
                report.ok.append(fr.id)
            except Exception as exc:  # noqa: BLE001  # một ca lỗi không chặn các ca còn lại
                logger.error("[reindex] ca bệnh %s lỗi: %s", fr.id, exc, exc_info=True)
                report.failed[fr.id] = f"{type(exc).__name__}: {exc}"
                self._log(f"LỖI ca {fr.id}: {report.failed[fr.id]}")
        collection = self._report_index.collection
        self._log(f"collection {collection}: {self._qdrant.count_sync(collection)} điểm, {len(report.ok) + len(report.failed)} ca trong DB")
        return report

    def prune_documents(self, *, dry_run: bool = False) -> PruneReport:
        # đúng collection mà bước `index` ghi vào, không suy ra lại từ settings
        collection = self._pipeline.documentService.collection
        return self._prune(collection, "document_id", set(self._documents.list_ids()), "tài liệu", dry_run)

    def prune_finalize_reports(self, case_ids: Iterable[str], *, dry_run: bool = False) -> PruneReport:
        return self._prune(self._report_index.collection, "case_id", set(case_ids), "ca bệnh", dry_run)

    def _prune(self, collection: str, key: str, known: set[str], label: str, dry_run: bool) -> PruneReport:
        """Xoá điểm có `key` không còn trong DB; điểm không có field `key` không bị đụng tới."""
        report = PruneReport()
        in_qdrant = self._qdrant.distinct_payload_values_sync(collection, key)
        if in_qdrant and not known:
            # DB trống mà Qdrant có dữ liệu thường là trỏ nhầm môi trường; xoá lúc này sẽ mất sạch kho
            report.refused = f"DB không có {label} nào nhưng {collection} có {len(in_qdrant)} {key} — nghi trỏ nhầm DB, không xoá gì."
            logger.error("[prune] %s", report.refused)
            self._log(f"TỪ CHỐI: {report.refused}")
            return report
        for orphan in sorted(in_qdrant - known):
            try:
                points = self._qdrant.count_sync(collection, eq_filter(key, orphan))
                if not dry_run:
                    self._qdrant.delete_by_filter_sync(collection, eq_filter(key, orphan))
                report.removed[orphan] = points
                self._log(f"{'[dry-run] sẽ xoá' if dry_run else 'đã xoá'} {points} điểm của {key}={orphan}")
            except Exception as exc:  # noqa: BLE001  # một id lỗi không chặn các id còn lại
                logger.error("[prune] xoá %s=%s lỗi: %s", key, orphan, exc, exc_info=True)
                report.failed[orphan] = f"{type(exc).__name__}: {exc}"
                self._log(f"LỖI xoá {key}={orphan}: {report.failed[orphan]}")
        return report
