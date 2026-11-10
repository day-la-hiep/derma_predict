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
