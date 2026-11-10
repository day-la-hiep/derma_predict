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
| identity | `GET /internal/users/{id}` | tên và vai trò tài khoản: `data: {id, full_name, role}`; 404 nếu không có (consultation lưu sẵn tên bác sĩ khi nhận ca) |
| identity | `GET /internal/patient-profiles?ids=a,b` | thông tin nhiều hồ sơ cùng lúc: `data: [{id, user_id, full_name, dob, gender, relationship, phone}]` (id không tồn tại thì bỏ qua) |
| consultation | `GET /internal/conversations/{id}` | agent lấy `{user_id, patient_profile_id, model}` của hội thoại (`model` là id ngắn như `gemma4-26b`); 404 khi không còn |
| consultation | `POST /internal/turns/{message_id}/result` | agent trả kết quả cuối: `conversation_id`, `content`, `status` (`done`\|`question`), `choice`, `reasoning` |
| consultation | `GET /internal/conversations/{id}/history` | agent kéo lịch sử tin: `data: [{sender, content, message_type}]`, cũ trước |
| consultation | `GET /internal/sessions/{id}` | clinical kiểm quyền chốt báo cáo: `data: {id, conversation_id, patient_profile_id, doctor_id, doctor_name, status}`; 404 nếu không có |
| consultation | `POST /internal/sessions/{id}/finalized` | clinical báo đã chốt báo cáo → đóng phiên (thay `announce_finalized`) |
| clinical | `GET /internal/patients/{id}/context` | agent kéo `data: {facts: [{label, fact_type, detail, body_site}]}` (fact dài hạn + đợt đang hoạt động) |
| consultation | `GET /internal/patients/{id}/latest-report?exclude_session_id=` | agent kéo `data: {summary: str\|null}`: báo cáo tiền tư vấn gần nhất của hồ sơ, trừ phiên đang sinh báo cáo |
| clinical | `POST /internal/episodes/apply-turn` | agent ghi kết quả lâm sàng của lượt: `{conversation_id, message_id, patient_profile_id, facts, hypotheses, image_predictions}` (dạng phần tử như `AgentResponseMessage` cũ) |
| consultation | `POST /internal/sessions/{id}/report` | agent ghi báo cáo tiền tư vấn (consultation sở hữu bảng `pre_consultation_reports` và báo cho bác sĩ/bệnh nhân): `{report_summary, status: ready\|failed}` (fact đã ghi sau mỗi lượt chat nên không còn `facts`/`provenance_pairs`) |
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
- Tên hiển thị (`doctor_name`, `patient_name`) lưu sẵn lúc ghi `ConsultationSession`, `Appointment`, `FinalizeReport`; không gọi identity mỗi lần liệt kê.

## 4. Redis (đã duyệt, đề xuất B)
| Loại | Tên | Ý nghĩa |
|---|---|---|
| **Stream** | `conversation:events:{conversation_id}` | mọi event của hội thoại (mục 5); `XADD` field `event` = JSON, SSE `XREAD` từ `Last-Event-ID` hoặc đầu lượt; `MAXLEN ~` + TTL |
| Pub/Sub | `user:calls:{user_id}` | sự kiện cuộc gọi của một tài khoản (tạm thời, mất cũng được) |
| Pub/Sub | `doctor:inbox` | danh sách ca của bác sĩ (tạm thời) |
| Pub/Sub + Key | `document:ingest:cancel`, `document:ingest:cancel:{document_id}:{stage_id}` | dừng bước pipeline (nội bộ knowledge) |
| Key | `auth:refresh:{user_id}:{jti}` | refresh token còn hiệu lực (identity) |
| Sentinel | `[DONE]` | hết 1 lượt; client bỏ qua, không đóng kết nối |

Bỏ: `conversation:room:{id}` (thay bằng Stream), `agent:turn:cancel`, `agent:active_turn:*`, `agent:pending_turn:*` (không còn hoãn publish chờ SSE mở: Stream có replay).
Tên hằng số: `shared/derma_shared/constants.py` (bản sao của `archive/core/`, còn các tên cũ; dọn khi viết knowledge/agent).

## 5. Event trên room / inbox / call (JSON, `type` là khoá phân biệt)
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

Consultation (`XADD` Stream cho `message.*`, `consultation.updated` loại room; Pub/Sub cho loại inbox/call):

| `type` | Kênh | Trường |
|---|---|---|
| `message.created` | stream | `message` (`MessageOutput`) |
| `message.done` | stream | `message_id`, `content=""` (tin bị chặn/đóng) |
| `consultation.updated` | stream | `session_id`, `status`, `doctor_id` |
| `consultation.updated` | inbox | `session` (`ConsultationSessionOutput`) |
| `call.ringing` | user calls | `mode`, `call` (`VideoCallOutput`) |
| `call.accepted` | user calls | `call` |
| `call.ended` | user calls | `reason`, `ended_by`, `call` |
| `call.signal` | user calls | `call_id`, `from`, `kind`, `payload` (WebRTC) |

FE phụ thuộc đúng các tên/khoá này: giữ nguyên.

## 6. Còn mở
- Quyền đọc bucket ảnh của clinical từ knowledge (index ca tham khảo cần ảnh): cùng MinIO, khác bucket; cấp quyền hoặc clinical gửi kèm `storage_key` và knowledge đọc bằng khoá MinIO chung.
- Schema chi tiết của `apply-turn`, `result`, `POST /internal/cases` chốt khi viết service tương ứng, rồi ghi lại vào đây.
- Event trong Stream: giữ nguyên tên và khoá ở mục 5; chỉ đổi kênh vận chuyển.
