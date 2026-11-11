# [Lưu ý] Trích dẫn gợi ý AI truy vết được

Nút trích dẫn ở gợi ý AI của bác sĩ mở được tài liệu gốc và đoạn sách được trích. Code: `ai_service` (`book_result`, `label_tool_evidence`), `knowledge_service/app/api/citation_api.py`, hợp đồng ở `contracts/README.md` mục 8.

## Điểm cần lưu ý

- **`ref` chỉ có từ khi có tính năng này.** Giả thuyết ghi trước đó (và bằng chứng không phải đoạn sách: đồ thị, ca bệnh, gợi ý ảnh) không có `ref`, FE không hiện nút. Không backfill được vì dữ liệu cũ không lưu `document_id`.
- **Trang PDF khác trang in.** `ref.page_start/page_end` là trang trong file PDF (để mở đúng chỗ), còn `source` / `pages` hiển thị là trang in trên sách. Hai số lệch nhau do bìa, lời nói đầu.
- **URL file gốc hết hạn sau 30 phút** (presigned MinIO). Mở lại sẽ xin URL mới; trình duyệt phải với tới được địa chỉ MinIO mà knowledge cấu hình (`MINIO_ENDPOINT`), ví dụ trong Docker nội bộ thì URL không dùng được từ máy ngoài.
- **Quyền:** `doctor` hoặc `admin`. Bệnh nhân không có route này; phần quản trị tài liệu `/admin/documents/*` vẫn chỉ admin.
- **Đoạn trích đọc từ `chunks.jsonl`**, không phải Qdrant: nếu bước `chunks` của tài liệu chạy lại thì `chunk_id` cũ có thể không còn khớp (đoạn hiển thị nhưng không có `is_cited`).
