from datetime import timedelta
from typing import Annotated, Any

from derma_shared.errors import NotFoundError
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_document_repository, require_doctor_or_admin
from app.dto.api import ApiResponse
from app.repositories.document_repository import DocumentRepository

# bác sĩ mở trích dẫn của gợi ý AI để đối chiếu tài liệu gốc; xem phần quản trị tài liệu vẫn chỉ admin
router = APIRouter(prefix="/citations", tags=["citations"], dependencies=[Depends(require_doctor_or_admin)])

Repo = Annotated[DocumentRepository, Depends(get_document_repository)]

SOURCE_URL_TTL = timedelta(minutes=30)
MAX_PASSAGES = 10


def _printed_pages(chunk: dict[str, Any]) -> str:
    start = chunk.get("page_printed_start") or chunk.get("page_start")
    end = chunk.get("page_printed_end") or chunk.get("page_end")
    if not start:
        return ""
    return f"tr.{start}" if not end or end == start else f"tr.{start}-{end}"


@router.get("/documents/{document_id}/source-url", operation_id="getCitationSourceUrl")
def get_source_url(document_id: str, repo: Repo, page: int = Query(default=1, ge=1)) -> ApiResponse[dict[str, Any]]:
    if not repo.exists(document_id):
        raise NotFoundError(f"tài liệu {document_id}")
    url = repo.files_for(document_id).presigned_get_url("source.pdf", SOURCE_URL_TTL)
    if url is None:
        raise NotFoundError(f"file gốc của tài liệu {document_id}")
    return ApiResponse(data={"url": url, "title": repo.get_title(document_id), "page": page})


@router.get("/documents/{document_id}/passages", operation_id="getCitationPassages")
def get_passages(
    document_id: str,
    repo: Repo,
    page_start: int = Query(ge=1),
    page_end: int | None = Query(default=None, ge=1),
    chunk_id: str | None = None,
) -> ApiResponse[dict[str, Any]]:
    if not repo.exists(document_id):
        raise NotFoundError(f"tài liệu {document_id}")
    end = max(page_end or page_start, page_start)
    chunks = repo.files_for(document_id).read_jsonl("chunks.jsonl")
    # chunks.jsonl có toàn văn (Qdrant chỉ giữ payload để tìm kiếm) nên đáng tin hơn để đọc lại đoạn trích
    hits = [c for c in chunks if c.get("page_start", 0) <= end and c.get("page_end", 0) >= page_start]
    hits.sort(key=lambda c: (c.get("chunk_id") != chunk_id, c.get("seq", 0)))  # đoạn được trích luôn nằm trong giới hạn
    shown = sorted(hits[:MAX_PASSAGES], key=lambda c: c.get("seq", 0))
    passages = [
        {
            "chunk_id": c.get("chunk_id"),
            "section": " > ".join(str(p) for p in c.get("toc_path") or [] if p),
            "pages": _printed_pages(c),
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "text": c.get("text", ""),
            "is_cited": c.get("chunk_id") == chunk_id,
        }
        for c in shown
    ]
    return ApiResponse(data={"title": repo.get_title(document_id), "passages": passages})
