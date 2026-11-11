---
name: derma-fe-conventions
description: Conventions for the Derma `fe/` frontend (Next.js App Router) — folder layout (`app/` vs `features/` vs `services/` vs `components/ui/`), the two state patterns in use (Zustand store for chat/SSE, TanStack Query hooks for the admin document-ingest pipeline), and the step-by-step way to add a page, a feature, a UI primitive, an SSE event type, or an admin-pipeline endpoint. Use whenever the user asks to add or modify a component, page, store, API call, hook, or SSE event in `fe/`, asks where frontend code should live, or how data flows from a Next.js page down to the backend — even if they don't say "convention".
---

# Derma `fe/` — layout and conventions

Paths are relative to `fe/`. To run/drive/screenshot the app, use `/run-fe`. Two unrelated
features live side by side with **different state patterns** — pick the one that matches
what you're touching, don't mix them.

`fe/CLAUDE.md` is stale (references `@tanstack/react-query` as if unused everywhere, `quill`/
`html-to-docx`/`mammoth` deps that aren't in `package.json`, and an old flat `services/`-only
structure) — trust this skill and the code over it.

## Layout

| Path | Owns | Must not |
|---|---|---|
| `app/` | Next.js App Router routes only (`page.tsx` = thin, imports a feature component) | hold business logic or API calls |
| `app/providers.tsx` | app-wide providers: `QueryClientProvider` (TanStack Query cho mọi trang; khu bác sĩ/quản trị còn client riêng trong `components/layout/app-shell.tsx`), `ThemeProvider`, `TooltipProvider`, `AccessGate`, `Toaster` | |
| `app/access-gate.tsx` | login gate: redirects to the area's login page (`features/auth` `LoginPage` → `AuthScreen`) until a JWT is stored (see Gotchas) | |
| `components/ui/` | shadcn primitives (`components.json`: style `new-york`, baseColor `neutral`) — generated/edited via shadcn conventions | hold feature-specific logic |
| `features/<name>/` | one folder per feature: `types.ts`, `api.ts` (axios calls + `unwrap`), `hooks.ts` (TanStack Query) or `store.ts` (Zustand), `constants.ts`, `components/` | import another feature's internals directly (go through its exported hooks/store) |
| `services/` | cross-feature infra: `client.ts` (axios singleton + auth interceptor), `endpoints.ts` (chat REST paths), `chat.sse.ts` (SSE client, implements `ChatService`), `apiAdapters.ts` (wire ↔ domain mapping), `index.ts` (mock/real `ChatService` factory), `mock/` | be feature-specific business logic |
| `hooks/` | generic cross-feature hooks (e.g. `use-mobile.ts`) | feature-specific hooks (those go in `features/<name>/hooks.ts`) |
| `lib/utils.ts` | `cn()` (clsx+tailwind-merge), `formatRelativeTime`, `formatBytes` | |
| `types/` | ambient `.d.ts` for untyped packages (e.g. `html-to-docx.d.ts`) | domain types (those go in `features/<name>/types.ts`) |

Path alias: `@/*` → repo root (`fe/`), e.g. `@/components/ui/button`, `@/features/chat/store`.

## Two state patterns — pick per feature

**Chat (`features/chat/`)** — one large Zustand store (`store.ts`, ~800 lines, not split into
slices) that calls `chatService` (`services/index.ts`, swaps between `chatSse` and
`mockChatService` on `NEXT_PUBLIC_USE_MOCK`) directly from store actions, and subscribes to SSE
via `chatService.onEvent()`. No TanStack Query here — the store *is* the cache, because SSE
pushes deltas that must mutate specific message/reasoning-step objects in place, which doesn't
fit a query-invalidation model. Components read via `useChatStore()` selectors.

**Admin / document-ingest (`features/document-pipeline/`)** — plain REST + TanStack Query. `api.ts`
exports one object (`documentApi`) of axios calls, each piped through `unwrap<T>()` (backend wraps
every response in `{ data: T }` — `ApiResponse[T]` on the Python side, see
`derma-core-conventions`). `hooks.ts` wraps each call in `useQuery`/`useMutation`, centralizes
query keys (`qk`), and polls (`refetchInterval`) while a pipeline stage is `running` instead of
needing a push channel. `useRefreshDocument` is the one place that invalidates — call it from every
mutation's `onSuccess`, don't invalidate ad hoc in components.

**Patient profile (`features/patient-profile/`)** — same TanStack pattern (`profileApi` + `hooks.ts` with `qk`), plus a tiny
persisted Zustand store for the UI choice `activeProfileId`; `features/chat/store.ts` reads it via `getActiveProfileId()`
when creating a conversation (`patient_profile_id` in the body).

**Rule of thumb:** server pushes deltas you must splice into existing state in real time → a
Zustand store like chat's. Everything else (CRUD + polling) → TanStack Query hooks like
document-pipeline's.

## The chat SSE flow (frontend side)

```
store.sendMessage() → chatService.sendMessage() [services/chat.sse.ts]
  1. POST /conversations/{id}/messages → gets real userMessage + assistantMessage (status=queued) ids
  2. fires chatService._openStream() in the background (not awaited) → GET .../stream (SSE)
     → parses `data: <json>\n\n` frames → ChatStreamEvent → impl.listeners (store subscribed via onEvent)
store's onEvent handler switches on event.type (message.delta / reasoning.step_* / message.question /
  message.tool_result / message.done / document.*) and mutates messagesByConversation[conversationId] in place
```

Backend side of this flow (RabbitMQ/worker/Redis) is documented in `derma-core-conventions`; the
event `type` strings and payload shapes are the contract between the two — change
`features/chat/types.ts`'s `FlatStreamEvent` and the backend's `emit()` calls together. Note:
the **mock** service (`services/mock/mockChatService.ts`) does not emit every event the real one
does (e.g. no `message.tool_result`, uses `reasoning.step_completed` + `choice` instead of the
real `message.question`) — a UI change that only works against the mock will break against the
real backend; verify against both, or at least check `NEXT_PUBLIC_USE_MOCK=false` before calling
a chat UI change done (see `/run-fe`).

## Recipes

**Add a page/route** — folder+`page.tsx` under `app/` (App Router); keep it thin, just import
and render a component from the matching `features/<name>/components/`. `"use client"` at the
top of the feature component if it uses hooks/state (App Router defaults to server components).

**Add a feature** — new `features/<name>/` with `types.ts` (domain types), `api.ts` (axios calls
via `@/services/client`'s `api`, each response piped through an `unwrap<T>` like
`toc-pipeline/api.ts`'s), `hooks.ts` (TanStack Query wrapping `api.ts`) or `store.ts` (Zustand,
if it needs push-driven state), `components/` for its UI. Don't reach into another feature's
`store.ts`/`api.ts` internals from outside — export what's needed from `hooks.ts`/`store.ts`.

**Add a UI primitive** — shadcn convention: lives in `components/ui/`, styled with Tailwind
classes composed via `cn()` from `@/lib/utils`, variants via `class-variance-authority` (see
`components/ui/button.tsx` for the pattern). Icons from `lucide-react` (`components.json`
`iconLibrary`).

**Add a new SSE event type** — add the variant to `FlatStreamEvent` in `features/chat/types.ts`
(payload shape must match what the backend's `emit()` sends, see `derma-core-conventions`'s "Add
middleware"), handle it in the store's event switch (`features/chat/store.ts`), and update
`services/mock/mockChatService.ts` if the mock should simulate it too (chat UI dev often happens
against the mock first).

**Add an admin-pipeline endpoint** (`features/document-pipeline/`) — add the call to `documentApi` in
`api.ts` (through `unwrap<T>`), add a `useQuery`/`useMutation` wrapper in `hooks.ts` (mutations
call `useRefreshDocument(documentId)` in `onSuccess`, `toast.error(errorMessage(e))` in `onError`), use
the hook from a component in `components/`.

## Đặt tên label & nút (tối giản)

Giao diện chỉ giữ **tên gọi ngắn**; hướng dẫn đầy đủ đặt vào hover (`components/ui/hint.tsx` → `<Hint content=...>`).

- **Nút / tab / chip lọc**: 1–2 từ, động từ hoặc danh từ chính ("Xác nhận", "Huỷ lịch", "Gửi", "Chờ"). Không lặp danh từ
  đã rõ theo ngữ cảnh ("Huỷ lịch khám" → "Huỷ lịch" khi đang ở màn lịch khám).
- **Tiêu đề mục**: ≤ 3 từ ("Lịch khám", "Báo cáo", "Dữ kiện"). Không kèm dòng phụ giải thích cố định bên dưới.
- **Trạng thái**: chấm màu + 1 từ ("Chờ", "Đang", "Xong"); nghĩa đầy đủ nằm trong hint.
- **Placeholder**: ≤ 4 từ. Phím tắt, ràng buộc, hậu quả của hành động → hint của nút, không viết thành đoạn chữ nhỏ phía dưới.
- **Hint** là câu đầy đủ, nói *việc này làm gì / hậu quả*, tối đa 2 câu. Nút chỉ có icon bắt buộc có `aria-label`
  (cùng nội dung ngắn) và `Hint`.
- Mọi thứ chỉ có trong hint thì phải là thông tin phụ; thông tin quyết định (tên bệnh nhân, trạng thái, hành động
  chính) luôn hiển thị. Cảnh báo "không phải chẩn đoán y khoa" của kết quả AI giữ nhãn ngắn ("gợi ý") hiển thị sẵn,
  câu đầy đủ trong hint.
- Cấu hình nhãn dùng chung đặt trong `constants.ts` của feature với cặp `label` (ngắn) + `hint` (đầy đủ);
  xem `features/doctor/constants.ts`.

## Code style

- Path alias `@/*`, never deep relative imports (`../../../`) across feature boundaries.
- Comments are Vietnamese, explain *why* (a backend contract detail, a UI/race-condition
  reason), not what — match the surrounding file; see `services/chat.sse.ts` and
  `features/document-pipeline/api.ts` for the density expected. No long block comments at the top
  of a file or above a function/component (no JSDoc essays); one short line at most.
- `pnpm lint` (ESLint) should be clean of errors (pre-existing `no-unused-vars` warnings in
  `services/mock/mockChatService.ts` for intentionally-unused mock params are known-acceptable).
- Error messages shown to users go through a `errorMessage(e)`-style helper that prefers the
  backend's FastAPI `detail` field (see `features/document-pipeline/api.ts`) — don't show raw axios
  errors.

## Gotchas

- Chat có route theo hội thoại (`features/chat/routes.ts`): `/chats/<id>` (hội thoại độc lập, hồ sơ lấy từ chính hội thoại),
  `/chats/new/<profileId>` (hội thoại mới luôn kèm hồ sơ), `/profile` (màn hồ sơ, không nằm dưới `/chats`); `/chats` chỉ là cổng
  vào, tự chuyển tới đoạn chat đã nhớ của hồ sơ đang chọn (`lastConversationByProfile` trong `features/patient-profile/store.ts`).
  `ChatPage` vẽ ở `app/(patient)/layout.tsx` (các page trả `null`) vì page dưới catch-all bị Next dựng lại mỗi lần đổi đường dẫn.
  URL là nguồn quyết định hội thoại đang mở; `store.init()` không tự chọn nữa.
- Khu bác sĩ: một trang `/doctor` (bảng "Ca khám", `features/appointments/components/DoctorCasesPage.tsx`) trong khung sidebar trái; mỗi dòng ghép
  lịch hẹn + báo cáo kết luận + kênh theo dõi theo `encounter_id`. Click một lần mở modal tóm tắt (`CaseSummaryDialog`, có nút "Xem chi tiết"), nhấp đúp mở màn chi tiết `/doctor/cases/<appointmentId>` (`AppointmentDetailPage`); trên dòng chỉ có thao tác nhanh theo trạng thái, hồ sơ và kênh chat (khung trượt). Kênh chat
  bác sĩ–bệnh nhân chỉ có sau khám và gắn với `encounter`; không còn luồng "yêu cầu tư vấn" từ chat AI.
- `NEXT_PUBLIC_USE_MOCK=true` makes the whole chat UI work from `localStorage` with zero backend
  calls — great for isolated UI work, but don't trust it to validate an integration change (see
  `/run-fe`).
- Auth is JWT login/register (`features/auth`, backend `/auth/*`): `app/access-gate.tsx` redirects to the area's own login page (`/login`, `/doctor/login`, `/admin/login`, with `?next=` for same-area paths; a logged-in user on a login page is sent to `next` or the area home) until `services/client.ts` has a token for the current **area**, which it attaches as `Authorization: Bearer` (interceptor clears it on 401). Sessions are stored per area (`derma-auth-{patient|doctor|admin}-{access-token|refresh-token|user}`; area = path: `/admin`, `/doctor`, else patient), so login/logout in one area never touches the others; a login whose role belongs to another area is saved there and the gate redirects to that area's home. Register is only offered on `/login`. Login pages live outside the shells via route groups (`app/doctor/(portal)`, `app/admin/(portal)`; `app/login`), so the doctor/admin layouts do not wrap them. Logout goes straight to the area's login page. Old shared `derma-auth-*` keys are migrated into the right area on first read. The server only issues tokens; chat/document routes do not require one yet. Conversations use the logged-in account's id (`getCurrentUserId()` in `services/client.ts`) as `user_id`; logout reloads the page so the chat store never leaks one account's data to the next.
- `services/chat.sse.ts` uses raw `fetch` + manual SSE frame parsing (`\n\n`-delimited `data:`
  lines), not `EventSource` — because it needs to send a custom `Authorization` header, which
  `EventSource` can't do.
- Binary downloads (page images, chunk export) go through axios with `responseType: "blob"` and
  `timeout: 0` (see `features/document-pipeline/api.ts`'s `pageImageUrl`/`exportChunks`) because they
  need the `Authorization` header too — a plain `<img src="...">`/`<a href="...">` can't attach it.
