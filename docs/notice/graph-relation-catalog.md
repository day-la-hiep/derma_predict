# Danh mục quan hệ / loại thực thể của bước graph

Trang `/doctor/graph-schema` (API `/admin/graph-schema/*`). Bước `graph` trích theo `GraphSchema` = bảng core trong code
(`pipeline/document_ingest/graph_schema.py`) + định nghĩa của bác sĩ trong Postgres (`graph_relations`, `graph_entity_types`).

- **Core chỉ đọc, luôn bật.** Không seed vào DB để code và DB không lệch nhau.
- **Đổi danh mục không tự đánh `stale` các tài liệu.** Muốn áp dụng phải chạy lại bước `graph` của từng sách.
- **Trường cấu trúc không sửa được sau khi tạo** (loại quan hệ, chủ đề, đầu kia, chiều; mã và label của loại thực thể):
  triple và cạnh đã lưu phụ thuộc vào chúng. Muốn đổi thì xoá rồi tạo lại.
- **Tắt ≠ xoá.** Tắt: lần `graph` sau không trích nữa, nhưng triple đã duyệt vẫn được `graph_index` lưu. Xoá: xoá luôn
  mọi cạnh `source='DOC'` loại đó trong Neo4j (của mọi sách); triple cũ trong `triples.jsonl` bị `graph_index` bỏ qua kèm cảnh báo.
- **Loại thực thể tự định nghĩa không có từ điển chuẩn**: mọi thực thể thành nút mới `doc_<loại>_<slug tên tiếng Anh>`
  và tự được chấp nhận (không cần `allow_new_entities`). Gộp trùng chỉ theo tên tiếng Anh đã chuẩn hoá, không có đồng nghĩa;
  không có nút nào cùng nghĩa để khớp vào (đồ thị nền không còn các nút BYT `typical_location`, `risk_factor`, `red_flag`).
- Chủ đề chỉ là bệnh hoặc thuốc. Chủ đề thuốc không dùng được đầu kia là DermO.
- Agent chỉ dùng loại cạnh có trong `agent/tools/hybrid_retrieval/kg_templates.py::RELATION_LABELS`, và chỉ khi
  `KG_EDGE_SOURCES` có `DOC`. Quan hệ mới của bác sĩ vào được đồ thị nhưng agent chưa truy vấn tới.
- Loại quan hệ và label Neo4j được ghép thẳng vào câu Cypher; được chặn bằng regex ở `GraphSchemaService`, đừng nới lỏng.
