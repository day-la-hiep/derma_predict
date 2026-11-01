# Báo cáo kết luận (FinalizeReport)

- **Định nghĩa.** Kết luận cuối do bác sĩ chốt khi "Đóng ca" một phiên tư vấn; tên cũ là `MedicalRecord` / "bệnh án". Bảng `finalize_reports`, **1 báo cáo / `consultation_session`** (unique); một hội thoại có nhiều phiên nên có nhiều báo cáo.
- **Khác `pre_consultation_reports`.** Bản đó là tóm tắt AI trước tư vấn và có thể bị sinh lại; báo cáo kết luận là của bác sĩ, không sửa sau khi chốt. Không gộp hai bảng để khỏi ghi đè kết luận.
- **Không còn "khám trực tiếp".** Đã xoá `POST /doctor/finalize-reports` và tìm hồ sơ bệnh nhân để ghi tay. Dòng cũ có `consultation_session_id IS NULL` vẫn giữ nguyên (cột còn nullable).
- **Gợi ý từ đồ thị không dùng LLM.** `GET .../finalize-draft` trả `suggestions`: nhận định/lời khuyên các phiên trước (Neo4j PJKG), bệnh ứng viên (`diseases_with_symptom`) và cờ đỏ (`red_flags_risk`) từ KG. Tên triệu chứng không khớp đồ thị thì bỏ qua (`translate=False`), nên triệu chứng tiếng Việt thường ít gợi ý. Lỗi graph không chặn đóng ca. Chỉ là gợi ý, không phải chẩn đoán.
- **Qdrant.** Collection đổi `derma_medical_cases` → `derma_finalize_reports`; collection cũ không tự xoá và collection mới trống cho tới khi chạy `make reindex-qdrant only=finalize-reports` (cần OpenRouter để embedding). Đến lúc đó tool `search_finalize_report*` của agent không tìm được ca nào.
- **Migration** `a7c1e9d4b302` dừng nếu có phiên nào đã có >1 báo cáo (trước khi thêm unique).
