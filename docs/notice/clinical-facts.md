# Dữ kiện lâm sàng: bảng hiện trạng + nhật ký nguồn + đợt bệnh

Từ migration `07a23a2f124b` (fact hiện trạng), `9d9ebfce7f5b` (đợt bệnh) và `5b2e8c41d7a9` (bỏ cột dị ứng / tiền sử), 2026-11-03. Thiết kế đầy đủ: `tmp/plan/2026-11-03-de-xuat-schema.html`.

## Quy tắc
- **`clinical_facts` là hiện trạng, sửa tại chỗ.** Không còn `status` / `superseded_by_id`, không còn bảng template. Nhãn so không phân biệt hoa thường ("Ngứa" = "ngứa").
- **Hai phạm vi fact.** `allergy` / `history` / `medication` là fact dài hạn của hồ sơ (`episode_id IS NULL`, khoá `uq_clinical_facts_long_term`); `symptom` / `lesion` / `other` thuộc một **đợt bệnh** (`clinical_episodes`, khoá `uq_clinical_facts_episode`). CHECK `ck_clinical_facts_long_term_no_episode` ép đúng phạm vi. "Ngứa" ở mặt và ở chân là 2 dòng.
- **Đợt bệnh = (hồ sơ, vùng, đợt).** Mỗi vùng tối đa 1 đợt `open` / `in_exam` (`uq_clinical_episodes_active_site`). Nhiều hội thoại cùng cập nhật một đợt. Đợt `open` không cập nhật quá `CLINICAL_EPISODE_EXPIRE_DAYS` (30) ngày thì bị đóng `expired` **lúc ghi** (không có job), lần ghi sau mở đợt mới.
- **Ghi theo lượt chat** (`ClinicalRecordService.apply_turn`, gọi từ `agent_response_consumer` khi `status="done"`): giả thuyết của `reflect` thay toàn bộ `ai_hypotheses` của đợt (đợt `in_exam` thì khoá, bỏ qua); fact upsert theo phạm vi; dự đoán CNN vào `clinical_episodes.image_predictions`.
- **`clinical_provenances` là nhật ký chỉ thêm.** Mỗi dòng: một nguồn ghi nhận giá trị nào (`detail`) lúc nào. Đây là chỗ duy nhất giữ lịch sử giá trị của fact (vd tin m1 "3 ngày", tin m2 "10 ngày").
- Lưu fact: nhãn chuẩn hoá khoảng trắng → tìm theo khoá → có thì cập nhật `detail` (khác giá trị cũ thì xoá `verified_at`), chưa có thì tạo. Nhật ký chỉ thêm cặp (fact, tin) **chưa có**; `quote` chép nội dung tin (tối đa 500 ký tự). **Báo cáo tiền tư vấn không còn ghi fact** (handler chỉ viết `summary`).
- **Hồ sơ không còn cột `allergies` / `medical_history`.** Form hồ sơ gửi `long_term_facts` = danh sách ĐẦY ĐỦ fact dài hạn (`ClinicalRecordService.replace_long_term_facts`): thêm / sửa theo (loại, nhãn), **mục bỏ khỏi form bị xoá — kể cả mục AI trích từ chat hay bác sĩ đã xác nhận**. Nhật ký `kind = 'profile'`. PATCH không gửi `long_term_facts` thì giữ nguyên.
- `PatientProfileDto.allergies` / `medical_history` (thẻ bệnh nhân của bác sĩ) và `SnapshotPatientProfile.allergies` / `medical_history` vẫn là chuỗi nhưng được **ghép từ fact** (`long_term_text`; snapshot ghép từ fact bác sĩ gửi lúc chốt). Payload Qdrant ca bệnh đọc từ snapshot.
- `message_id` của nhật ký là `ON DELETE SET NULL`: xoá hội thoại không làm fact mất bằng chứng (đọc `quote`).

## Memory (LangGraph store) ≠ fact
- Memory theo hồ sơ chỉ còn thông tin **giao tiếp** (ai nhắn hộ, xưng hô, mức chi tiết, ưu tiên). Prompt `BATCH_SYSTEM` / `CONSOLIDATE_SYSTEM` cấm lưu lâm sàng; phơi nhiễm (nghề nghiệp, mỹ phẩm, thú nuôi), mang thai / cho con bú → bộ trích fact ghi `history`.
- Trong prompt agent, memory nằm ở khối "Về người dùng" (không phải căn cứ y khoa), fact ở khối "Hồ sơ lâm sàng" (plan / reflect / answer).
- Memory cũ (câu tự do lâm sàng) xoá bằng `scripts/clear_profile_memories.py --apply` (mặc định chạy thử); giữ `memories_archive`.

## Điểm dễ nhầm
- **Mục chưa rõ vùng** (fact theo đợt, giả thuyết, ảnh không có `body_site` hợp lệ) gắn vào: đợt duy nhất lượt này đã chạm → nếu không, đợt `open` duy nhất của hội thoại → nếu vẫn không xác định được thì **bỏ (log)**. Fact bị bỏ vẫn nằm trong state của agent và được gửi lại ở lượt sau. Ảnh khi lượt chạm nhiều vùng: gắn vào đợt có giả thuyết trùng nhãn top-1 của CNN.
- **Nguồn của fact trỏ đúng bảng `messages` nhờ `TurnRequest.user_message_id`** (id DB gán cho `HumanMessage`). Tin trong checkpoint cũ có id ngẫu nhiên của LangGraph → bị bỏ khi ghi nhật ký (không có trong DB).
- **Agent đọc fact thẳng từ Postgres** (`agent/context/builder.py::_known_facts`, chỉ đọc; Core vẫn là nơi duy nhất ghi), nạp làm `known` mỗi lượt; giá trị trong DB đè giá trị cũ trong checkpoint. Đợt đã đóng / hết hạn không được nạp.
- **`code` / `body_site` của giả thuyết là chuỗi, không phải Literal**: model nhỏ ghi lệch thì chuẩn hoá (`agent/common/clinical_codes.py`): mã sai → suy từ tên bệnh qua bảng tên CNN → không khớp thì `OTHER`; vùng sai → trống.
- **Migration gộp fact trùng là một chiều.** Downgrade không tách lại; `detail` lịch sử của nhật ký mất khi downgrade M1; downgrade M2 gộp các fact cùng nhãn ở nhiều đợt.
- Fact symptom / lesion / other **trước 2026-11-03** không có vùng → nằm trong một đợt `closed` "dữ liệu cũ" (vùng `nhieu_vung`) mỗi hồ sơ; `image_finding` cũ → `other`. `ClinicalFactType.IMAGE_FINDING` vẫn còn trong enum chỉ để đọc snapshot cũ.
- **Graph hành trình**: báo cáo tiền tư vấn không gửi fact nữa → không có cạnh fact mới cho tới Đợt 5. Node `ClinicalFact` cũ của các bản trùng đã xoá vẫn còn trong Neo4j.
- Màn bác sĩ (`ClinicalFactOutput`) vẫn liệt kê mọi fact của hồ sơ, **chưa** nhóm theo đợt / hiện vùng — làm ở Đợt 4.
