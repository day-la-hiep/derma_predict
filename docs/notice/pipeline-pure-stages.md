# Pipeline document ingest: hàm thuần + service chạy bước

## Quy tắc
- `pipeline/document_ingest/stages/step*.py` chỉ là hàm biến đổi dữ liệu. Đọc/ghi MinIO, đọc override, kiểm tra LLM/Docling/embedding/Neo4j và ghi trạng thái nằm ở `app/services/document_stage_runner.py` (`DocumentStageRunner`); `DocumentIngestPipelineService` chỉ giữ máy trạng thái, hàng đợi và hai bảng dispatch `_runners`/`_reappliers`.
- Dữ liệu giữa các hàm là model Pydantic (`pipeline/document_ingest/types.py`, `DocumentChunk`, `DocumentTriple`); mọi field có `description`.

## Điểm dễ nhầm
- **File JSON giữ tên, nhưng nay đủ field mặc định.** `toc.json` và `toc.auto.json` ghi bằng `model_dump()` nên mỗi mục có đủ khoá (`suspect`, `edited`, `pdf_page`... với giá trị mặc định) thay vì chỉ khoá đã set. Code đọc dict bằng `.get()` vẫn đúng.
- **Đọc file cũ**: model dùng `extra="ignore"` + giá trị mặc định, nên file trong MinIO thiếu/thừa key vẫn nạp được.
- **`approve` và `reapply` của `DocumentIngestPipelineService` trả `DocumentOutput`**, không còn trả summary. Muốn xem summary thì đọc `repo.status(...)["stages"][stage]["summary"]`.
- **Dừng bước**: callback `progress` của `StageRunState` ném `StageCancelled`; hàm thuần chỉ cần gọi `on_progress` trong vòng lặp lớn.
- **Test**: thay một bước bằng `patch.dict(service._runners, {"ingest": fn})` (không patch method, vì bảng dispatch đã bind lúc khởi tạo); embedding nằm ở `service.runner._embedding`.
- **File tạm PDF** nằm ở `/tmp/document_ingest_tmp/<document_id>/`, chỉ bị xoá khi xoá tài liệu (xem `docs/pending/pipeline-ingest-cleanup.md`).
