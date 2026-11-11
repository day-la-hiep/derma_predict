def cut_chunks(doc: TocDoc, rows: list[PageRow], cfg: ChunkingConfig, *, document_id: str, document_title: str,
               figure_pages: list[tuple[str, int]], on_progress: OnProgress) -> tuple[list[DocumentChunk], list[dict], dict[str, Any]]:
    """`toc.json` + các trang (đã bỏ trang nhiễu) -> (chunks, danh sách chunk cần soát, summary)."""
    if doc.offset is None:
        raise StageError("Chưa xác định được độ chênh lệch số trang — hãy nhập tay ở bước Mục lục rồi làm lại.")
    # Bước 1: mục lục -> các nút có điểm bắt đầu; thân sách -> các dòng chữ (bỏ trang mục lục)
    nodes = build_toc_nodes(doc, max(r.page for r in rows))
    if not nodes:
        raise StageError("Không mục nào của mục lục nằm trong các trang đã đọc — hãy kiểm tra độ chênh lệch số trang.")
    skip = set(doc.toc_pages)
    units = [(r.page, i, ln) for r in rows if r.page not in skip for i, ln in enumerate(r.text.split("\n"))]
    # Bước 2: cắt chunk theo khung mục lục
    on_progress(1, 2, "cắt chunk")
    chunks, outside = build_chunks(nodes, units, cfg, document_id=document_id, document_title=document_title,
                                   printed_offset=doc.offset, figure_pages=figure_pages)
    if not chunks:
        raise StageError("Không tạo được đoạn nào (nội dung sách có thể đang trống).")
    return chunks, build_review(chunks, cfg), _summarize(chunks, nodes, doc, outside, cfg)
