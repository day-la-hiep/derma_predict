# [Lưu ý] Cuộc gọi thoại / video bác sĩ ↔ bệnh nhân

WebRTC P2P 1-1; `consultation_service` chỉ quản lý vòng đời cuộc gọi và relay signaling, không nhận media.
Code: `VideoCallService`, `VideoCallController`, `fe/features/video-call/`. Hướng mở rộng: [video-call](../pending/video-call.md).

## Quy tắc

- **Gắn kênh theo dõi, không còn phiên tư vấn.** `video_calls.conversation_id` trỏ kênh `doctor_followup`. Chỉ bác sĩ của kênh khởi tạo, chỉ khi kênh còn mở ([followup-channel](followup-channel.md)); bệnh nhân chủ kênh là bên nhận. Mỗi kênh tối đa 1 cuộc gọi chưa kết thúc.
- Trạng thái: `pending` (đổ chuông), `ongoing`, `ended`. Lý do kết thúc (`rejected`/`cancelled`/`missed`/`ended`) **không lưu cột**, chỉ nằm trong event `call.ended` và nội dung tin tóm tắt.
- Event cuộc gọi (`call.ringing|accepted|ended|signal`) đi qua kênh Redis riêng của từng tài khoản (`user:calls:{user_id}`) và SSE `GET /video-calls/stream`, không qua stream hội thoại. `signal` chỉ gửi tới bên kia và chỉ relay khi `ongoing`. Hai tin chat bắt đầu/kết thúc (`video_call`, sender doctor) vẫn đi qua stream vì là tin nhắn.
- ICE: `GET /video-calls/ice-config` trả STUN, kèm TURN khi cấu hình.

## Điểm cần lưu ý

- Hết giờ đổ chuông (30 giây) do **FE của bên gọi** tự gửi `end`; server không có timer. Bên gọi đóng tab giữa chừng thì cuộc gọi treo tới khi một bên kết thúc, chặn gọi mới trong kênh.
- Cuộc gọi của phiên tư vấn cũ giữ trong DB nhưng không thao tác được nữa (không gắn kênh mới).
- Không ghi hình, không lưu media. Chưa thử end-to-end trên trình duyệt với hai tài khoản.
