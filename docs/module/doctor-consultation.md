# Module Tư vấn với bác sĩ

Từ một hội thoại với trợ lý AI, bệnh nhân có thể xin bác sĩ tư vấn. Bác sĩ nhận ca, đọc báo cáo tóm tắt do AI sinh sẵn, nhắn tin trực tiếp
trong cùng hội thoại, gọi thoại / video (WebRTC), xem hồ sơ + đồ thị hành trình bệnh nhân, rồi chốt **báo cáo kết luận** để đóng ca.

> Kết quả AI (báo cáo tóm tắt, gợi ý từ đồ thị) chỉ là tham khảo cho bác sĩ, **không phải chẩn đoán y khoa**.

## 1. Code nằm ở đâu

| Lớp | File |
|---|---|
| FE | `fe/app/doctor/page.tsx` (ca tư vấn), `fe/app/doctor/records/page.tsx` (lịch sử khám); `fe/features/doctor/` (`DoctorConsultationPage`, `SessionList`, `ChatViewer`, `ReportPanel`, `AiSummaryView`, `ClinicalFactList`, `FinalizeConsultationDialog`, `FinalizeReportForm`, `PatientInfoCard`, `PatientJourneyCanvas`...); phía bệnh nhân `fe/features/chat/components/RequestConsultationDialog.tsx`, `ConsultationDivider.tsx`; gọi video `fe/features/video-call/` |
| API | `core/app/api/doctor_api.py` (ca tư vấn, báo cáo kết luận, đồ thị hành trình, `request-consultation`), `video_call_api.py`, `conversation_api.py` (room SSE) |
| Service | `consultation_service.py` (vòng đời phiên, quyền xem room, tin của bác sĩ), `finalize_report_service.py` + `finalize_report_index_service.py` (chốt báo cáo, nạp Qdrant), `video_call_service.py`, `patient_graph_service.py` (đồ thị hành trình), `room_events.py` (Pub/Sub room / inbox / cuộc gọi) |
| Repository / Model | `consultation_repository.py`, `finalize_report_repository.py`, `video_call_repository.py`; `models/consultation_session.py`, `finalize_report.py`, `video_call.py`, `clinical.py` |
| Worker | `core/agent/handler/consultation_report.py` (sinh báo cáo tiền tư vấn), `core/agent/common/fact_extractor.py` (trích dữ kiện) |

Phân quyền: các endpoint bác sĩ dùng `require_role("doctor")` (`app/api/deps.py`); bệnh nhân dùng JWT thường và chỉ thao tác trên hội thoại của mình.

## 2. Vòng đời phiên tư vấn

```
bệnh nhân bấm "Yêu cầu bác sĩ"
        │ POST /conversations/{id}/request-consultation
        ▼
   pending ──bác sĩ nhận ca / gửi tin đầu──▶ active ──đóng ca / chốt báo cáo──▶ resolved
     │  AI vẫn trả lời bệnh nhân              │  AI dừng, chỉ người ↔ người
     └─ Worker sinh báo cáo tiền tư vấn       └─ có thể gọi video
```

- Mỗi hội thoại tối đa **một phiên đang mở** (chỉ mục unique trên `consultation_sessions`); xin lần nữa khi đang mở thì trả lại phiên cũ. Một hội thoại có thể có nhiều phiên nối tiếp.
- Mỗi chuyển trạng thái ghi một **tin mốc** vào hội thoại (`consultation_requested` / `consultation_accepted` / `consultation_resolved`); FE dựng đường kẻ phân cách từ các tin này.
- **Bác sĩ gửi tin khi ca còn `pending` cũng là nhận ca** (service tự `accept` rồi ghi tin; UI báo trước ở nút gửi). Ca `resolved` thì gửi tin trả 409.
- Ca đang do bác sĩ khác phụ trách → 403 (`_owned_session`). Chỉ đóng được ca `active`.
- Khi ca `active`, `POST /conversations/{id}/messages` của bệnh nhân chỉ ghi tin và phát `message.created`, **không** tạo turn agent; ca `pending` thì AI vẫn trả lời (xem [chat.md](chat.md)).

### Báo cáo tiền tư vấn (AI)
Lúc tạo phiên, Core publish `TurnRequest(type="consultation_report")` lên `agent_request_queue`. Agent Worker đọc hội thoại, tóm tắt và trích **dữ kiện lâm sàng**
(triệu chứng, thời gian, vị trí, tiền sử, thuốc, dị ứng...) kèm tin nhắn nguồn, rồi trả qua `agent_response_queue`; Core lưu vào `pre_consultation_reports`,
`clinical_facts`, `clinical_provenances` (`save_generated_report`). Bác sĩ thấy báo cáo xuất hiện sau khi Worker xong (tạo phiên không phải chờ).

## 3. API

Base `/api/v1`, response bọc `{"data": ...}`. Mọi endpoint cần JWT.

| Method | Path | Ai | Việc |
|---|---|---|---|
| POST | `/conversations/{id}/request-consultation` | bệnh nhân | tạo phiên `pending` + tin mốc, publish sinh báo cáo |
| GET | `/doctor/consultations` | bác sĩ | danh sách ca (hàng đợi `pending` + ca của mình) |
| GET | `/doctor/consultations/stream` | bác sĩ | SSE inbox: ca mới / đổi trạng thái (`consultation.updated`) |
| GET | `/doctor/consultations/{sid}` | bác sĩ | chi tiết ca: bệnh nhân, báo cáo AI, dữ kiện |
| POST | `/doctor/consultations/{sid}/accept` | bác sĩ | nhận ca |
| POST | `/doctor/consultations/{sid}/reply` | bác sĩ | gửi tin vào hội thoại (nhận ca nếu còn `pending`) |
| POST | `/doctor/consultations/{sid}/resolve` | bác sĩ | đóng ca không kèm báo cáo |
| GET | `/doctor/consultations/{sid}/finalize-draft` | bác sĩ | form báo cáo kết luận điền sẵn + gợi ý từ đồ thị |
| POST | `/doctor/consultations/{sid}/finalize` | bác sĩ | chốt báo cáo kết luận và đóng ca (201) |
| GET | `/doctor/consultations/{sid}/finalize-reports` | bác sĩ | lịch sử báo cáo kết luận của bệnh nhân thuộc ca |
| GET | `/doctor/finalize-reports` | bác sĩ | báo cáo do mình chốt (màn Lịch sử khám) |
| GET | `/doctor/patient-profiles/{pid}/finalize-reports` | bác sĩ | báo cáo của một hồ sơ bệnh nhân |
| GET | `/doctor/patient-profiles/{pid}/journey-graph` | bác sĩ | đồ thị hành trình bệnh nhân (còn alias `/doctor/patients/{pid}/journey-graph`) |
| GET | `/conversations/{id}/messages`, `/conversations/{id}/stream` | chủ hội thoại, bác sĩ liên quan | tin nhắn và SSE room (xem mục 4) |
| GET | `/patient-profiles/{id}/finalize-reports` | bệnh nhân | xem báo cáo kết luận của hồ sơ (chỉ đọc) |
| GET | `/video-calls/stream`, `/video-calls/ice-config` | cả hai | SSE cuộc gọi của tài khoản; cấu hình STUN / TURN |
| POST | `/conversations/{id}/video-calls` | bác sĩ | gọi bệnh nhân (ca phải `active`) |
| POST | `/video-calls/{cid}/accept`, `/end`, `/signal` | cả hai | bắt máy, kết thúc, relay signaling WebRTC |

## 4. Realtime và phạm vi xem

Ba bên (bệnh nhân, bác sĩ, agent) chung một **room** SSE của hội thoại (`conversation:room:{id}`). Ngoài event của agent còn có `message.created` (tin của bệnh nhân /
bác sĩ đã ghi DB) và `consultation.updated` (`session_id`, `status`, `doctor_id`). Danh sách ca của bác sĩ nghe thêm kênh `doctor:inbox`. Pub/Sub không replay nên FE
refetch `GET /messages` mỗi khi nối lại.

Bác sĩ chỉ xem hội thoại **từ đầu tới hết phiên gần nhất của mình** (`ConsultationService.room_access`): ca `pending` ai cũng đọc được để quyết định nhận; ca đã `resolved`
thì cắt tại tin mốc kết thúc và stream bị từ chối; bác sĩ không liên quan → 403. Bảng quy tắc và các ngoại lệ: [doctor-chat-access](../notice/doctor-chat-access.md).

## 5. Gọi thoại / video

WebRTC P2P 1-1; Core chỉ quản lý vòng đời cuộc gọi và relay signaling, không nhận media.

- Chỉ **bác sĩ phụ trách** khởi tạo, khi phiên `active`; bệnh nhân là bên nhận. Mỗi phiên tối đa một cuộc gọi chưa kết thúc. Trạng thái: `pending` (đổ chuông) → `ongoing` → `ended`.
- Event cuộc gọi đi qua kênh Redis riêng của từng tài khoản (`user:calls:{user_id}`) và SSE global `GET /video-calls/stream`, không qua room hội thoại.
- Chat chỉ ghi hai tin hệ thống `video_call` (bắt đầu / kết thúc kèm thời lượng, hoặc lý do nhỡ / từ chối / huỷ).
- Hai bên khác mạng cần TURN: `TURN_URL`, `TURN_SECRET` (coturn trong `docker-compose.yml`) hoặc TURN ngoài `METERED_TURN_*`; trình duyệt cần HTTPS (trừ `localhost`) mới cho dùng camera / mic.
- Chi tiết quy tắc, giới hạn: [video-call](../notice/video-call.md).

## 6. Báo cáo kết luận và đồ thị hành trình

**Báo cáo kết luận** (`finalize_reports`) do bác sĩ chốt khi đóng ca: một báo cáo / phiên, không sửa sau khi chốt. Form được điền sẵn (`finalize-draft`) từ dữ kiện đang hiệu lực
kèm nguồn, kèm gợi ý không dùng LLM: nhận định / lời khuyên các phiên trước, bệnh ứng viên và cờ đỏ từ đồ thị. Báo cáo lưu **snapshot** dữ kiện + tin / ảnh nguồn và có thể gắn ảnh bệnh
(`patient_images`, nhãn xác nhận `confirmed_label` cho CNN). Chốt xong:

1. đóng phiên và ghi tin mốc `consultation_resolved`, phát `consultation.updated`;
2. nạp báo cáo (kèm ảnh) vào Qdrant `derma_finalize_reports` để agent tra ca tương tự (`search_finalize_report*`); lỗi nạp chỉ ghi warning, bù bằng `make reindex-qdrant only=finalize-reports`;
3. đồng bộ vào **đồ thị hành trình bệnh nhân** trên Neo4j ([patient-journey-graph](patient-journey-graph.md)); đồ thị cũng được cập nhật khi báo cáo tiền tư vấn được sinh.

Bệnh nhân xem được báo cáo kết luận của từng hồ sơ ở tab "Báo cáo kết luận" (chỉ đọc). Chi tiết lưu ý: [finalize-report](../notice/finalize-report.md).

## 7. Hạn chế / đơn giản hoá có chủ ý

- Chưa kiểm thử end-to-end trên trình duyệt với hai tài khoản (bệnh nhân + bác sĩ); video call chưa thử trên Safari / iOS.
- Dữ kiện lâm sàng và báo cáo AI lấy theo bệnh nhân (mọi lần khám), chưa cắt theo phiên nên bác sĩ có thể thấy dữ kiện sinh ra sau khi phiên của mình kết thúc.
- Pub/Sub không replay: event rớt lúc SSE đứt thì mất; cuộc gọi có thể kẹt "Đang kết nối…". Hết giờ đổ chuông (30 giây) do FE bên gọi gửi `end`, Core không có timer.
- Không ghi âm / ghi hình, chưa có thông báo đẩy khi đóng tab. Không có đặt lịch khám.
- Một hội thoại chỉ có một phiên mở; bác sĩ khác không thể tiếp quản ca đã `active`.
