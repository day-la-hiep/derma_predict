# Derma Hospital — Frontend (`fe/`)

Next.js (App Router) + TypeScript. Gọi Core ở `NEXT_PUBLIC_API_URL` (mặc định `http://localhost:3050/api/v1`).

## Chạy

```bash
cp .env.local.example .env.local   # NEXT_PUBLIC_USE_MOCK=false để gọi Core thật
pnpm install
pnpm dev                           # http://localhost:3010 (hoặc `make frontend` ở gốc repo)
pnpm exec tsc --noEmit && pnpm lint
```

## Route

| Route | Việc | Dữ liệu |
|---|---|---|
| `/chats` | chat với trợ lý AI, hồ sơ bệnh nhân, xin tư vấn bác sĩ, gọi video | Zustand store + SSE (`features/chat/`, `features/video-call/`) |
| `/doctor` | bác sĩ: hàng đợi ca tư vấn, chat, báo cáo AI, chốt báo cáo kết luận | `features/doctor/` |
| `/doctor/records` | lịch sử khám (báo cáo kết luận) | `features/doctor/` |
| `/doctor/documents`, `/doctor/documents/[documentId]` | admin: pipeline số hoá sách (cần Ingest Worker) | TanStack Query, poll (`features/document-pipeline/`) |
| `/doctor/graph-schema` | admin: loại thực thể và quan hệ của đồ thị sách | `features/graph-schema/` |

Đăng nhập: `features/auth/`, token gắn `Authorization: Bearer` ở `services/client.ts`; `app/access-gate.tsx` chặn khi chưa đăng nhập.

## Tài liệu

- [docs/backend-contract.md](docs/backend-contract.md) — hợp đồng REST + SSE với Core.
- [docs/FRONTEND_LOGIC_SPECIFICATION.md](docs/FRONTEND_LOGIC_SPECIFICATION.md) — logic FE.
- Quy ước thư mục / state: skill `derma-fe-conventions` (`../.claude/skills/derma-fe-conventions/SKILL.md`).
