"""Nạp lại toàn bộ dữ liệu Qdrant (chunk sách + ca bệnh) từ nguồn chuẩn: MinIO (`chunks.jsonl`) và Postgres (`finalize_reports`)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # chạy được từ `core/` mà không cần cài package

from app.api.deps import (  # noqa: E402
    get_document_ingest_pipeline_service,
    get_document_repository,
    get_finalize_report_index_service,
    get_postgres_client,
    get_qdrant_client,
)
from app.services.qdrant_reindex_service import (  # noqa: E402
    PruneReport,
    QdrantReindexService,
    ReindexReport,
    load_finalize_bundles,
    load_finalize_report_ids,
)


def _summary(title: str, r: ReindexReport) -> None:
    print(f"== {title}: {len(r.ok)} ok, {len(r.skipped)} bỏ qua, {len(r.failed)} lỗi")


def _prune_summary(title: str, r: PruneReport, dry_run: bool) -> int:
    verb = "sẽ xoá" if dry_run else "đã xoá"
    print(f"== prune {title}: {verb} {sum(r.removed.values())} điểm của {len(r.removed)} id mồ côi, {len(r.failed)} lỗi" + (", TỪ CHỐI" if r.refused else ""))
    return len(r.failed) + (1 if r.refused else 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["documents", "finalize-reports"], help="chỉ nạp một nhóm (mặc định: cả hai)")
    ap.add_argument("--document", action="append", metavar="ID", help="chỉ nạp tài liệu này (lặp được); ngầm hiểu --only documents")
    ap.add_argument("--prune", action="store_true", help="xoá điểm mồ côi (id không còn trong DB); chạy sau khi nạp lại")
    ap.add_argument("--prune-only", action="store_true", help="chỉ xoá điểm mồ côi, không nạp lại (ngầm hiểu --prune)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ liệt kê việc sẽ làm, không gọi embedding / ghi Qdrant")
    args = ap.parse_args()
    args.prune = args.prune or args.prune_only
    if args.prune and args.document:
        ap.error("--prune cần danh sách đầy đủ, không dùng chung với --document")

    service = QdrantReindexService(
        get_document_ingest_pipeline_service(), get_document_repository(), get_finalize_report_index_service(), get_qdrant_client()
    )
    only = "documents" if args.document else args.only
    failed = 0
    if only in (None, "documents") and not args.prune_only:
        r = service.reindex_documents(args.document, dry_run=args.dry_run)
        _summary("tài liệu", r)
        failed += len(r.failed)
    if only in (None, "finalize-reports") and not args.prune_only:
        r = service.reindex_finalize_reports(load_finalize_bundles(get_postgres_client().sync_session_factory), dry_run=args.dry_run)
        _summary("ca bệnh", r)
        failed += len(r.failed)
    sessions = get_postgres_client().sync_session_factory
    if args.prune and only in (None, "documents"):
        failed += _prune_summary("tài liệu", service.prune_documents(dry_run=args.dry_run), args.dry_run)
    if args.prune and only in (None, "finalize-reports"):
        failed += _prune_summary(
            "ca bệnh", service.prune_finalize_reports(load_finalize_report_ids(sessions), dry_run=args.dry_run), args.dry_run
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
