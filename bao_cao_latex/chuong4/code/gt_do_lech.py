def build_toc(auto: TocAuto, overrides: dict[str, Any], rows: list[PageRow], total_pages: int) -> TocDoc:
    """Áp override lên kết quả AI (`toc.auto.json`), dựng cây + độ lệch + neo -> nội dung `toc.json` (hàm thuần, không ghi file)."""
    entries = apply_overrides(auto.entries, overrides)
    skip = set(auto.toc_pages)
    if overrides.get("_offset") is not None:
        off, info = int(overrides["_offset"]), {"source": "user"}
    else:
        off, info = estimate_offset(rows, entries, skip)
        info["source"] = "auto"
    build_tree(entries)
    anchored = anchor_entries(entries, rows, off, skip, total_pages) if off is not None else 0
    warnings = list(auto.meta.warnings)
    if off is None:
        warnings.append("Chưa xác định được độ chênh lệch giữa số trang in và số trang trong file PDF: hãy nhập tay, "
                        "hoặc làm bước Đọc nội dung để hệ thống tự tính.")
    return TocDoc(toc_pages=auto.toc_pages, pages_source=auto.pages_source, entries=entries, offset=off, offset_info=info,
                  total_pages=total_pages, anchored=anchored, warnings=warnings)
