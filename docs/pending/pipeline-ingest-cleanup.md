# [Pending] Dọn tiếp pipeline document ingest

## Vấn đề
Sau khi tách `pipeline/` thành hàm thuần, vẫn còn vài chỗ rườm rà hoặc chưa đồng nhất.

## Việc chưa làm
- **Summary của từng bước vẫn là `dict`** (`build_summary`, `summarize_toc`, `summarize_triples`...). Muốn class hoá (`IngestSummary`, `TocSummary`...) cần chốt: `DocumentStage.summary` ở `dto/base` đang là `dict`, nên service phải `model_dump(exclude_none=True)` để FE nhận đúng hình dạng cũ.
- **`topics`/`unmapped`/item trích của `step5_graph` vẫn là dict.** Có thể thêm `Topic`, `ExtractedItem`, `UnmappedItem` vào `types.py`.
- **`DocumentService` còn đọc `toc.json`, `pages.jsonl`, `figures.json`, `chunks.jsonl` bằng dict** (xem mục lục, trang nguồn, danh sách chunk) thay vì dùng `TocDoc`/`PageRow`/`DocumentChunk`.
- **Double DTO mapping**: entity `dto/base` → wire DTO (`_stage_output()`...) đi hai lượt; có thể trả thẳng một kiểu.
- **`DocumentOverrideRepository` tách riêng khỏi `DocumentRepository`** (`repo.overrides`); có thể gộp vì chỉ có một chỗ dùng.
- **Dọn file tạm**: `/tmp/document_ingest_tmp/<id>/` chỉ xoá khi xoá tài liệu; chưa có job dọn khi worker khởi động. Kiểm tra "dùng lại bản sao" chỉ so kích thước.
- **`QdrantReindexService` gọi `pipeline.runner.index_document_chunks`**; nếu tách `DocumentStageRunner` thành object độc lập trong `deps.py` thì reindex không cần biết `DocumentIngestPipelineService`.

## Câu hỏi cần chốt
- Có đưa `PageRow`/`TocEntry`... lên `dto/base` (cần duyệt trước) hay giữ trong `pipeline/types.py`?

## Phụ thuộc
Không phụ thuộc việc khác; làm sau khi bảo vệ cũng được.
