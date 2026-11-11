# [Lưu ý] Kiến trúc microservice trong gốc repo (`<tên>_service/`)

Code mới nằm ở gốc repo (`<tên>_service/`); `archive/core/` (monolith cũ) đóng băng và vẫn giữ cổng 3050 tới khi nghiệm thu. Gateway chạy cổng 3040.
Hợp đồng liên service: `contracts/README.md`. Quy ước làm việc: skill `derma-microservice-migration`.

| Service | Công nghệ | Cổng | Sở hữu |
|---|---|---|---|
| gateway | Spring Cloud Gateway | 3040 | chỉ định tuyến theo đường dẫn, không verify JWT |
| identity | Spring Boot | 3051 | tài khoản, bác sĩ, hồ sơ bệnh nhân, token |
| consultation | Spring Boot | 3052 | hội thoại, tin nhắn, phiên tư vấn, cuộc gọi video, báo cáo tiền tư vấn |
| clinical | Spring Boot | 3053 | đợt bệnh, fact, giả thuyết, lịch hẹn, lần khám, báo cáo kết luận |
| knowledge | Python/FastAPI | 3054 | pipeline sách, Qdrant, Neo4j, tìm kiếm cho agent |
| ai | Python/LangGraph | 3055 | agent, nhận lượt qua REST `/internal/turns` |

## Điểm dễ hiểu nhầm

- **Id mềm, không FK chéo service.** `patient_profile_id`, `doctor_id`, `message_id`... chỉ là chuỗi. Xoá/đổi ở service này
  không tự lan sang service kia; identity hỏi `has-data` của consultation và clinical trước khi cho xoá hồ sơ.
- **Không có transaction phân tán, không outbox.** Chốt báo cáo kết luận lưu ở clinical trước, rồi mới gọi knowledge (`POST /internal/cases`)
  và consultation (đặt hạn kênh theo dõi). Gọi knowledge hoặc consultation lỗi chỉ ghi log, không rollback báo cáo; ca thiếu trong Qdrant được bù bằng
  `POST /internal/cases/reindex`.
- **Route `/patient-profiles/{id}/episodes|finalize-reports` thuộc clinical**, phần còn lại của `/patient-profiles` thuộc identity; `/doctor/encounters/**` thuộc clinical còn `/doctor/followup-channels/**` thuộc consultation. Gateway xếp route clinical trước.
- **Ảnh đính kèm báo cáo:** field `file_id` của form chốt nay là `storage_key` của ảnh. Clinical chỉ nhận ảnh nằm trong tin nguồn của fact hoặc
  ảnh đã phân loại của đợt bệnh; khoá lạ bị bỏ (có `warning`).
- **SSE chat** đi bằng Redis Stream `conversation:events:{id}` (replay 30 giây); FE gửi `Last-Event-ID` khi nối lại. Pub/Sub chỉ còn cho `user:calls:{id}`.
- **Java gọi Python phải ép HTTP/1.1** (`Http11`), nếu không JDK nâng lên h2c và uvicorn mất body POST.
- **Gateway dùng Spring Boot 4.0.6** (Spring Cloud 2025.1 chưa hỗ trợ 4.1); các service Spring còn lại dùng 4.1.2.
- **DB:** một Postgres, năm database (`make services-db`); dữ liệu cũ trong `derma_hospital_db` không bị đụng, và chưa có script chuyển dữ liệu
  cũ sang database mới (chỉ knowledge cần copy bảng sách/đồ thị bằng `pg_dump`).

## Chưa làm / chưa kiểm

- Đã chạy thật (2026-11-10) identity, consultation, clinical, gateway trên Postgres + Redis thật, qua gateway: đăng ký/đăng nhập, chat + SSE, xin tư vấn → nhận → chốt, đặt lịch → khám → chốt; khi ai/knowledge tắt thì hệ thống báo lỗi nhẹ nhàng (câu trả lời xin lỗi, gợi ý đồ thị bị bỏ).
- Đã chạy thật (2026-11-10) luồng chat với ai + knowledge + LLM (OpenRouter): FE/gateway → consultation → ai → (tool tìm kiếm qua knowledge, đồ thị Neo4j) → SSE trả lời, fact và giả thuyết ghi vào clinical (`apply-turn`); hỏi tiếp lượt hai cũng chạy. `.env` của ai/knowledge (`<tên>_service//.env`, đã gitignore) chép từ `archive/core/.env`, không chép cấu hình LangSmith.
- Đã kiểm thêm (2026-11-10): upload ảnh lên MinIO thật, CNN phân loại ảnh (Actinic_Keratosis 0.93) → clinical lưu vào đợt bệnh → bác sĩ thấy ảnh + dự đoán trên FE; bác sĩ xác nhận → bắt đầu khám → chốt kết luận trên FE (form có gợi ý đồ thị từ knowledge), ca được nạp vào knowledge; admin xem danh sách sách, pipeline, ảnh trang, quan hệ đồ thị.
- Dữ liệu sách đã copy từ `derma_hospital_db` sang database `knowledge` (files 8, documents 4, document_stages 24, document_overrides 3; checksum khớp); DB cũ không bị đụng.
- Ảnh chỉ gắn vào đợt khi xác định được duy nhất (giả thuyết trùng nhãn CNN top-1, hoặc hội thoại chỉ chạm một vùng); hội thoại nhiều đợt mà không khớp thì bỏ ảnh và ghi `warn` ở clinical (hành vi kế thừa từ `archive/core/`).
- Model mô tả ảnh (`AGENT_VISION_MODEL`, medgemma local qua Ollama) không chạy trên máy này nên bước mô tả ảnh báo lỗi kết nối rồi bỏ qua; CNN vẫn chạy.
- Chưa kiểm `interrupt()` resume bằng câu hỏi chọn (`message.question`), cuộc gọi video.
- Provider LLM đôi lúc trả 429; agent tự chuyển sang graph tiền chẩn đoán, không làm hỏng lượt.
- Lỗi có sẵn từ `archive/core/` (kg_templates.py dòng 124, chữ rác chèn vào Cypher của intent `diseases_with_symptom`): đã sửa trong `knowledge_service`, `archive/core/` giữ nguyên.
- Knowledge DB mới còn trống (chưa copy bảng sách từ `derma_hospital_db`); Qdrant/Neo4j dùng dữ liệu hiện có.
- Chưa kiểm upload ảnh thật lên MinIO từ consultation.
- Gateway chưa test với SSE thật (SCG không buffer mặc định).
