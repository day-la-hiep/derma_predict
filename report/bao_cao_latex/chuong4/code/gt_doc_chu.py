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
