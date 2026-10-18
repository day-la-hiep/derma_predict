# [Lưu ý] Tool mô tả ảnh bằng model multimodal (MedGemma)

Tool `analyze_skin_image_multimodal` (`core/agent/tools/skin_image_multimodal.py`, hàm gọi model ở
`core/agent/common/vision.py`) cho agent "nhìn" ảnh qua một model multimodal và bổ sung mô tả cho kết quả CNN
`classify_skin_image`. Tool mô tả chung ở [chat.md](../module/chat.md).

## Cấu hình model theo role

Mọi model đều là chuỗi `provider:model`, đi qua cùng `agent/common/llm.py::get_model`:

| Role | Biến `.env` | Ghi chú |
|---|---|---|
| Luồng chính | `AGENT_MODEL` (+ `AGENT_MODEL_CHOICES` chọn theo hội thoại) | |
| Triage nhẹ | `AGENT_TRIAGE_MODEL` | Trống = dùng model của hội thoại |
| Mô tả ảnh | `AGENT_VISION_MODEL` | Trống = tool tắt, agent chạy CNN-only |

Provider: `openrouter` (OpenRouter), `openai` (OpenAI trực tiếp), `google_genai` (Gemini), `deepseek`,
`local` (Ollama/vLLM qua OpenAI-compatible, trỏ bằng `LOCAL_LLM_BASE_URL`). Lưu ý `openai:` không còn là OpenRouter. Ví dụ `AGENT_VISION_MODEL=local:medgemma:4b`.
Trong CLI test (`agent.test.cli`), `/set triage_model` và `/set vision_model` đổi từng role để thử.

## Quy tắc

| Điểm | Hành vi |
|---|---|
| Bật/tắt | `AGENT_VISION_MODEL` rỗng thì tool không có trong graph. Tool được đăng ký lúc dựng graph nên đổi giá trị cần khởi động lại worker (CLI: hội thoại mới) |
| Dữ liệu gửi đi | Ảnh (đã thu về JPEG ≤1024px) gửi tới provider của model; `local` thì không rời máy. Chưa có bước xin đồng ý riêng khi dùng provider đám mây |
| Vai trò kết quả | Mô tả + giả thuyết, **không phải bằng chứng lâm sàng và không phải chẩn đoán**. `evidence.py` chỉ tính `source="book"`/web nên kết quả này không được tính |
| Lỗi | Provider lỗi/timeout → tool trả chuỗi lỗi mềm, agent vẫn dùng kết quả CNN |

## Điểm cần lưu ý

- **Flow đưa kết quả sang `hybrid_retrieval` chưa cố định.** Prompt chỉ bảo agent coi đây là mô tả bổ sung cho CNN,
  khác nhau thì nêu bất định. Hướng chốt sau: xem [multimodal-before-cnn.md](../pending/multimodal-before-cnn.md).
- Model phải **nhận ảnh**. `AGENT_VISION_MODEL` trỏ vào model chỉ có text sẽ báo lỗi mềm ở mỗi lượt có ảnh.
- Ollama trên GPU nhỏ (4 GB) chạy một phần trên CPU nên lượt đầu sau khi nghỉ chậm; `LOCAL_LLM_TIMEOUT` mặc định 300 giây.
- MedGemma trên Vertex AI (endpoint Model Garden) **không còn được hỗ trợ trực tiếp** trong code; muốn dùng thì
  cần provider mới hoặc đặt sau một server tương thích OpenAI và dùng `local`.
- Prompt hệ thống của agent là chuỗi tĩnh nên nhắc tool theo kiểu "nếu có"; không tách prompt theo cờ.
