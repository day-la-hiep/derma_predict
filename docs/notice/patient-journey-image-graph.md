# Nối ảnh bệnh nhân tải lên vào Đồ thị hành trình (Patient Journey Knowledge Graph)

## 1. Bản chất & Schema
- Node mới trên Neo4j: `:PatientImage`
  - Thuộc tính: `id` (trùng với `file_id` trong PostgreSQL/MinIO), `url` (`/api/v1/files/{file_id}/view`), `body_site` (vị trí tổn thương giải phẫu), `content_type`, `confirmed_label` (nhãn chẩn đoán bác sĩ xác nhận), `description`.
- Các quan hệ:
  - `(s:ConsultationSession)-[:HAS_IMAGE]->(img:PatientImage)`: Phiên tư vấn đính kèm ảnh.
  - `(img:PatientImage)-[:EVIDENCES]->(f:ClinicalFact)`: Ảnh làm bằng chứng cho dữ kiện lâm sàng (triệu chứng, tổn thương) được trích xuất từ tin nhắn chứa ảnh đó.
  - `(img:PatientImage)-[:CONFIRMED_AS]->(c:SuspectedCondition)`: Nhãn chẩn đoán bác sĩ xác nhận gắn với ảnh này khi chốt ca.
  - `(img_prev:PatientImage)-[:FOLLOWS]->(img_curr:PatientImage)`: Tự động nối giữa 2 ảnh có cùng vị trí `body_site` thuộc 2 phiên kế tiếp (`(s_prev)-[:NEXT]->(s_curr)`), biểu diễn sự tiến triển tổn thương theo thời gian (*Before / After progression*).

## 2. Hai thời điểm đồng bộ
1. **Lúc hoàn tất tiền tư vấn (`save_generated_report` trong `ConsultationService`)**:
   - Quét tất cả tin nhắn trong cuộc trò chuyện gắn với phiên, lọc các file `content_type` dạng ảnh (`image/*`).
   - Dựa trên `provenance_pairs` (`fact_id -> message_id`), tự động kết nối `(img)-[:EVIDENCES]->(fact)`.
2. **Lúc bác sĩ chốt ca (`_create` trong `FinalizeReportService`)**:
   - Truyền danh sách `attached_images` có `body_site` và `confirmed_label` vào `sync_finalized_session`.
   - Cập nhật thông tin lên node `:PatientImage` và nối sang `:SuspectedCondition`.

## 3. Hiển thị trên Frontend (Doctor Portal)
- Canvas đồ thị: Node `PatientImage` được xếp ở phía trên phiên tư vấn, màu xanh cyan (`#06b6d4`), icon `ImageIcon`.
- Timeline: Hiển thị thumbnail ảnh tổn thương thu nhỏ dưới phần tóm tắt của từng phiên.
- Inspector (panel bên phải): Click vào node `PatientImage` sẽ hiển thị ảnh trực tiếp, vị trí cơ thể và nhãn chẩn đoán xác nhận.
