# pipeline/document_ingest — sách giáo khoa → đoạn nội dung theo mục lục

Pipeline số hoá sách: lấy khung **part → section → mục** (kèm số trang) từ **mục lục** của sách,
rồi chunk tự do trong khung đó. Mỗi chunk mang metadata của mục chứa nó.

```
PDF → ingest (chữ từng trang) → toc (LLM đọc mục lục, người duyệt) → độ lệch + neo (luật) → chunks → index (Qdrant)
                                                                                         └→ graph (LLM trích quan hệ, người duyệt) → graph_index (Neo4j)
```

| Bước | Module | Ra (trong MinIO `document/<document>/`) | LLM |
|---|---|---|---|
| ingest | `stages/step1_ingest.py` | `pages.jsonl` | không |
| toc | `stages/step2_toc.py` + `mapping.py` | `toc.auto.json` (máy), `toc.json` (đã áp override + độ lệch + neo) | đọc vài chục trang mục lục |
| chunks | `stages/step3_chunks.py` | `chunks.jsonl`, `review/chunks.json` | không |
| index | `stages/step4_index.py` (+ `DocumentService`) | `index.json` + các point trong Qdrant | không (embedding qua OpenRouter) |
| graph | `stages/step5_graph.py` + `graph_schema.py` + `graph_link.py` | `graph/units.json`, `graph/unmapped.json`, `triples.auto.jsonl` (máy), `triples.jsonl` (đã áp override) | chia lô theo mục nhỏ nhất, AI nêu chủ thể và trích theo ô, chọn nút khớp |
| graph_index | `stages/step6_graph_index.py` (+ `DocumentGraphService`) | `graph_index.json` + cạnh `source='DOC'` trong Neo4j | không |

- `graph` chỉ trích quan hệ có trong PrimeKG/DermO (registry `graph_schema.py`, cộng loại / quan hệ bác sĩ định nghĩa trong bảng `graph_entity_types`, `graph_relations`),
  khớp tên vào từ điển PrimeKG đầy đủ + DermO. Luồng và giới hạn: `docs/module/knowledge-graph-flow.md`, `docs/module/knowledge-graph.md`.

- `toc` **không phụ thuộc** `ingest`: đọc mục lục chỉ OCR riêng vài trang. `mapping.py` (độ lệch + neo) cần `pages.jsonl` nên
  được tính lại mỗi khi sửa mục lục (`reapply`) và ngay trước khi chunk — rất rẻ, không gọi LLM.
- Không chắc thì báo, không đoán im lặng: `suspect` (số trang không tăng dần), `out_of_range`, `anchored=false` → chunk `boundary`.
- Sửa tay lưu ở bảng `document_overrides` nên chạy lại LLM không mất; đổi khung không phải OCR lại.
- Giới hạn: chỉ có những mục mà mục lục liệt kê; một độ lệch duy nhất cho cả sách; số trang OCR sai nhưng vẫn tăng dần chưa bắt được.

## Cách chạy

Không có CLI: dùng giao diện `/doctor/documents` (hoặc gọi thẳng API `/api/v1/admin/documents/*`). Core chỉ kiểm tra điều kiện, ghi
`running` rồi publish `document_ingest_queue`; **Ingest Worker** (`make ingest-worker`, `app/workers/document_ingest_worker.py`) chạy bước
(mỗi lần một bước, trong thread), giao diện poll trạng thái; nút Dừng đặt cờ Redis, bước dừng ở điểm kiểm tra gần nhất.
Worker khởi động lại thì các bước còn `running` từ lần trước được đánh dấu `failed` và làm lại được (bước đọc nội dung có điểm lưu nên không
phải đọc lại các trang đã xong). Cần MinIO, Redis, RabbitMQ, Postgres, Qdrant (và Neo4j cho `graph_index`) đang chạy.

## Chỗ đặt code

`pipeline/` chỉ tập trung vào **logic xử lý/biến đổi dữ liệu** (đọc chữ, đọc mục lục, đối chiếu số trang, chia đoạn, cấu hình sách). Phần còn lại
nằm ở `app/` theo quy ước của Core:

| Việc | Nơi đặt |
|---|---|
| Client + capability generic: MinIO (`MinioClient`), Qdrant (`QdrantVectorClient`), Redis + khoá phân tán (`RedisClient`), LLM trả JSON (`LLMClient`), Docling (`DoclingClient`), embedding (`EmbeddingClient`) | `app/infra/*_client.py` |
| Nghiệp vụ sách trên client generic: CRUD sách, cài đặt, mục lục, chunk, ảnh trang, nhật ký, profile; chunk trong Qdrant (`DocumentService`) | `app/services/document_service.py` |
| Truy cập dữ liệu sách: `DocumentRepository`, các bước + phụ thuộc, trạng thái, override, nhật ký, xoá sách | `app/repositories/document_repository.py` |
| Chạy từng bước: đọc/ghi MinIO, kiểm tra LLM/Docling/embedding/Neo4j, gọi hàm thuần (`DocumentStageRunner`, `StageRunState`) | `app/services/document_stage_runner.py` |
| Điều khiển pipeline (`DocumentIngestPipelineService`: kiểm tra, ghi `running` + publish queue, chạy bước, dừng, duyệt, áp lại override; bảng dispatch `_runners`/`_reappliers`) | `app/services/document_ingest_pipeline_service.py` |
| Tiến trình chạy bước (consume `document_ingest_queue`) | `app/workers/document_ingest_worker.py` |
| Đồ thị sách: tìm nút, danh sách / sửa quan hệ, ghi Neo4j | `app/services/document_graph_service.py`, `app/infra/neo4j_client.py` |
| API / DTO | `app/api/document_api.py`, `app/dto/request/document.py`, `app/dto/response/document.py` |
| **Tạo/giữ/đóng mọi instance** ở trên (`get_document_service()`, `get_document_ingest_pipeline_service()`...) | `app/api/deps.py` |
| Schema cấu hình sách (`Profile`, Pydantic) | `app/models/document_profile.py` |
| MinIO giả cho test | `tests/memory_infra.py` |

`DocumentStageRunner` nhận client qua constructor; mỗi hàm `run_*` đọc đầu vào từ MinIO, gọi **hàm thuần** trong `stages/` rồi ghi đầu ra. Hàm thuần nhận dữ liệu thường
(hoặc model trong `types.py`), trả dữ liệu, báo tiến độ/nhật ký qua hai callback `on_progress(done, total, message)` và `on_log(message)`; dừng = callback ném `StageCancelled`.
Test gọi thẳng hàm thuần (`tests/test_pure_stages.py`, không cần dịch vụ nào) và chạy cả luồng qua service bằng `MemoryMinio` + SQLite file tạm (thay Postgres) + `QdrantClient(":memory:")` + embedding giả.

Trong `pipeline/document_ingest/`: `stages/` (step1_ingest `extract_pages`, step2_toc `read_toc`, step3_chunks `cut_chunks`, step4_index `embed_chunks`, step5_graph `extract_triples`, step6_graph_index `build_graph_payload`),
`mapping.py` (độ lệch + neo, `build_toc`, `build_tree`), `types.py` (model dữ liệu giữa các hàm: `PageRow`, `TocEntry`, `TocAuto`, `TocDoc`, `TocNode`... mọi field có `description`), `graph_schema.py` (loại thực thể + quan hệ),
`graph_link.py` (khớp tên vào từ điển PrimeKG + DermO), `textutil.py`, `profile.py` (cấu hình sách mặc định).

## Lưu trữ (không còn workspace trên đĩa)

Mọi thứ nằm trong **MinIO**, bucket `MINIO_DOCUMENTS_BUCKET` (mặc định `derma-documents`), dưới `document/<document_id>/`: `source.pdf`, `page_img/p<N>.png`,
`pages.jsonl`, `toc.auto.json`, `toc.json`, `chunks.jsonl`, `index.json`, `triples.auto.jsonl`, `triples.jsonl`, `graph/`, `graph_index.json`, `review/`, `logs/`, `docling_parts/`
(điểm lưu để OCR tiếp tục được). Cache LLM ở `_cache/llm/`. Chunk được embed (`EMBEDDING_MODEL`, mặc định `qwen/qwen3-embedding-8b` qua OpenRouter, 4096 chiều) và nạp vào **Qdrant** collection
`QDRANT_DOCUMENT_COLLECTION` (mặc định `derma_document_chunks_v4`; vector dense + sparse `bm25`, IDF do Qdrant tính — Qdrant không thêm sparse vector vào collection đã tạo nên bản cũ `derma_document_chunks` cần index lại sang collection mới), payload có `document_id`, `toc_path`, trang, `source_pdf`.

Tiền xử lý cho tìm từ khoá (`app/infra/bm25/`): làm sạch chữ OCR (`text_clean`), tách từ ghép tiếng Việt bằng underthesea, bỏ stopword (giữ phủ định và đơn vị liều), stem tiếng Anh bằng Snowball (nltk). Mỗi tài liệu chọn `text_language` (vi / en / mixed) trong cài đặt; giá trị này được ghi vào payload `bm25_mode` để câu hỏi được mã hoá đúng cách cho từng nhóm. Đổi ngôn ngữ hoặc tokenizer thì phải làm lại bước Lưu vào kho.

- Chỉ backend (Core) chạm MinIO/Qdrant; FE chỉ gọi API (ảnh trang được Core đọc từ MinIO rồi trả về).
- Trạng thái bước nằm ở bảng `document_stages` (Postgres) và override ở `document_overrides`; MinIO không còn `status.json` / `overrides/`. Thư mục tạm chỉ chứa bản sao PDF cho
  pdftotext/Docling/pdftoppm (`/tmp/document_ingest_tmp/<document_id>/`, xoá cùng sách; không có job dọn bản sao của sách không bị xoá).
- Xoá sách xoá cả đối tượng MinIO lẫn point Qdrant của sách. Chạy lại bước `index` thay thế toàn bộ point cũ của sách.

Test dùng `MemoryMinio` + SQLite + Qdrant in-memory + embedding giả (không cần dịch vụ nào chạy).

Giao diện: `/doctor/documents` (API `/api/v1/admin/documents/*`).
Test: `python -m unittest pipeline.document_ingest.tests.test_document_pipeline pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index pipeline.document_ingest.tests.test_graph pipeline.document_ingest.tests.test_graph_schema pipeline.document_ingest.tests.test_text_preprocess pipeline.document_ingest.tests.test_pure_stages` và `tests/test_reindex_qdrant.py`.
