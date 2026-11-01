# [Lưu ý] Cuộc gọi thoại / video bác sĩ ↔ bệnh nhân

WebRTC P2P 1-1; Core chỉ quản lý vòng đời cuộc gọi và relay signaling, không nhận media. Code: `core/app/services/video_call_service.py`,
`core/app/api/video_call_api.py`, `fe/features/video-call/`. Kế hoạch gốc và hướng mở rộng: [video-call](../pending/video-call.md).

## Quy tắc

- **Chỉ bác sĩ phụ trách khởi tạo**, khi phiên tư vấn `active`; bệnh nhân (chủ hội thoại) là bên nhận. Mỗi phiên tối đa 1 cuộc gọi chưa kết thúc.
- Trạng thái dùng nguyên schema cũ: `pending` = đang đổ chuông, `ongoing`, `ended`. Lý do kết thúc (`rejected`/`cancelled`/`missed`/`ended`)
  **không lưu cột**, chỉ nằm trong event `call.ended` và nội dung tin tóm tắt.
- Event cuộc gọi (`call.ringing|accepted|ended|signal`) **không đi qua room hội thoại** mà qua kênh Redis riêng của từng tài khoản (`user:calls:{user_id}`)
  và một SSE global `GET /video-calls/stream` do `CallLayer` mở sau đăng nhập. `signal` chỉ gửi tới bên kia; chỉ relay khi `ongoing`. Hai tin chat
  bắt đầu/kết thúc vẫn đi qua room vì là tin nhắn.
- Chat chỉ ghi **hai tin hệ thống** `video_call` (sender doctor): "Cuộc gọi bắt đầu" khi bệnh nhân bắt máy và "Cuộc gọi kết thúc · mm:ss" khi kết thúc.
  Cuộc gọi không được bắt máy chỉ có tin kết thúc ("Cuộc gọi nhỡ", "Bệnh nhân đã từ chối cuộc gọi", "Bác sĩ đã huỷ cuộc gọi"). Tin không bao giờ bị sửa lại.
  Nút Chấp nhận/Từ chối/Huỷ nằm ở thẻ đổ chuông nhỏ không chắn trang (`CallOverlay`); tin chat chỉ là dòng trạng thái, không có nút.
- Thoại → video: bật camera trong cuộc gọi sẽ đàm phán lại (perfect negotiation, bên nhận là `polite`). `mode` chỉ để UI bên nhận biết, không lưu DB.

## Điểm cần lưu ý

- **TURN ngoài (Metered Open Relay)**: đặt `METERED_TURN_USERNAME` / `METERED_TURN_CREDENTIAL` trong `core/.env` (credential tĩnh, gitignore, không đưa vào
  `.env.example`); Core trả kèm cho FE qua `GET /video-calls/ice-config`. Hạn mức miễn phí có giới hạn (~20 GB/tháng, kiểm tra lại ở metered.ca). Credential
  tĩnh do FE nhận được nên ai đăng nhập đều thấy — chấp nhận cho đồ án, nên đổi (rotate) trên dashboard nếu lộ.
- **Cần TURN khi hai bên khác mạng.** Mặc định chỉ STUN (đủ cho cùng LAN/localhost). Bật `coturn` trong `docker-compose.yml`, đặt `TURN_URL`
  trỏ IP/domain public và `--external-ip` cho coturn; credential do Core cấp theo HMAC, hết hạn sau `TURN_CREDENTIAL_TTL_SECONDS`.
- **Cần HTTPS** (trừ `localhost`) thì trình duyệt mới cho `getUserMedia`.
- Bên nhận thấy cuộc gọi đến ở mọi trang miễn là tab đang mở và đã đăng nhập (SSE global). Chưa có thông báo đẩy khi đóng tab.
- Redis Pub/Sub **không replay**: event rơi vào lúc SSE đang đứt sẽ mất và cuộc gọi có thể kẹt "Đang kết nối…". Chưa có `GET /video-calls/active` để đồng bộ
  lại khi nối lại. Mở nhiều tab cùng tài khoản thì mỗi tab đều nhận và đổ chuông.
- Hết giờ đổ chuông (30 giây) do **FE của bên gọi** tự gửi `end`; Core không có timer. Bên gọi đóng tab giữa chừng thì cuộc gọi `pending`/`ongoing`
  treo cho tới khi một bên bấm kết thúc, và chặn gọi mới trong phiên đó.
- Không ghi hình, không lưu media. Chưa kiểm thử end-to-end trên trình duyệt với hai tài khoản và nhiều trình duyệt (Safari/iOS).
