# Hợp đồng liên service (đặc tả cho phần Spring ⇄ Python)

Nguồn: code hiện tại của `archive/core/` (đóng băng). Hai phía Java/Python phải bám file này; đổi một phía thì sửa file này và phía kia cùng lúc.

Sinh lại file máy đọc được (chạy trong `archive/core/`):

```bash
PYTHONPATH=. .venv/bin/python ../contracts/export_contracts.py
```

| File | Nội dung |
|---|---|
| `openapi.core.json` | 68 route REST của `archive/core/`: route, JSON snake_case, envelope `ApiResponse` |
| `messages.schema.json` | JSON Schema cũ của `TurnRequest`, `TurnAttachment`, `AgentResponseMessage` (RabbitMQ của `archive/core/`), chỉ để đối chiếu |
| `README.md` | Phần còn lại: JWT, endpoint nội bộ, Redis (Stream/Pub-Sub), event SSE |

## 1. REST
- Giữ nguyên route, JSON snake_case, envelope `{"data": ...}`; lỗi `{"detail": "..."}` với mã 400/401/403/404/409/422 theo `errors.py` (`AppError` và con).
- Endpoint nội bộ `/internal/...` chỉ gọi giữa service, không qua gateway.
- Route của `archive/core/` thuộc service nào: bảng prefix trong plan, mục "Gateway + hạ tầng".

## 2. JWT
- HS256, khoá `JWT_SECRET_KEY` dùng chung; chỉ `identity` phát token, các service tự verify.
- Access (30 phút): `sub` (user id), `username`, `role` (`patient|doctor|admin`), `type="access"`, `iat`, `exp`.
- Refresh (30 ngày): `sub`, `jti`, `type="refresh"`, `iat`, `exp`; `jti` lưu Redis `auth:refresh:{user_id}:{jti}` để thu hồi/rotation (do `identity` quản lý).
- Mật khẩu bcrypt (`$2b$`), `BCryptPasswordEncoder` đọc được.
- Header: `Authorization: Bearer <access>`; dịch vụ kiểm `type == "access"`.

## 3. Lệnh nội bộ giữa service = REST `/internal/...` (đã duyệt, đề xuất A, D, F, H)
Không qua gateway; mọi lời gọi kèm header `X-Internal-Key` (cấu hình `INTERNAL_API_KEY`). Danh sách dự kiến, chốt chi tiết khi viết từng service:

| Service | Endpoint | Việc |
|---|---|---|
| ai | `POST /internal/turns` (202) | nhận `TurnRequest` (chỉ id + nội dung + file; **không** mang context), chạy nền |
| ai | `POST /internal/turns/{message_id}/cancel` | dừng lượt: `{cancelled: bool}` |
| identity | `GET /internal/patient-profiles/resolve?user_id=&profile_id=` | consultation xác định hồ sơ của tài khoản (bỏ `profile_id` = hồ sơ đầu tiên): `data: {id, user_id, full_name}`; 404 nếu không có/không phải của tài khoản |
| identity | `GET /internal/users/{id}` | tên và vai trò tài khoản: `data: {id, full_name, role}`; 404 nếu không có (consultation lấy tên bác sĩ cho kênh theo dõi) |
| identity | `GET /internal/patient-profiles?ids=a,b` | thông tin nhiều hồ sơ cùng lúc: `data: [{id, user_id, full_name, dob, gender, relationship, phone}]` (id không tồn tại thì bỏ qua) |
| consultation | `GET /internal/conversations/{id}` | agent lấy `{user_id, patient_profile_id, model}` của hội thoại (`model` là id ngắn như `gemma4-26b`); 404 khi không còn |
| consultation | `POST /internal/turns/{message_id}/result` | agent trả kết quả cuối: `conversation_id`, `content`, `status` (`done`\|`question`), `choice`, `reasoning` |
| consultation | `GET /internal/conversations/{id}/history` | agent kéo lịch sử tin: `data: [{sender, content, message_type}]`, cũ trước |
| clinical | `GET /internal/patients/{id}/context` | agent kéo `data: {facts: [{label, fact_type, detail, body_site}]}` (fact dài hạn + đợt đang hoạt động) |
| clinical | `POST /internal/episodes/apply-turn` | agent ghi kết quả lâm sàng của lượt: `{conversation_id, message_id, patient_profile_id, facts, hypotheses, image_predictions}` (dạng phần tử như `AgentResponseMessage` cũ) |
| consultation | `POST /internal/encounters/{id}/followup-channel` | clinical mở kênh chat theo dõi khi bắt đầu khám: body `{patient_profile_id, doctor_id}` → `data: {conversation_id}`; idempotent theo lần khám |
| consultation | `PUT /internal/encounters/{id}/followup-channel/until` | clinical đặt hạn kênh khi chốt kết luận: body `{followup_until}` (ISO, = chốt + `derma.followup-days`, mặc định 30 ngày) |
| clinical | `GET /internal/patients/long-term-facts?profile_ids=a,b` | identity lấy fact dài hạn (dị ứng/tiền sử/thuốc) để ghép vào hồ sơ: `data: {profileId: [{id, fact_type, label, detail, verified_at}]}` |
| clinical | `PUT /internal/patients/{id}/long-term-facts` | identity thay toàn bộ fact dài hạn: body `{facts: [{fact_type, label, detail}]}` → `data: [fact]` |
| clinical, consultation | `GET /internal/patients/{id}/has-data` | identity hỏi hồ sơ đã có báo cáo/hội thoại chưa trước khi xoá: `data: {has_data: bool}` |
| clinical | `GET /internal/finalize-reports?page=&page_size=` | knowledge đọc để reindex ca tham khảo; trả `data: [CaseInput]` |
| knowledge | `POST /internal/cases` | clinical gửi báo cáo vừa chốt (`CaseInput`: `report_id`, `patient_profile_id`, `doctor_id`, `encounter_id`/`consultation_session_id`, `diagnosis`, `notes`, `is_reference_case`, `created_at`, `snapshot{patient_profile, assessment, clinical_facts}`, `images[{file_id, storage_key, ...}]`) → index Qdrant ca + đồng bộ Neo4j PJKG |
| knowledge | `POST /internal/cases/reindex` | đọc `GET clinical /internal/finalize-reports?page=&page_size=50` (mỗi trang `data: [CaseInput]`), dựng lại Qdrant + đồ thị; trả `{indexed, failed[]}` |
| knowledge | `GET /internal/patients/{id}/history-hints` | nhận định + lời khuyên các phiên trước (clinical dùng cho form chốt báo cáo) |
| knowledge | `GET /internal/patients/{id}/journey-graph` | đồ thị hành trình bệnh nhân (clinical bọc thành route công khai cho FE) |
| knowledge | `POST /internal/search/semantic`, `/search/bm25` (`corpus` = `document` \| `finalize_report`), `/search/graph`, `/graph/document-query`, `/kg/intent`, `/kg/discriminating-questions` | retrieval cho agent; tìm ca tương tự = `/search/semantic` với `corpus=finalize_report` (không còn `/similar-cases`) |

- Ghi vào chủ dữ liệu: kết quả lâm sàng agent gọi **clinical** trước, rồi trả câu trả lời cho **consultation**; lỗi gọi clinical chỉ `logger.warning`, không làm mất câu trả lời.
- Hợp đồng cũ `agent_request_queue` / `agent_response_queue` / `finalize_report_finalized` **bỏ**. `AgentResponseMessage` cũ tách làm hai: phần cho consultation (nội dung, trạng thái, choice, reasoning) và phần cho clinical (facts, hypotheses, image_predictions, báo cáo). `messages.schema.json` sinh từ `archive/core/` vẫn là bản cũ, dùng để đối chiếu; schema mới định nghĩa trong từng service.
- RabbitMQ chỉ còn `document_ingest_queue`, nội bộ `knowledge` (Python ⇄ Python).
- "Hội thoại đang có lượt chạy" = tồn tại tin assistant `queued`/`question` trong DB (consultation trả 409 khi gửi thêm); không còn khoá Redis `active_turn`.
- Tên hiển thị (`doctor_name`, `patient_name`) lưu sẵn lúc ghi `Appointment`, `FinalizeReport`; không gọi identity mỗi lần liệt kê.

## 4. Redis (đã duyệt, đề xuất B)
| Loại | Tên | Ý nghĩa |
|---|---|---|
| **Stream** | `conversation:events:{conversation_id}` | mọi event của hội thoại (mục 5); `XADD` field `event` = JSON, SSE `XREAD` từ `Last-Event-ID` hoặc đầu lượt; `MAXLEN ~` + TTL |
| Pub/Sub | `user:calls:{user_id}` | sự kiện cuộc gọi của một tài khoản (tạm thời, mất cũng được) |
| Pub/Sub + Key | `document:ingest:cancel`, `document:ingest:cancel:{document_id}:{stage_id}` | dừng bước pipeline (nội bộ knowledge) |
| Key | `auth:refresh:{user_id}:{jti}` | refresh token còn hiệu lực (identity) |
| Sentinel | `[DONE]` | hết 1 lượt; client bỏ qua, không đóng kết nối |

Bỏ: `conversation:room:{id}` (thay bằng Stream), `agent:turn:cancel`, `agent:active_turn:*`, `agent:pending_turn:*` (không còn hoãn publish chờ SSE mở: Stream có replay).
Tên hằng số: `shared/derma_shared/constants.py` (bản sao của `archive/core/`, còn các tên cũ; dọn khi viết knowledge/agent).

## 5. Event trên room / call (JSON, `type` là khoá phân biệt)
Agent `XADD` vào Stream (kèm `conversation_id`, `message_id`):

| `type` | Trường thêm |
|---|---|
| `message.started` | `corr_id` |
| `message.delta` | `delta` |
| `message.thinking` | `content` |
| `message.tool_start` | `step_id`, `tool`, `input` |
| `message.tool_result` | `step_id`, `tool`, `input`, `content` |
| `message.question` | `choice` (`MessageChoice`) |
| `message.done` | `content` |

Consultation (`XADD` Stream cho `message.*`; Pub/Sub cho loại call):

| `type` | Kênh | Trường |
|---|---|---|
| `message.created` | stream | `message` (`MessageOutput`) |
| `message.done` | stream | `message_id`, `content=""` (tin bị chặn/đóng) |
| `call.ringing` | user calls | `mode`, `call` (`VideoCallOutput`) |
| `call.accepted` | user calls | `call` |
| `call.ended` | user calls | `reason`, `ended_by`, `call` |
| `call.signal` | user calls | `call_id`, `from`, `kind`, `payload` (WebRTC) |

FE phụ thuộc đúng các tên/khoá này: giữ nguyên.

## 6. Còn mở
- Quyền đọc bucket ảnh của clinical từ knowledge (index ca tham khảo cần ảnh): cùng MinIO, khác bucket; cấp quyền hoặc clinical gửi kèm `storage_key` và knowledge đọc bằng khoá MinIO chung.
- Schema chi tiết của `apply-turn`, `result`, `POST /internal/cases` chốt khi viết service tương ứng, rồi ghi lại vào đây.
- Event trong Stream: giữ nguyên tên và khoá ở mục 5; chỉ đổi kênh vận chuyển.

## 7. Kênh theo dõi sau khám (public, qua gateway → consultation)
Kênh = hội thoại `kind=doctor_followup` gắn một lần khám; AI không trả lời. Tin nhắn dùng lại `/conversations/{id}/messages` (GET/POST) và `/conversations/{id}/stream`; gửi sau `followup_until` → 409.

| Endpoint | Việc |
|---|---|
| `GET /api/v1/followup-channels/by-encounter/{encounter_id}` | bệnh nhân chủ kênh hoặc bác sĩ của kênh: `{conversation_id, encounter_id, status: open\|read_only, followup_until, doctor_id, doctor_name, ...}`; 404 nếu chưa có kênh |
| `GET /api/v1/doctor/followup-channels` | kênh của bác sĩ, thêm `patient_profile_id`, `patient_name`, `last_message_at`, `preview` |
| `POST /api/v1/doctor/followup-channels/{conversation_id}/extend` | body `{days}` (1..90, mặc định 30) gia hạn từ `followup_until`; chỉ khi còn mở và đã có hạn |
| `POST /api/v1/conversations/{id}/video-calls` | gọi video: chỉ bác sĩ của kênh, chỉ khi kênh còn mở (các route `/video-calls/*` giữ nguyên) |

Đã bỏ: `request-consultation`, `/doctor/consultations/*`, `/doctor/consultations/{id}/finalize*`, `consultation_report`. `openapi.core.json` và `messages.schema.json` sinh từ `archive/core/` (đóng băng) nên vẫn còn các đường dẫn cũ; không sửa tay.
