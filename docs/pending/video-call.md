# [Pending] Gọi thoại / video giữa bác sĩ và bệnh nhân

> **Trạng thái:** giai đoạn 1–4 đã cài (xem [notice](../notice/video-call.md)); chọn phương án không đổi schema (giữ 3 trạng thái, bác sĩ khởi tạo).
> Còn lại: kiểm thử trình duyệt thật, TURN khác mạng, hết giờ phía server, thông báo cuộc gọi đến ngoài hội thoại đang mở.

## Hiện trạng

- Chưa có code cuộc gọi nào. Chỉ có schema: bảng `video_calls` (`pending → ongoing → ended`, `room_id`),
  `messages.message_type = 'video_call'` và `messages.video_call_id`. Chưa có API, chưa có màn hình.
- Hạ tầng có thể tái dùng: room SSE `/conversations/{id}/stream` (Redis Pub/Sub, đã kiểm quyền qua
  `ConsultationService.room_access`).
- Thoại và video dùng chung một stack WebRTC; "nâng cấp thoại → video" là thêm video track rồi renegotiate.

## Lý thuyết cần nắm

1. Media capture: `getUserMedia`, `MediaStream`/`MediaStreamTrack`, `enumerateDevices`, constraints; `track.enabled` để tắt/bật mic/cam.
2. `RTCPeerConnection`: gửi track P2P giữa hai trình duyệt.
3. Signaling (WebRTC không quy định): SDP offer/answer, ICE candidate, tín hiệu ring/accept/reject/hangup.
4. NAT traversal: ICE (host/srflx/relay), STUN (lấy IP public), TURN (relay khi P2P không thông; ~10–20% cuộc gọi cần).
5. Bảo mật transport: SRTP + DTLS có sẵn; `getUserMedia` đòi HTTPS (trừ `localhost`).
6. Codec: Opus (audio); VP8/VP9/H.264/AV1 (video), Safari ưu tiên H.264; thương lượng qua SDP.
7. Chất lượng mạng: congestion control (GCC), `getStats()` (bitrate, packet loss, RTT).
8. Renegotiation / perfect negotiation: xử lý glare (`polite`/`impolite`, `makingOffer`, `ignoreOffer`). Phần khó nhất.
9. Mở rộng (chỉ để bảo vệ): mesh vs SFU vs MCU, simulcast/SVC.
10. Debug: `chrome://webrtc-internals`, `about:webrtc`, Trickle ICE test.

## So sánh công nghệ

### Kiến trúc media

| | P2P mesh (WebRTC thuần) | SFU (LiveKit/mediasoup/Janus) | MCU | Managed (Twilio/Agora/Daily) |
|---|---|---|---|---|
| Cách chạy | Hai client nối thẳng | Client gửi lên server, server chuyển tiếp | Server trộn thành 1 luồng | Mua SDK |
| Phù hợp | 1-1, tối đa 3-4 người | Nhóm, ghi hình, hội chẩn | Thiết bị yếu | Cần ra nhanh |
| Chi phí hạ tầng | Gần 0, chỉ cần TURN | Server băng thông lớn | Rất tốn CPU | Trả theo phút |
| Dữ liệu y tế | Không qua bên thứ ba (TURN vẫn mã hóa) | Qua server của mình | Server giải mã | Rời hệ thống |

Kết luận: bác sĩ ↔ bệnh nhân 1-1 → P2P + coturn. SFU chỉ khi có hội chẩn nhiều bác sĩ, ghi hình, hoặc AI xử lý stream.

### Thư viện client

| Lựa chọn | Đánh giá |
|---|---|
| WebRTC API thuần | **Chọn.** ~200 dòng, hiểu sâu, không dependency |
| simple-peer | Ít bảo trì, che mất cơ chế |
| PeerJS | Giấu lý thuyết; server công cộng không hợp dữ liệu y tế |
| LiveKit client SDK | Mạnh nhưng phải dựng LiveKit server; dành cho phương án nâng cấp |
| Jitsi (iframe) | Không tùy biến được; chỉ làm fallback |

### Kênh signaling

| Lựa chọn | Đánh giá |
|---|---|
| REST POST + SSE hiện có | **Chọn.** Tái dùng room + kiểm quyền; thêm event `call.*` và `POST .../signal` |
| WebSocket | Hai chiều thật nhưng phải làm auth/reconnect riêng; chỉ khi SSE bộc lộ giới hạn |
| Socket.IO | Thêm dependency và server riêng; không cần |

### STUN/TURN

| Lựa chọn | Đánh giá |
|---|---|
| coturn tự host (thêm vào `docker-compose.yml`) | **Chọn.** Time-limited credential (HMAC) do Core cấp |
| STUN công cộng của Google | Chỉ dev, không có relay |
| Twilio/Metered TURN | Dễ nhưng tốn tiền, phụ thuộc ngoài; dự phòng khi không có IP public |

## Luồng đề xuất

### Giai đoạn 0 — Chốt thiết kế (cần duyệt trước khi code)
- Mở rộng trạng thái `video_calls`: thêm `ringing`, `rejected`, `missed`; hoặc giữ nguyên và thêm cột `mode` (`audio`|`video`).
  Đụng `dto/base` → hỏi duyệt; migration phải giữ dữ liệu, đọc lại file sinh ra.
- Ai gọi ai: đề xuất bác sĩ của phiên `active` khởi tạo, bệnh nhân nhận; tái dùng `room_access`.

### Giai đoạn 1 — Hạ tầng
- Thêm `coturn` vào `docker-compose.yml` (`use-auth-secret`, dải cổng UDP relay).
- Biến `TURN_URL`, `TURN_SECRET` trong settings (không commit secret).
- Dev chạy HTTPS (`next dev --experimental-https`) hoặc dùng `localhost` cho cả hai tab.

### Giai đoạn 2 — Backend (Core)
- `POST /video-calls` tạo cuộc gọi (ringing), ghi tin `message_type=video_call`, publish `call.ringing`.
- `POST /video-calls/{id}/accept|reject|end` chuyển trạng thái, ghi `started_at`/`ended_at`.
- `POST /video-calls/{id}/signal` `{type: offer|answer|candidate, payload}` relay qua Redis tới room; kiểm người gửi thuộc cuộc gọi.
- `GET /video-calls/ice-config` trả STUN/TURN + credential hết hạn ~1 giờ.
- Timeout ~30 giây không bắt máy → `missed`. Chỉ Core ghi Postgres.

### Giai đoạn 3 — Frontend
- Hook `useCall`: state machine `idle → ringing → connecting → connected → ended` + `RTCPeerConnection` + `getUserMedia`.
- Đăng ký event `call.*` vào SSE listener hiện có (skill `derma-fe-conventions`).
- UI: popup cuộc gọi đến, cửa sổ gọi (video chính + video của mình nhỏ), nút mic/cam/kết thúc, chỉ báo mạng.
- Xử lý: từ chối quyền cam/mic, không có thiết bị, đóng tab giữa chừng (`beforeunload` gọi `end`).

### Giai đoạn 4 — Nâng cấp thoại → video
- Bắt đầu audio-only; bấm "Bật camera" → `addTrack` → renegotiate theo perfect negotiation.
- Phần dễ lỗi nhất, dành thời gian test kỹ.

### Giai đoạn 5 — Kiểm thử
- Hai trình duyệt / hai tài khoản (bệnh nhân + bác sĩ) cùng máy.
- Hai máy khác mạng, ép `iceTransportPolicy: "relay"` để kiểm coturn.
- Chrome ↔ Firefox ↔ Safari/iOS (autoplay, H.264).
- Mạng yếu (DevTools throttling).
- Unit test state machine và API backend (không cần service thật).

### Giai đoạn 6 — Tài liệu
- `docs/notice/video-call.md`: quy tắc ai được gọi, TURN credential, không ghi hình.
- Cập nhật `docs/module/` và `docs/overview/db-tables.md` theo schema mới.
- Ghi mục "Hạn chế" cho báo cáo.

## Rủi ro / hạn chế (ghi vào báo cáo)

- Không có TURN thì ~1/5 cuộc gọi không nối được (mạng di động, firewall).
- coturn cần IP public + dải UDP mở, khó demo qua mạng trường → chuẩn bị TURN thương mại hoặc demo trong LAN.
- Chưa ghi hình/lưu cuộc gọi (có chủ ý); nếu làm sau này cần SFU và consent.
- Khu admin chưa kiểm JWT phía server; với call **phải** kiểm quyền tham gia, nếu không ai biết `call_id` cũng gửi được signal.
- Video chỉ hỗ trợ tư vấn, không thay khám trực tiếp.

## Câu hỏi cần chốt

- Mở rộng trạng thái hay thêm cột `mode`?
- Ai được khởi tạo cuộc gọi (chỉ bác sĩ, hay cả bệnh nhân)?
- Demo ở đâu (LAN hay khác mạng) → quyết định coturn tự host hay TURN thương mại.

## Phụ thuộc

- `consultation_sessions` / `ConsultationService.room_access` (đã có).
- Room SSE + Redis Pub/Sub (đã có).
- Bảng `video_calls` + `messages.video_call_id` (đã có schema, chưa có API).
