# Dữ kiện lâm sàng: bảng hiện trạng + nhật ký nguồn

Từ migration `07a23a2f124b` (2026-11-03). Thiết kế đầy đủ: `tmp/plan/2026-11-03-de-xuat-schema.html`.

## Quy tắc
- **`clinical_facts` là hiện trạng, sửa tại chỗ.** Mỗi (hồ sơ, `fact_type`, nhãn) đúng một dòng: unique index `uq_clinical_facts_profile_type_label` trên `lower(label)` — "Ngứa" và "ngứa" là cùng fact. Không còn `status` / `superseded_by_id`, không còn bảng template.
- **`clinical_provenances` là nhật ký chỉ thêm.** Mỗi dòng: một nguồn ghi nhận giá trị nào (`detail`) lúc nào. Đây là chỗ duy nhất giữ lịch sử giá trị của fact (vd tin m1 "3 ngày", tin m2 "10 ngày").
- Lưu fact (`ConsultationService.save_generated_report`): nhãn chuẩn hoá khoảng trắng → tìm theo khoá → có thì cập nhật `detail` (khác giá trị cũ thì xoá `verified_at`), chưa có thì tạo. Nhật ký chỉ thêm cặp (fact, tin) **chưa có**; `quote` chép nội dung tin (tối đa 500 ký tự).
- `message_id` của nhật ký là `ON DELETE SET NULL`: xoá hội thoại không làm fact mất bằng chứng (đọc `quote`).

## Điểm dễ nhầm
- **Id fact agent gửi về là id tạm** (`cf-...`). Core ánh xạ sang id thật sau upsert rồi mới đẩy SSE / đồng bộ graph — đừng dùng id trong `AgentResponseMessage.facts` để truy DB.
- **Migration gộp fact trùng là một chiều.** Bản trùng bị xoá, nhật ký dồn về bản mới nhất; downgrade không tách lại, và `detail` lịch sử của nhật ký mất khi downgrade (nhật ký cũ không có cột này).
- **Node `ClinicalFact` cũ trong Neo4j** của các bản trùng đã xoá vẫn còn (graph không bị migration đụng tới). Graph được dựng lại từ kết luận đã chốt ở Đợt 5.
- **Graph vẫn nhận fact lúc tạo báo cáo tiền tư vấn** (`sync_pre_consultation`) cho tới Đợt 5, vì `sync_finalized_session` đang `MATCH` node phiên mà bước đó tạo ra.
- Fact trích từ hội thoại khác nhau của cùng hồ sơ dồn vào cùng một dòng nếu trùng nhãn — kể cả triệu chứng của hai đợt bệnh khác nhau. Tách theo đợt bệnh là việc của Đợt 2 (`clinical_facts.episode_id`).
