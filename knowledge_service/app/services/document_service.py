"""Nghiệp vụ tài liệu"""
import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic import ValidationError

from app.dto.base.document import NewDocument
from app.dto.api import (
    ChunkListOutput,
    ChunkOutput,
    DocumentOutput,
    DocumentSettings,
    DocumentSummary,
    FigureListOutput,
    FigureOutput,
    FileDto,
    SourcePageOutput,
    StageOutput,
    TocOutput,
    TocUpdate,
)
from derma_shared.errors import ConflictError, InvalidError, NotFoundError
from app.models.document_profile import Profile
from app.models.document_stage import STAGES, get_blocking_deps
from app.repositories.document_repository import DocumentRepository
from app.services.document_chunk_index import DocumentChunkIndex
from app.services.document_graph_service import DocumentGraphService
from app.pipeline.document_ingest.profile import ProfileError, default_profile
from app.pipeline.document_ingest.textutil import sha

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 500 * 1024 * 1024
PAGE_IMAGE_DPI = 80
PAGE_IMAGE_KEY = "page_img/p{page}.png"


def _paginate(
    rows: list[dict[str, Any]], page: int, page_size: int
) -> list[dict[str, Any]]:
    start = (max(page, 1) - 1) * page_size
    return rows[start : start + page_size]


def read_profile(repo: DocumentRepository, document_id: str) -> Profile:
    """Đọc cài đặt của tài liệu (`documents.profile`); thiếu hoặc sai thì báo lỗi hiển thị cho người dùng."""
    try:
        profile = repo.get_profile(document_id)
    except ValidationError as exc:
        raise InvalidError(f"Cài đặt của tài liệu bị lỗi: {exc}") from exc
    if profile is None:
        raise InvalidError("Cài đặt của tài liệu bị lỗi: tài liệu chưa có cài đặt")
    return profile


def get_temp_root() -> Path:
    """Thư mục tạm cho `get_local_pdf()` (bản sao PDF để pdftotext/Docling/pdftoppm đọc, dùng xuyên suốt 1 lần chạy bước)."""
    p = Path(tempfile.gettempdir()) / "document_ingest_tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_local_pdf(repo: DocumentRepository, document_id: str) -> Path:
    """Bản sao tạm của `source.pdf` trên đĩa, dùng lại khi cùng kích thước"""
    try:
        return repo.files_for(document_id).local_copy("source.pdf", get_temp_root() / document_id / "source.pdf")
    except FileNotFoundError as exc:
        raise FileNotFoundError("Không tìm thấy file PDF của tài liệu.") from exc


class DocumentService:
    def __init__(self, repository: DocumentRepository, chunks: DocumentChunkIndex,
                 graph: DocumentGraphService | None = None) -> None:
        self.repo, self.chunks, self.graph = repository, chunks, graph
        repository.files.ensure_bucket()

    # ---- tài liệu ----
    def ensure_idle(self, document_id: str, action: str) -> None:
        if self.repo.get_running_stage(document_id) is not None:
            raise ConflictError(f"Tài liệu đang được xử lý — hãy chờ xong hoặc dừng trước khi {action}.")

    def fail_orphaned_runs(self) -> int:
        """Bước ghi `running` nhưng không còn tiến trình nào chạy nó -> failed"""
        return self.repo.fail_running_stages("Tiến trình xử lý đã dừng bất thường (xem nhật ký).")

    @staticmethod
    def _stage_outputs(detail: dict[str, Any]) -> list[StageOutput]:
        """Trạng thái từng bước xử lý của tài liệu (dữ liệu DB ghép với hằng `STAGES`) cho API admin."""
        status = detail["stages"]
        out = []
        for s in STAGES:
            st = status[s["id"]]
            prog = st.get("progress")
            out.append(
                StageOutput(
                    stage_id=s["id"],
                    title=s["title"],
                    deps=s["deps"],
                    uses_llm=s["llm"],
                    state=st.get("state", "not_started"),
                    started_at=st.get("started_at"),
                    finished_at=st.get("finished_at"),
                    approved_at=st.get("approved_at"),
                    progress=prog if isinstance(prog, dict) else None,
                    summary=st.get("summary") or None,
                    error=st.get("error"),
                    options=st.get("options") or {},
                    blocked_by=get_blocking_deps(s["id"], status),
                )
            )
        return out

    def list_documents(self) -> list[DocumentSummary]:
        out = []
        for did in self.repo.list_ids():
            detail = self.repo.get_detail(did)
            out.append(
                DocumentSummary(
                    id=did,
                    title=detail.get("title", did),
                    created_at=detail.get("created_at"),
                    # chỉ đọc số trang đã cache, không tải PDF về để đếm
                    pdf_pages=detail.get("pdf_pages") or None,
                    file_size=(detail.get("source_file") or {}).get("size"),
                    states={k: v.get("state", "not_started") for k, v in detail["stages"].items()},
                )
            )
        return out

    def pdf_pages(self, document_id: str) -> int | None:
        cached = self.repo.get_pdf_pages(document_id)
        if cached:
            return int(cached)
        try:
            n = self._count_pages(get_local_pdf(self.repo, document_id))
        except FileNotFoundError:
            return None
        if n is None:
            return None
        self.repo.update_meta(document_id, pdf_pages=n)
        return n

    def get_document(self, document_id: str) -> DocumentOutput:
        detail = self.repo.get_detail(document_id)
        if not detail:
            raise NotFoundError(document_id)
        source = detail.get("source_file")
        stages = self._stage_outputs(detail)
        return DocumentOutput(
            id=document_id,
            title=detail.get("title", document_id),
            created_at=detail.get("created_at"),
            source_file=FileDto.model_validate(source) if source else None,
            pdf_pages=self.pdf_pages(document_id) if source else None,
            stages=stages,
            running_stage=next((s.stage_id for s in stages if s.state == "running"), None),
        )

    async def create_document(
        self,
        upload: UploadFile,
        title: str,
        engine: str | None,
    ) -> DocumentOutput:
        try:
            draft = NewDocument.model_validate({"title": title, "engine": engine or "pdftotext"})
        except ValidationError as exc:
            raise InvalidError(exc.errors()[0]["msg"].removeprefix("Value error, ")) from exc
        head = await upload.read(4)
        if head != _PDF_MAGIC:
            raise InvalidError("File tải lên không phải là PDF.")
        tmp_dir = Path(tempfile.mkdtemp(prefix="toc_upload_"))
        try:
            tmp = tmp_dir / "source.pdf"
            await self._save_upload(upload, head, tmp)  # chỉ kiểm tra giới hạn; kích thước ghi vào `files` khi tạo
            pages = await asyncio.to_thread(self._count_pages, tmp)
            did = await asyncio.to_thread(
                self.repo.create,
                draft.title,
                {"pdf_pages": pages},
                default_profile("", draft.engine),
                {"source.pdf": tmp},
                None,
                upload.filename or "",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return self.get_document(did)

    @staticmethod
    async def _save_upload(upload: UploadFile, head: bytes, dest: Path) -> int:
        """Ghi upload ra `dest` (đã đọc sẵn `head`), trả về số byte; quá giới hạn thì báo lỗi."""
        size = len(head)
        with dest.open("wb") as f:
            f.write(head)
            while chunk := await upload.read(1 << 20):
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise InvalidError(f"File PDF quá lớn (tối đa {MAX_PDF_BYTES >> 20} MB).")
                await asyncio.to_thread(f.write, chunk)
        return size

    @staticmethod
    def _count_pages(path: Path) -> int | None:
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(path)).pages)
        except Exception:
            logger.warning("Không đếm được số trang của %s", path, exc_info=True)
            return None

    def delete_document(self, document_id: str) -> None:
        self.ensure_idle(document_id, "xóa")
        self._delete(document_id)

    def page_image(self, document_id: str, page: int) -> bytes:
        """PNG của một trang PDF để đối chiếu mục lục/định vị bằng mắt. Vẽ lần đầu rồi lưu vào MinIO (`page_img/`)."""
        files = self.repo.files_for(document_id)
        total = self.pdf_pages(document_id)
        if (
            not files.exists("source.pdf")
            or total is None
            or not 1 <= page <= total
        ):
            raise NotFoundError(f"page {page}")
        name = PAGE_IMAGE_KEY.format(page=page)
        cached = files.get_bytes(name)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="toc_page_") as tmp_dir:
            out = Path(tmp_dir) / "page"
            try:
                subprocess.run(
                    ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(PAGE_IMAGE_DPI), "-png", "-singlefile",
                     str(get_local_pdf(self.repo, document_id)), str(out)],
                    check=True, capture_output=True, timeout=120,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise InvalidError(f"Không hiển thị được hình ảnh trang {page}: {exc}") from exc
            data = out.with_suffix(".png").read_bytes()
        files.put_bytes(name, data)
        return data

    def get_toc(self, document_id: str) -> TocOutput:
        doc = self.repo.files_for(document_id).read_json("toc.json")
        if doc is None:
            raise NotFoundError("toc.json")
        # `toc.json` giữ khoá lưu trữ cũ; đổi sang tên wire ở đây thay vì sửa dữ liệu đã có
        entries = [
            {**{k: v for k, v in e.items() if k not in ("printed_page", "pdf_page")},
             "page_printed": e.get("printed_page"), "page": e.get("pdf_page")}
            for e in doc.get("entries", [])
        ]
        return TocOutput.model_validate({**doc, "entries": entries})

    def update_toc(self, document_id: str, body: TocUpdate) -> None:
        """Lưu chỉnh sửa mục lục của người duyệt vào override (bảng `document_overrides`, stage `toc`). Caller áp lại bước `toc` sau đó."""
        files = self.repo.files_for(document_id)
        if not body.model_dump(exclude_defaults=True):
            raise InvalidError("Không có thay đổi nào để lưu.")
        auto = files.read_json("toc.auto.json")
        if auto is None:
            raise ConflictError("Hãy làm bước Mục lục trước.")
        ids = {e["id"] for e in auto["entries"]}
        ov = self.repo.overrides.get(document_id, "toc")
        added = list(ov.get("_added") or [])
        ids |= {a["id"] for a in added}
        for it in body.items:
            if it.id not in ids:
                raise NotFoundError(it.id)
            cur = dict(ov.get(it.id) or {})
            if it.title is not None:
                if not it.title.strip():
                    raise InvalidError("Tên mục không được để trống.")
                cur["title"] = it.title.strip()
            if it.level is not None:
                cur["level"] = it.level
            if it.page_printed is not None:
                cur["printed_page"] = it.page_printed
            if it.clear_page:
                cur["printed_page"] = None
            ov[it.id] = cur
            for a in added:  # mục thêm tay sửa thẳng vào bản ghi của nó
                if a["id"] == it.id:
                    a.update(
                        {
                            k: v
                            for k, v in cur.items()
                            if k in {"title", "level", "printed_page"}
                        }
                    )
        for d in body.deleted:
            if d not in ids:
                raise NotFoundError(d)
        added_ids = {a["id"] for a in added}
        ov["_deleted"] = sorted(set(ov.get("_deleted") or []) | {d for d in body.deleted if d not in added_ids})
        added = [a for a in added if a["id"] not in body.deleted]  # mục thêm tay bị xoá thì bỏ hẳn
        for a in body.added:
            if a.after_id is not None and a.after_id not in ids:
                raise NotFoundError(a.after_id)
            added.append({
                "id": "x" + sha(a.title, str(len(added)), json.dumps(sorted(ids)))[:6],
                "title": a.title.strip(), "level": a.level, "printed_page": a.page_printed, "after": a.after_id,
            })
        ov["_added"] = added
        if body.offset is not None:
            ov["_offset"] = body.offset
        self.repo.overrides.write(document_id, "toc", ov)

    def list_figures(
        self, document_id: str, q: str, page: int, page_size: int
    ) -> FigureListOutput:
        rows = self.repo.files_for(document_id).read_json("figures.json", []) or []
        ql = q.strip().lower()
        picked = [
            f
            for f in rows
            if not ql or ql in (f.get("caption") or "").lower() or ql == str(f["page"])
        ]
        return FigureListOutput(
            items=[
                FigureOutput.model_validate(f)
                for f in _paginate(picked, page, page_size)
            ],
            total=len(picked),
            page=page,
            page_size=page_size,
        )

    def figure_image(self, document_id: str, figure_id: str) -> bytes:
        files = self.repo.files_for(document_id)
        fig = next((f for f in files.read_json("figures.json", []) or [] if f["figure_id"] == figure_id), None)
        data = files.get_bytes(f"figures/{fig['image_file']['file_name']}") if fig else None
        if data is None:
            raise NotFoundError(figure_id)
        return data

    def list_chunks(
        self,
        document_id: str,
        q: str,
        node: str,
        only_review: bool,
        page: int,
        page_size: int,
    ) -> ChunkListOutput:
        files = self.repo.files_for(document_id)
        rows = files.read_jsonl("chunks.jsonl")
        review = {
            r["id"]: r["reason"]
            for r in files.read_json("review/chunks.json", []) or []
        }
        entries = (files.read_json("toc.json") or {}).get("entries", [])
        by_id = {e["id"]: e for e in entries}
        prefix: list[str] | None = None
        if node:
            if node not in by_id:
                raise NotFoundError(node)
            prefix = by_id[node]["path"]
        ql = q.strip().lower()
        picked = [
            c
            for c in rows
            if (prefix is None or c["toc_path"][: len(prefix)] == prefix)
            and (
                not ql
                or ql in c["text"].lower()
                or any(ql in h.lower() for h in c["toc_path"])
            )
            and (not only_review or c["chunk_id"] in review)
        ]
        by_path: dict[tuple[str, ...], int] = {}
        for (
            c
        ) in rows:  # số chunk dưới mỗi mục (kể cả mục con) cho cây điều hướng
            for k in range(1, len(c["toc_path"]) + 1):
                key = tuple(c["toc_path"][:k])
                by_path[key] = by_path.get(key, 0) + 1
        per_node = {
            e["id"]: by_path.get(tuple(e["path"]), 0)
            for e in entries
            if by_path.get(tuple(e["path"]))
        }
        items = [
            ChunkOutput.model_validate({**c, "review_reason": review.get(c["chunk_id"])})
            for c in _paginate(picked, page, page_size)
        ]
        return ChunkListOutput(
            items=items,
            total=len(picked),
            page=page,
            page_size=page_size,
            counts={
                "all": len(rows),
                "review": len(review),
                "tokens": sum(c["tokens"] for c in rows),
                "per_node": per_node,
            },
        )

    def _delete(self, document_id: str) -> None:
        """Xoá tài liệu: mọi đối tượng trong MinIO + các đoạn đã lưu trong Qdrant + cạnh đã nạp vào Neo4j."""
        self.chunks.delete_chunks(document_id)
        if self.graph is not None:
            self.graph.delete_document(document_id)
        self.repo.delete(document_id)
        shutil.rmtree(get_temp_root() / document_id, ignore_errors=True)

    # ---- cài đặt, nhật ký, trang nguồn, xuất chunk ----
    def get_settings(self, document_id: str) -> DocumentSettings:
        p = read_profile(self.repo, document_id)
        return DocumentSettings(title=self.repo.get_title(document_id), engine=p.extraction.engine)

    def update_settings(self, document_id: str, body: DocumentSettings) -> DocumentSettings:
        self.ensure_idle(document_id, "đổi cài đặt")
        p = read_profile(self.repo, document_id)
        p.extraction.engine = body.engine
        self.repo.update_meta(document_id, profile=p.model_dump(mode="json"), title=body.title.strip())
        return self.get_settings(document_id)

    def get_page(self, document_id: str, page: int) -> SourcePageOutput:
        for r in self.repo.files_for(document_id).iter_jsonl("pages.jsonl"):
            if r["page"] == page:
                return SourcePageOutput.model_validate(r)
        raise NotFoundError(f"page {page}")

    def export_chunks(self, document_id: str) -> bytes:
        data = self.repo.files_for(document_id).get_bytes("chunks.jsonl")
        if data is None:
            raise NotFoundError("chunks.jsonl")
        return data
