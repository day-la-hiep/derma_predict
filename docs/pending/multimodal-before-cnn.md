# [Pending] Mở rộng tool multimodal (MedGemma): bước trước CNN, fuse, đối chiếu sách

Chưa làm, không phải cam kết. Hiện `analyze_skin_image_multimodal` chỉ là tool bổ sung mô tả bên cạnh CNN
(xem [medgemma-image-description.md](../notice/medgemma-image-description.md)). Tài liệu này ghi các hướng mở rộng
đã tính tới khi tách client `describe_skin_image` (`core/agent/common/vision.py`) khỏi tool.

## 1. Việc chưa làm

| # | Việc | Vì sao | Gợi ý cách làm |
|---|---|---|---|
| 1 | **Chạy MedGemma trước CNN** | Biết ảnh có phải da, có nhiều tổn thương, chất lượng ảnh ra sao trước khi phân loại | Gọi lại `describe_skin_image` (`core/agent/common/vision.py`) từ một bước nội bộ (không qua LLM), kết quả cache trên `AgentContext`; CNN đọc từ đó |
| 2 | **Cho MedGemma trả dữ liệu có cấu trúc** | Hiện chỉ là text tự do nên máy không dùng lại được | Yêu cầu JSON (hình thái, vị trí, giả thuyết, độ chắc chắn) rồi validate bằng pydantic |
| 3 | **Fuse CNN + MedGemma** | Hai nguồn đang để agent tự cân nhắc | Quy tắc gộp rõ, kèm cờ "bất đồng"; chỉ làm khi đã có số đo |
| 4 | **Đưa giả thuyết MedGemma vào `hybrid_retrieval`** | Chưa chốt có kiểm chứng giả thuyết bằng sách hay không, và truy vấn thế nào | Dùng tên bệnh nêu ở giả thuyết làm truy vấn; hoặc chỉ khi bất đồng với CNN |
| 5 | **Xin đồng ý trước khi gửi ảnh sang Google** | Ảnh y tế rời hệ thống | Cờ trên hồ sơ người dùng, hiển thị ở FE trước khi upload |
| 6 | **Đánh giá** | Chưa biết MedGemma có làm kết quả tốt hơn CNN-only không | Bộ ảnh có nhãn + so sánh top-1 và độ bất đồng; xem `core/agent/test/` |

## 2. Ràng buộc cần giữ

- Kết quả multimodal chỉ là gợi ý, không phải bằng chứng lâm sàng, luôn ghi rõ không phải chẩn đoán.
- Lỗi model multimodal không được làm hỏng turn: agent phải còn chạy được bằng CNN.
- Nếu chạy trước CNN thì đây là bước nội bộ, không để LLM chép lại `object_key` thêm một lần.
- Ý tưởng cắt vùng tổn thương nằm riêng ở [lesion-roi-crop.md](lesion-roi-crop.md).
