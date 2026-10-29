# [Lưu ý] Route của chat bệnh nhân

URL quyết định hội thoại đang mở, nên tải lại trang hay mở link vẫn đúng đoạn chat.

| Đường dẫn | Ý nghĩa |
|---|---|
| `/chats/<id>` | một hội thoại, độc lập với hồ sơ trên URL; hồ sơ đang chọn tự đổi theo hồ sơ của hội thoại đó |
| `/chats/new/<profileId>` | hội thoại mới của hồ sơ đó (chưa có record, tạo khi gửi tin đầu tiên rồi thay bằng `/chats/<id>`) |
| `/chats/new` | thiếu hồ sơ: tự thêm hồ sơ đang chọn thành `/chats/new/<profileId>` |
| `/profile` | màn quản lý hồ sơ (không nằm dưới `/chats`) |
| `/chats` | cổng vào: tới đoạn chat đã nhớ của hồ sơ đang chọn, không có thì `/chats/new/<profileId>` |

Đổi hồ sơ trong sidebar luôn mở `/chats/new/<hồ sơ mới>`.

## Điểm cần lưu ý

- **Nhớ theo trình duyệt, không theo tài khoản.** Đoạn chat gần nhất của từng hồ sơ và hồ sơ đang chọn lưu trong localStorage
  (`derma-active-profile`). Id hồ sơ riêng của từng tài khoản nên không lẫn giữa tài khoản, nhưng đổi trình duyệt là mất.
- **`ChatPage` nằm ở `app/(patient)/layout.tsx`.** Đặt trong page `[[...slug]]` thì Next dựng lại component mỗi lần đổi đường
  dẫn, khiến effect "store → URL" chạy lúc mount và kéo URL về hội thoại cũ. Nhóm `(patient)` không xuất hiện trên URL.
- **Id hội thoại không tồn tại** (bị xoá, hoặc của tài khoản khác) hoặc **hồ sơ không còn** thì quay về `/chats` để chọn lại.
- Luồng "gửi tin đầu tiên ở `/chats/new/<hồ sơ>` rồi chuyển sang `/chats/<id>`" chưa kiểm thử trên trình duyệt (cần agent worker chạy).
