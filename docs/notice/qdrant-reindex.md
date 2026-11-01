# Nạp lại Qdrant (`scripts/reindex_qdrant.py`)

- **Nguồn nạp lại là MinIO/Postgres, không phải Qdrant.** Chunk sách lấy từ `document/<id>/chunks.jsonl`, ca bệnh từ bảng `finalize_reports`; embedding và sparse vector sinh lại từ đó. Payload trong Qdrant không đủ để dựng lại (thiếu ngôn ngữ BM25, ảnh...).
- **Không đổi trạng thái stage.** Với sách, script gọi trực tiếp `stages/index.run` thay vì `begin/execute`, nên stage `index` vẫn `approved`, các bước sau không bị `stale`; tiến độ/nhật ký của bước không ghi vào DB.
- **Embedding chạy xong mới xoá điểm cũ của tài liệu** (logic sẵn có của bước `index`): lỗi mạng/quota không làm mất dữ liệu. Giữa lúc xoá và upsert xong, tài liệu đó tạm thiếu trong kết quả tìm.
- **Đổi model/số chiều hoặc collection thiếu sparse vector → phải đổi tên collection** (`QDRANT_DOCUMENT_COLLECTION`, ví dụ `..._v5`) rồi chạy lại; Qdrant không thêm sparse vector vào collection đã tạo. Script không tự xoá collection cũ, không sửa `.env`.
- **Một mục lỗi không chặn mục khác**; kết thúc in tổng ok/bỏ qua/lỗi, exit code 1 nếu có lỗi. Tài liệu có stage `index` chưa chạy bị bỏ qua.
- **Chưa làm:** không xoá điểm mồ côi (ca đã xoá khỏi DB nhưng còn trong Qdrant); không nạp lại Neo4j (`graph_index`).
- Dùng: `make reindex-qdrant [only=documents|finalize-reports] [document=<id>] [dry=1]`; nên chạy `dry=1` trước.
