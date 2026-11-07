import logging
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.models.document_profile import ExtractionConfig

from ..types import DoclingBlock, FigureDraft, PageRow
from ..textutil import BODY_LABELS, noise_score, parse_page_ranges, pdftotext_pages, upper_ratio
from . import StageError

logger = logging.getLogger(__name__)

# convert(đầu, cuối) -> các khối Docling của khoảng trang; checkpoint/lưu ảnh do service lo
Convert = Callable[[int, int], list[DoclingBlock]]
OnProgress = Callable[[int, int, str], None]
OnLog = Callable[[str], None]


def _noop_progress(done: int, total: int, message: str = "") -> None:
    return None


def get_head_key(line: str) -> str:
    return re.sub(r"[^A-Z]", "", line.upper())[:14]


def _page_range(spec: object, total: int) -> tuple[int, int]:
    """Option `pages` ("1-300", "40") -> (đầu, cuối) trong [1, total]."""
    if not spec:
        return 1, total
    a, _, b = str(spec).strip().partition("-")
    try:
        lo, hi = int(a), int(b or a)
    except ValueError as e:
        raise StageError(f"Option pages không hợp lệ: {spec!r} (vd '1-300')") from e
    lo, hi = max(1, lo), min(total, hi)
    if lo > hi:
        raise StageError(f"Khoảng trang {spec!r} nằm ngoài sách ({total} trang)")
    return lo, hi


def build_page_row(n: int, header: str, printed: int | None, text: str, noise_set: set[int], offset: int) -> PageRow:
    reason = "profile" if n in noise_set else ("index" if get_head_key(header) == "INDEX" else None)
    return PageRow(page=n, page_printed=printed if printed is not None else n + offset, header=header, text=text,
                   noise=reason is not None, noise_reason=reason, noise_score=noise_score(text))


def find_first_text_line(lines: list[str]) -> int | None:
    return next((i for i, ln in enumerate(lines) if ln.strip()), None)


def build_summary(engine: str, rows: list[PageRow], first: int, last: int) -> dict:
    """Summary đi thẳng ra API/FE (snake_case)."""
    return {
        "engine": engine, "pages": len(rows), "page_range": [first, last],
        "pages_skipped": sum(1 for r in rows if r.noise),
        "pages_empty": sum(1 for r in rows if not r.text.strip()),
        "pages_high_noise": sum(1 for r in rows if r.noise_score > 0.05),
    }


# ---------------------------------------------------------------- docling
def build_docling_rows(by_page: dict[int, list[DoclingBlock]], first: int, last: int, total: int, ext: ExtractionConfig) -> list[PageRow]:
    noise_set = parse_page_ranges(ext.noise_pages, total)
    rows = []
    for n in range(first, last + 1):
        blocks = by_page.get(n, [])
        header = " ".join(b.text for b in blocks if b.label == "page_header")
        printed = next((int(b.text) for b in blocks if b.label == "page_footer" and b.text.strip().isdigit()), None)
        # bảng/mục lục là Markdown nhiều dòng: gộp một dòng để chỉ số dòng ổn định
        lines = [("• " if b.label == "list" else "") + " ".join(b.text.split()) for b in blocks if b.label in BODY_LABELS]
        rows.append(build_page_row(n, header, printed, "\n".join(lines), noise_set, ext.page_offset))
    return rows


def get_figures_from_blocks(document_id: str, by_page: dict[int, list[DoclingBlock]], first: int, last: int) -> list[FigureDraft]:
    """Hình theo thứ tự trang; `image_key` tương đối, service đổi thành `image_file` khớp `DocumentFigure`."""
    out: list[FigureDraft] = []
    for n in range(first, last + 1):
        for blk in by_page.get(n, []):
            if blk.label != "figure" or blk.image_key is None:
                continue
            seq = len(out) + 1
            out.append(FigureDraft(figure_id=f"{document_id}:f{seq:05d}", document_id=document_id, page=n, seq=seq,
                                   bbox=blk.bbox, caption=blk.text, image_key=blk.image_key))
    return out


def _extract_docling(pdf: Path, ext: ExtractionConfig, document_id: str, pages_opt: object, convert: Convert,
                     on_progress: OnProgress, on_log: OnLog) -> tuple[list[PageRow], list[FigureDraft], dict]:
    from pypdf import PdfReader

    total = len(PdfReader(str(pdf)).pages)
    first, last = _page_range(pages_opt, total)
    step = ext.docling_chunk_pages
    spans = [(a, min(a + step - 1, last)) for a in range(first, last + 1, step)]
    by_page: dict[int, list[DoclingBlock]] = {}
    for i, (a, b) in enumerate(spans, 1):
        on_progress(i - 1, len(spans), f"Nhận dạng chữ: trang {a}-{b}")
        blocks = convert(a, b)
        on_log(f"trang {a}-{b}: {len(blocks)} khối")
        for blk in blocks:
            if first <= blk.page <= last:
                by_page.setdefault(blk.page, []).append(blk)
    on_progress(len(spans), len(spans), "dựng pages.jsonl")
    rows = build_docling_rows(by_page, first, last, total, ext)
    figures = get_figures_from_blocks(document_id, by_page, first, last)
    summary = build_summary("docling", rows, first, last)
    summary["figures"] = len(figures)
    return rows, figures, summary


# ---------------------------------------------------------------- pdftotext
def find_running_header_keys(lines_by_page: list[list[str]], on_log: OnLog) -> set[str]:
    cnt: Counter[str] = Counter()
    for lines in lines_by_page:
        i = find_first_text_line(lines)
        if i is not None and 4 <= len(lines[i].strip()) <= 110 and upper_ratio(lines[i].strip()) >= 0.6:
            cnt[get_head_key(lines[i].strip())] += 1
    threshold = max(5, int(0.015 * len(lines_by_page)))
    keys = {k for k, n in cnt.items() if n >= threshold and k}
    on_log(f"{len(keys)} kiểu running header (ngưỡng ≥ {threshold} trang)")
    return keys


def build_pdftotext_rows(lines_by_page: list[list[str]], header_keys: set[str], ext: ExtractionConfig,
                    on_progress: OnProgress) -> list[PageRow]:
    total = len(lines_by_page)
    noise_set = parse_page_ranges(ext.noise_pages, total)
    rows = []
    for n, lines in enumerate(lines_by_page, 1):
        on_progress(n, total, "đọc trang")
        header = ""
        i = find_first_text_line(lines)
        if i is not None and header_keys and get_head_key(lines[i].strip()) in header_keys:
            header, lines = lines[i].strip(), lines[i + 1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        printed: int | None = None
        if lines and re.fullmatch(r"\s*\d{1,4}\s*", lines[-1]):  # số trang in ở cuối trang
            printed, lines = int(lines[-1].strip()), lines[:-1]
        while lines and not lines[0].strip():
            lines = lines[1:]
        rows.append(build_page_row(n, header, printed, "\n".join(lines).rstrip(), noise_set, ext.page_offset))
    return rows


def _extract_pdftotext(pdf: Path, ext: ExtractionConfig, on_progress: OnProgress, on_log: OnLog) -> tuple[list[PageRow], dict]:
    try:
        raw_pages = pdftotext_pages(pdf, ext.layout)
    except RuntimeError as e:
        logger.warning("pdftotext thất bại với %s: %s", pdf, e)
        raise StageError(str(e)) from e
    if not raw_pages:
        raise StageError("PDF không có văn bản — với sách scan, hãy chọn “nhận dạng chữ từ ảnh” trong Cài đặt.")
    lines_by_page = [p.split("\n") for p in raw_pages]
    header_keys = find_running_header_keys(lines_by_page, on_log) if ext.strip_running_headers else set()
    rows = build_pdftotext_rows(lines_by_page, header_keys, ext, on_progress)
    return rows, build_summary("pdftotext", rows, 1, len(rows))


def extract_pages(pdf: Path, ext: ExtractionConfig, *, document_id: str = "", pages_opt: object = None,
                  convert: Convert | None = None, on_progress: OnProgress = _noop_progress,
                  on_log: OnLog = lambda _msg: None) -> tuple[list[PageRow], list[FigureDraft], dict]:
    """PDF -> (các dòng `pages.jsonl`, danh sách hình, summary); `convert` bắt buộc khi engine là docling."""
    if ext.engine != "docling":
        rows, summary = _extract_pdftotext(pdf, ext, on_progress, on_log)
        return rows, [], summary
    if convert is None:
        raise StageError("Chưa cấu hình công cụ nhận dạng chữ (Docling).")
    return _extract_docling(pdf, ext, document_id, pages_opt, convert, on_progress, on_log)
