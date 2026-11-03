# [Pending] Danh mục mẫu fact do bác sĩ cấu hình

Bảng `clinical_fact_templates` cũ đã gộp vào `clinical_facts` (2026-11-03): template do `get_or_create_template` sinh tự do theo label LLM trả, nên không phải danh mục thật. Ý tưởng dưới đây là làm lại danh mục **đúng nghĩa**, khi có thời gian.

## Vấn đề
- LLM đặt label không ổn định ("Ngứa" / "Ngứa da") → fact trùng, vì khoá duy nhất là `(hồ sơ, fact_type, lower(label))`.
- `ontology_id` không có ai điền, graph phải đoán từ chữ tự do.
- `detail` không đều: lúc có thời gian khởi phát, lúc không.

## Luồng đề xuất
1. Bảng `clinical_fact_templates` (id, fact_type, label, ontology_id, `slots` jsonb — các ý cần ghi, vd `["thời gian", "vị trí", "mức độ"]`, `enabled`). **Chỉ tạo/sửa qua màn hình admin/bác sĩ**, AI không bao giờ tạo.
2. `clinical_facts.template_id` nullable. Fact ngoài danh mục: `template_id = NULL`, `fact_type = other` hoặc giữ loại, label tự do → hiện trong danh sách "chờ đưa vào danh mục".
3. Bộ trích fact nhận danh mục (lọc theo `fact_type` hoặc top-N gần nghĩa) và phải chọn label có sẵn; `slots` dùng để agent biết cần hỏi thêm gì.
4. Bác sĩ gộp fact ngoài danh mục vào một template → cập nhật `template_id`, label theo template.

## Câu hỏi cần chốt
- Ai được sửa danh mục: chỉ admin, hay mọi bác sĩ?
- Danh mục ban đầu lấy từ đâu (DermO, triệu chứng thường gặp trong guideline)?
- Danh mục lớn thì chọn top-N bằng embedding hay chỉ lọc theo `fact_type`?

## Phụ thuộc
- Bảng fact hiện trạng + nhật ký `clinical_provenances` (đã làm).
