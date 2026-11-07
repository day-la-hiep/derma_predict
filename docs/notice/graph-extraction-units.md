# Bước `graph`: trích theo lô, chủ thể do AI nêu

- Bước `graph` không còn phân loại mục là "bệnh / thuốc / khác". Chunk được chia thành **lô** (tối đa `chunks_per_call`
  chunk liền nhau, không vượt ranh giới mục nhỏ nhất của mục lục); AI đọc từng lô và tự nêu **chủ thể** của mỗi quan hệ.
  Lý do: sách có mục lục thô (Andrews chỉ có 39 chương) bị xếp toàn `other` nên không trích được quan hệ nào.
- Loại chủ thể (bệnh hay thuốc) suy ra từ ô quan hệ (`Slot.topic`), không do AI chọn.
- Quan hệ thiếu chủ thể bị bỏ và tính vào `subject_missing` (cảnh báo trong summary + nhật ký). Câu trích không có thật
  trong lô vẫn bị loại như trước (`evidence_dropped`).
- `triple_id` giờ băm theo **chủ thể do AI nêu** thay vì mã mục. Chạy lại `graph` trên sách đã có duyệt tay sẽ sinh mã mới:
  `rejected` / `relink` trong override cũ không còn khớp quan hệ nào (không lỗi, chỉ không có tác dụng).
- Chạy thử: tuỳ chọn `limit_calls` (số lượt gọi AI, lấy rải đều khắp sách). Chạy cả sách đọc **mọi** chunk nên tốn nhiều
  lượt hơn bản cũ (Andrews 4.232 chunk, lô 3 chunk ≈ 1.400 lượt).
- Chủ thể ở lô nằm giữa hai bệnh có thể bị gán nhầm; câu trích nguyên văn giúp người duyệt kiểm tra ở `TripleBrowser`.
- `graph/topics.json` không còn được ghi (thay bằng `graph/units.json`); file cũ trên MinIO không được đọc.
- `DocumentChunk` bỏ `part/section/topic/subtopic`, chỉ còn `toc_path`. Point Qdrant đã index trước đó vẫn mang các trường cũ
  trong payload cho tới khi chạy lại bước `index`; truy xuất chỉ đọc `toc_path` nên không bị ảnh hưởng.
