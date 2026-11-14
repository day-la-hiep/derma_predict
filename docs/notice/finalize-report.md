# Báo cáo kết luận (FinalizeReport)

## Chốt theo lần khám (hiện tại): mô tả của bác sĩ → dữ kiện
- **Dữ kiện AI chỉ xoá hoặc giữ.** Form "Kết luận" liệt kê dữ kiện hiện hành đọc từ graph theo dõi (knowledge); bác sĩ bỏ bớt hoặc để nguyên, không sửa/thêm tay. `facts` gửi lên = các dữ kiện được giữ (`source_fact_id` = id cạnh trong graph); dữ kiện vắng mặt chép vào `snapshot.removed_facts`. **Chốt không ghi ngược vào graph** (không xoá, không sửa, không đánh dấu xác nhận ở đó): graph chỉ phản ánh điều người bệnh nói với AI, nên fact bác sĩ đã bỏ vẫn hiện ở lần khám sau.
- **Bắt buộc 3 trường:** `diagnosis` (nhận định), `reasoning` (cơ sở nhận định), `description` (mô tả của bác sĩ, văn bản tự do về điều khám thấy) cộng `diagnosis_code`. Thiếu thì 422 trước khi gọi ai.
- **Mô tả → dữ kiện lúc chốt.** Clinical gọi `POST ai /internal/extract-facts-from-description` **trước transaction** (không giữ kết nối DB lúc gọi LLM) với các dữ kiện đã giữ làm `known_facts`. Dữ kiện mới (kèm `site_text`/`onset_text` khi bác sĩ viết rõ vị trí, thời điểm; ai không suy ra): origin `doctor_observed`; trùng khoá (loại + nhãn, không phân biệt hoa thường) với một dữ kiện đã giữ thì lấy `detail` từ mô tả và origin `doctor_corrected`.
- **Xác nhận chỉ có ở snapshot:** mọi dữ kiện trong `snapshot.clinical_facts` là dữ kiện bác sĩ đã xem và chốt (origin cho biết giữ nguyên, sửa hay bác sĩ tự quan sát); graph không có `verified_*` nên màn bác sĩ hiện "Chưa xác nhận" cho tới khi chốt. Graph không đọc được thì chốt trả 502 và không lưu gì (giống khi ai lỗi).
- **Ai lỗi → 502 "Chưa chuyển được mô tả thành dữ kiện, vui lòng thử lại."** và **không chốt gì** (không tạo báo cáo, lần khám/lịch/đợt giữ nguyên); bác sĩ bấm lại được. Đây là chủ ý: chốt thiếu dữ kiện còn tệ hơn phải thử lại.
- **Lưu mô tả:** `snapshot.assessment.description` (JSON, không migration; báo cáo cũ là null). Knowledge đưa mô tả vào văn bản ca bệnh để embedding.
- **Điểm dễ nhầm:** mô tả nhắc lại dữ kiện bác sĩ vừa bỏ thì dữ kiện đó được tạo lại như dữ kiện mới (clinical flush việc xoá trước khi thêm để không vướng chỉ mục duy nhất). Dữ kiện LLM trả về loại không hợp lệ bị bỏ và ghi log. Chưa kiểm chứng với LLM thật: chất lượng nhãn/`detail` phụ thuộc model.

## Ghi chú cũ (luồng chốt theo phiên tư vấn, đã gỡ)

- **Định nghĩa.** Kết luận cuối do bác sĩ chốt khi "Đóng ca" một phiên tư vấn; tên cũ là `MedicalRecord` / "bệnh án". Bảng `finalize_reports`, **1 báo cáo / `consultation_session`** (unique); một hội thoại có nhiều phiên nên có nhiều báo cáo.
- **Khác `pre_consultation_reports`.** Bản đó là tóm tắt AI trước tư vấn và có thể bị sinh lại; báo cáo kết luận là của bác sĩ, không sửa sau khi chốt. Không gộp hai bảng để khỏi ghi đè kết luận.
- **Không còn "khám trực tiếp".** Đã xoá `POST /doctor/finalize-reports` và tìm hồ sơ bệnh nhân để ghi tay. Dòng cũ có `consultation_session_id IS NULL` vẫn giữ nguyên (cột còn nullable).
- **Gợi ý từ đồ thị không dùng LLM.** `GET .../finalize-draft` trả `suggestions`: nhận định/lời khuyên các phiên trước (Neo4j PJKG), bệnh ứng viên (`diseases_with_symptom`) và cờ đỏ (`red_flags_risk`) từ KG. Tên triệu chứng không khớp đồ thị thì bỏ qua (`translate=False`), nên triệu chứng tiếng Việt thường ít gợi ý. Lỗi graph không chặn đóng ca. Chỉ là gợi ý, không phải chẩn đoán.
- **Qdrant.** Collection đổi `derma_medical_cases` → `derma_finalize_reports`; collection cũ không tự xoá và collection mới trống cho tới khi chạy `make reindex-qdrant only=finalize-reports` (cần OpenRouter để embedding). Đến lúc đó tool `search_finalize_report*` của agent không tìm được ca nào.
- **Migration** `a7c1e9d4b302` dừng nếu có phiên nào đã có >1 báo cáo (trước khi thêm unique).
