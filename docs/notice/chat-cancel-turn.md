# Dừng trả lời của chatbot

- FE bấm nút Dừng (thay nút Gửi lúc đang trả lời) → `POST /conversations/{id}/cancel` → Core publish `agent:turn:cancel` → Agent Worker huỷ task của turn, đóng turn bằng `message.done` kèm phần đã stream.
- Turn chưa tới worker (đang chờ mở SSE) được Core tự đóng với nội dung rỗng.
- Lưu ý: huỷ giữa lúc LangGraph đang chạy tool có thể để checkpoint thiếu `ToolMessage` cho tool call dở; chưa xử lý, nếu lượt sau lỗi thì cần vá ở đây.
- Turn đang xếp hàng sau lock của cùng hội thoại (hiếm) không bị dừng.
