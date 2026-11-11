import json
import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.infra.docling_client import DoclingClient
from app.infra.llm_client import LLMClient, LLMError
from app.models.document_profile import ExtractionConfig

from .. import mapping
from ..textutil import BODY_LABELS, parse_page_ranges, pdftotext_pages
from ..types import PageRow, TocAuto, TocDoc, TocEntry, TocMeta
from . import StageError

logger = logging.getLogger(__name__)

OnProgress = Callable[[int, int, str], None]
OnLog = Callable[[str], None]

DIGEST_HEAD_PAGES = 60
DIGEST_TAIL_PAGES = 15

FIND_PROMPT = """Bạn nhận bản tóm tắt các trang đầu và cuối của một cuốn sách (PDF; OCR có thể nhiễu, bảng ở dạng Markdown). Hãy tìm các trang là MỤC LỤC (danh sách tên phần/chương/mục kèm số trang), thường nằm liền nhau gần đầu sách (đôi khi sau lời nói đầu). Mỗi trang có: page (số trang PDF), chars (số ký tự), head (220 ký tự đầu).

Quy tắc:
- Trang đầu của mục lục thường có chữ CONTENTS / MỤC LỤC / TABLE OF CONTENTS; các trang sau chỉ là các hàng "tên | số trang".
- Không tính lời nói đầu, lời cảm ơn, danh sách hình/bảng, hay mục từ (index) cuối sách.
- Chỉ dùng thông tin được cung cấp; không chắc thì để trống.

Trả về DUY NHẤT JSON hợp lệ: {"toc_pages": [8, 9, 10], "reason": "≤ 15 từ"}"""

PARSE_PROMPT = """Bạn đọc các trang MỤC LỤC của một cuốn sách (OCR có thể nhiễu; bảng ở dạng Markdown "| tên | số trang |") và chuyển thành danh sách mục theo ĐÚNG thứ tự đọc.

Mỗi mục: {"level": 0-3, "title": "...", "printed_page": 123 hoặc null}
- level 0 = PART (phần lớn, vd "PART IV ..."), 1 = SECTION (nhóm/chương, vd "SECTION 2 ECZEMA/DERMATITIS"), 2 = mục/bệnh/chương con có số trang, 3 = mục con thụt vào dưới một mục level 2.
- Tên mục lấy nguyên văn, chỉ sửa lỗi OCR RÕ RÀNG (chữ bị thay ký tự, vd "Lupua Erythematolus" -> "Lupus Erythematosus"); không thêm, bỏ hay gộp mục. Dòng tiêu đề bị ngắt thành nhiều dòng thì gộp một mục.
- printed_page là số trang IN của sách (số Ả Rập). Số La Mã (xxiii) hoặc không có số thì null.
- Bỏ các dòng không phải mục: chữ CONTENTS/MỤC LỤC, tên sách, số trang đứng một mình, dòng kẻ bảng.
- "context" là part/section cuối của nhóm trang trước: dùng để biết mục đầu nhóm này thuộc đâu; KHÔNG lặp lại context thành mục.

Trả về DUY NHẤT JSON hợp lệ: {"entries": [{"level": 1, "title": "...", "printed_page": 61}]}"""


# ---------------------------------------------------------------- đọc chữ các trang
def count_pages(rows: list[PageRow], pdf: Callable[[], Path]) -> int:
    if rows:
        return max(r.page for r in rows)
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf())).pages)
    except StageError:
        raise
    except Exception as e:
        logger.warning("pypdf không đọc được PDF: %s", e)
        raise StageError(f"Không đọc được PDF: {e}") from e


def read_pdftotext_pages(pdf: Path, first: int, last: int) -> dict[int, str]:
    try:
        out = pdftotext_pages(pdf, True, first, last)
    except RuntimeError as e:
        logger.warning("pdftotext thất bại với %s: %s", pdf, e)
        raise StageError(str(e)) from e
    return {first + i: t for i, t in enumerate(out[: last - first + 1])}


def build_digests(rows: list[PageRow], total: int, pdf: Callable[[], Path]) -> list[dict[str, Any]]:
    wanted = sorted(set(range(1, min(total, DIGEST_HEAD_PAGES) + 1)) | set(range(max(1, total - DIGEST_TAIL_PAGES + 1), total + 1)))
    texts = {r.page: r.text for r in rows}
    if not texts:
        texts = read_pdftotext_pages(pdf(), 1, total)  # chưa ingest: lớp text ẩn của PDF (có thể kém) đủ để nhận ra trang mục lục
    return [{"page": n, "chars": len(texts.get(n, "")), "head": " ".join(texts.get(n, "").split())[:220]} for n in wanted]


def get_page_texts(pages: list[int], rows: list[PageRow], ext: ExtractionConfig, pdf: Callable[[], Path],
               docling: DoclingClient | None, on_progress: OnProgress) -> dict[int, str]:
    """Chữ các trang mục lục: lấy từ `pages.jsonl` nếu có, không thì đọc thẳng từ PDF."""
    have = {r.page: r.text for r in rows}
    if all(p in have for p in pages):
        return {p: have[p] for p in pages}
    if ext.engine == "docling":
        if docling is None:
            raise StageError("Chưa cấu hình công cụ nhận dạng chữ (Docling).")
        out: dict[int, str] = {}
        runs: list[list[int]] = []
        for p in sorted(pages):
            if runs and p == runs[-1][-1] + 1:
                runs[-1].append(p)
            else:
                runs.append([p])
        for run in runs:
            on_progress(0, 1, f"Docling OCR trang mục lục {run[0]}-{run[-1]}")
            blocks = docling.convert_pages(pdf(), run[0], run[-1], ocr=True, force_ocr=ext.docling_force_ocr, tables=True)
            for b in blocks:
                if b["label"] in BODY_LABELS:
                    out[b["page"]] = (out.get(b["page"], "") + "\n" + " ".join(b["text"].split())).strip("\n")
        return {p: out.get(p, "") for p in pages}
    got = read_pdftotext_pages(pdf(), min(pages), max(pages))
    return {p: got.get(p, "") for p in pages}


# ---------------------------------------------------------------- LLM
def find_toc_pages(llm: LLMClient, digests: list[dict[str, Any]]) -> tuple[list[int], str]:
    try:
        data = llm.complete_json(FIND_PROMPT, "Các trang (JSON):\n" + json.dumps(digests, ensure_ascii=False), name="toc_find")
    except LLMError as e:
        logger.warning("LLM không xác định được trang mục lục: %s", e)
        raise StageError(f"AI không xác định được trang mục lục: {e}") from e
    raw = data.get("toc_pages") if isinstance(data, dict) else None
    pages = sorted({int(p) for p in raw if str(p).isdigit()}) if isinstance(raw, list) else []
    if not pages:
        raise StageError("AI không tìm thấy trang mục lục — hãy nhập số trang mục lục (vd 8-22) rồi thử lại.")
    return pages, str((data or {}).get("reason") or "")[:160]


def _clean_entry(it: Any) -> TocEntry | None:
    if not isinstance(it, dict):
        return None
    title = " ".join(str(it.get("title") or "").split()).strip(" |-.")
    if len(title) < 2:
        return None
    try:
        level = max(0, min(int(it.get("level", 2)), 3))
    except (TypeError, ValueError):
        level = 2
    page = it.get("printed_page")
    page = int(page) if isinstance(page, (int, float)) or (isinstance(page, str) and page.strip().isdigit()) else None
    return TocEntry(id="", level=level, kind=mapping.KINDS[level], title=title, printed_page=page)  # id gán sau khi gom đủ mục


def parse_entries(llm: LLMClient, texts: dict[int, str], on_progress: OnProgress,
                  on_log: OnLog) -> tuple[list[TocEntry], list[str]]:
    """LLM đọc các trang mục lục theo nhóm, tuần tự (nhóm sau cần part/section cuối của nhóm trước)."""
    warnings: list[str] = []
    groups: list[list[int]] = []
    size = 0
    for p in sorted(texts):
        n = len(texts[p])
        if groups and (len(groups[-1]) >= 3 or size + n > 9000):
            groups.append([])
            size = 0
        if not groups:
            groups.append([])
        groups[-1].append(p)
        size += n
    entries: list[TocEntry] = []
    context: dict[str, str] = {}

    def ask(pages: list[int]) -> list[TocEntry]:
        payload = {"context": context, "pages": [{"page": p, "text": texts[p][:7000]} for p in pages]}
        try:
            data = llm.complete_json(PARSE_PROMPT, "Dữ liệu (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="toc_parse")
        except LLMError as e:
            if len(pages) == 1:
                logger.warning("LLM không đọc được trang mục lục %s: %s", pages[0], e)
                warnings.append(f"AI không đọc được trang mục lục {pages[0]}: {str(e)[:100]}")
                return []
            on_log(f"nhóm trang {pages} lỗi -> đọc từng trang")
            return [x for p in pages for x in ask([p])]
        items = data.get("entries") if isinstance(data, dict) else data
        out = []
        for it in items or []:
            e = _clean_entry(it)
            if e is not None:
                e.toc_page = pages[0] if len(pages) == 1 else None
                out.append(e)
        return out

    for i, g in enumerate(groups, 1):
        on_progress(i - 1, len(groups), f"LLM đọc mục lục: trang {g[0]}-{g[-1]}")
        got = ask(g)
        for e in got:
            if e.level == 0:
                context = {"part": e.title}
            elif e.level == 1:
                context = {**context, "section": e.title}
        entries += got
    for n, e in enumerate(entries, 1):
        e.id = f"t{n:04d}"
    return entries, warnings


def flag_suspects(entries: list[TocEntry]) -> int:
    """Số trang in phải tăng dần. Giữ dãy không giảm dài nhất; mục ngoài dãy đó (hay là chữ số bị OCR sai) bị đánh dấu."""
    idx = [i for i, e in enumerate(entries) if e.printed_page is not None]
    pages = [p for p in (e.printed_page for e in entries) if p is not None]
    n = len(pages)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pages[j] <= pages[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    keep: set[int] = set()
    k = max(range(n), key=lambda i: best[i], default=-1)
    while k >= 0:
        keep.add(k)
        k = prev[k]
    flagged = 0
    for pos, i in enumerate(idx):
        bad = pos not in keep
        entries[i].suspect = bad
        if bad:
            entries[i].suspect_reason = "số trang không tăng dần (có thể đọc sai chữ số)"
            flagged += 1
    return flagged


# ---------------------------------------------------------------- chạy / tổng kết
def _locate_toc_pages(llm: LLMClient, rows: list[PageRow], total: int, pages_opt: object,
                      pdf: Callable[[], Path]) -> tuple[list[int], str, str]:
    explicit = str(pages_opt or "").strip()
    if explicit:
        pages = sorted(parse_page_ranges([x for x in explicit.split(",")], total))
        if not pages:
            raise StageError(f"Số trang mục lục không hợp lệ: {explicit!r} (ví dụ đúng: 8-22)")
        return pages, "user", "do bạn nhập"
    pages, reason = find_toc_pages(llm, build_digests(rows, total, pdf))
    return pages, "llm", reason


def read_toc(pdf: Callable[[], Path], rows: list[PageRow], ext: ExtractionConfig, llm: LLMClient,
             docling: DoclingClient | None, pages_opt: object = None, on_progress: OnProgress = lambda *_: None,
             on_log: OnLog = lambda _msg: None) -> TocAuto:
    """Trang mục lục + chữ trang -> kết quả máy `toc.auto.json` (chưa áp override/độ lệch)."""
    total = count_pages(rows, pdf)
    # Bước 1: xác định trang mục lục (người dùng nhập hoặc LLM tìm)
    on_progress(0, 3, "xác định trang mục lục")
    pages, source, reason = _locate_toc_pages(llm, rows, total, pages_opt, pdf)
    on_log(f"trang mục lục ({source}): {pages[0]}-{pages[-1]} ({len(pages)} trang) — {reason}")
    # Bước 2: lấy chữ các trang mục lục
    on_progress(1, 3, "đọc chữ các trang mục lục")
    texts = get_page_texts(pages, rows, ext, pdf, docling, on_progress)
    if not any(t.strip() for t in texts.values()):
        raise StageError("Các trang mục lục không có chữ — hãy kiểm tra lại số trang, hoặc chọn cách đọc “nhận dạng chữ từ ảnh” trong Cài đặt.")
    # Bước 3: LLM chuyển chữ thành cây mục
    entries, warnings = parse_entries(llm, texts, on_progress, on_log)
    if not entries:
        raise StageError("AI không đọc ra mục nào từ các trang mục lục.")
    # Bước 4: đánh dấu mục có số trang đáng ngờ
    flagged = flag_suspects(entries)
    if flagged:
        warnings.append(f"{flagged} mục có số trang không tăng dần theo thứ tự mục lục (thường do đọc sai chữ số) — vui lòng kiểm tra các mục được tô vàng.")
    return TocAuto(toc_pages=pages, pages_source=source, entries=entries, meta=TocMeta(warnings=warnings, reason=reason))


def summarize_toc(doc: TocDoc) -> dict[str, Any]:
    """Summary hiển thị cho người duyệt, tính từ `toc.json`."""
    by_level = Counter(e.level for e in doc.entries)
    summary: dict[str, Any] = {
        "toc_pages": f"{doc.toc_pages[0]}-{doc.toc_pages[-1]}", "pages_source": doc.pages_source, "entries": len(doc.entries),
        "parts": by_level.get(0, 0), "sections": by_level.get(1, 0), "topics": by_level.get(2, 0) + by_level.get(3, 0),
        "suspect": sum(1 for e in doc.entries if e.suspect), "offset": doc.offset, "anchored": doc.anchored,
    }
    if doc.warnings:
        summary["warnings"] = doc.warnings
    return summary
