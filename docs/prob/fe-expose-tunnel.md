# [Prob] FE chỉ đăng nhập / realtime được trên máy chạy server khi expose qua tunnel

## Hiện tượng
FE chạy trên laptop (`pnpm dev`, cổng 3010), expose ra ngoài bằng tunnel (`derma.day-la-hiep.site`):

- Trang `/_next/static/*` trả 403, websocket HMR (`/_next/hmr`) lỗi.
- Đăng nhập chỉ được trên chính laptop đó, máy khác / điện thoại không đăng nhập được.
- SSE chat chỉ realtime trên máy local, điện thoại không realtime.

## Nguyên nhân và cách khắc phục

### 1. 403 chunk và HMR lỗi
- **Vì sao:** `allowedDevOrigins` trong `fe/next.config.ts` chỉ có `ai-legal.day-la-hiep.site`. Next 16 ở chế độ dev chặn origin lạ truy cập `/_next/*`.
- **Sửa:** đổi thành `["*.day-la-hiep.site"]`. Domain khác thì thêm vào danh sách. Cần restart `pnpm dev`.

### 2. Đăng nhập chỉ được trên laptop
- **Vì sao:** `fe/.env.local` đặt `NEXT_PUBLIC_API_URL=http://localhost:3050/api/v1`. `services/client.ts` và `services/sse.ts` dùng biến này làm base URL, và `NEXT_PUBLIC_*` bị nhúng vào bundle trình duyệt. `localhost:3050` trên điện thoại / máy khác là chính máy đó, không phải Core.
- **Sửa:** `NEXT_PUBLIC_API_URL=/api/v1` (cả `.env.local` và `.env.local.example`). Trình duyệt gọi vào chính domain FE, rewrite trong `next.config.ts` forward `/api/v1/*` sang `BACKEND_URL` (mặc định `http://localhost:3050`) ở phía server. Chỉ cần expose FE, Core không cần mở ra ngoài.
- **Lưu ý:** `NEXT_PUBLIC_API_URL` được nhúng lúc khởi động nên phải restart `pnpm dev`. Token đăng nhập nằm trong `localStorage` theo từng origin, mỗi domain / địa chỉ phải đăng nhập riêng. Sau khi đổi, trình duyệt có thể còn cache bundle cũ: hard reload hoặc xoá site data.

### 3. SSE không realtime qua tunnel (chưa kiểm chứng)
- **Nghi vấn:** khi proxy qua rewrite, Next mặc định nén gzip response nên các event bị gom lại. Core trả `Cache-Control: no-cache` + `X-Accel-Buffering: no` nhưng không có `no-transform` (`core/app/api/conversation_api.py`, `doctor_api.py`).
- **Đã sửa:** `compress: false` trong `fe/next.config.ts`. Cần restart `pnpm dev`.
- **Nếu vẫn không realtime:** thêm `no-transform` vào `Cache-Control` của hai endpoint SSE ở Core; kiểm tra tunnel (cloudflared / Cloudflare) có buffer `text/event-stream` không.
- **Chưa làm:** chưa gửi tin nhắn chat thật qua domain để xác nhận, vì chưa có tài khoản test.

## Cách kiểm tra nhanh
```bash
curl -s https://<domain>/api/v1/health        # phải 200 qua tunnel
```
Trong trình duyệt: DevTools → Network (bật Preserve log), request `auth/login` phải đi tới `https://<domain>/api/v1/auth/login`, không còn `localhost:3050`.

## Điều kiện để chạy
Laptop vẫn phải chạy FE (:3010), Core (:3050) và tunnel trỏ vào `localhost:3010`.
