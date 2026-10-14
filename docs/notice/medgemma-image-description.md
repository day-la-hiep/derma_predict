# [Lưu ý] Tool mô tả ảnh bằng MedGemma

Tool `analyze_skin_image_multimodal` (`core/agent/tools/skin_image_multimodal.py`, client ở
`core/agent/common/medgemma.py`) cho agent "nhìn" ảnh qua MedGemma trên Vertex AI và bổ sung mô tả cho kết quả
CNN `classify_skin_image`. Tool mô tả chung ở [chat.md](../module/chat.md).

## Quy tắc

| Điểm | Hành vi |
|---|---|
| Bật/tắt | `MEDGEMMA_ENABLED` (mặc định `false`). Tắt thì tool không có trong `ALL_TOOLS`, agent chạy CNN-only như cũ |
| Dữ liệu gửi đi | Ảnh bệnh nhân (đã thu về JPEG ≤1024px) được gửi sang Google khi bật. Chưa có bước xin đồng ý riêng |
| Vai trò kết quả | Mô tả + giả thuyết, **không phải bằng chứng lâm sàng và không phải chẩn đoán**. `evidence.py` chỉ tính `source="book"`/web nên kết quả này không được tính |
| Lỗi | API lỗi/timeout/chưa cấu hình → tool trả chuỗi lỗi mềm, agent vẫn dùng kết quả CNN |
| Xác thực | ADC (`GOOGLE_APPLICATION_CREDENTIALS`), không đặt key trong repo |

## Điểm cần lưu ý

- **Flow đưa kết quả sang `hybrid_retrieval` chưa cố định.** Prompt chỉ bảo agent coi đây là mô tả bổ sung cho CNN,
  khác nhau thì nêu bất định. Hướng chốt sau: xem [multimodal-before-cnn.md](../pending/multimodal-before-cnn.md).
- Chưa kiểm chứng trên endpoint thật: client mới được thử với transport giả. Cần project, location, endpoint ID
  của MedGemma đã deploy lên Vertex AI Model Garden.
- Prompt hệ thống của agent là chuỗi tĩnh nên nhắc tool theo kiểu "nếu có"; không tách prompt theo cờ.
- Thêm một lần gọi mạng cho mỗi lượt có ảnh nên lượt chậm hơn.
