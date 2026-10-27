# Module Chat tư vấn da liễu

Bệnh nhân chat với trợ lý AI (có thể kèm ảnh da). Agent suy luận nhiều bước, gọi tool tra guideline,
knowledge graph, phân loại ảnh; thiếu thông tin thì hỏi lại; câu trả lời được stream realtime.

> Kết quả AI **không phải chẩn đoán y khoa**; guideline đang chờ bác sĩ duyệt.

## 1. Code nằm ở đâu

| Lớp | File |
|---|---|
| FE | `fe/app/chats/page.tsx`, `fe/features/chat/` (`store.ts` Zustand + xử lý SSE, `components/`), `fe/services/apiAdapters.ts` |
| API | `core/app/api/conversation_api.py`, `core/app/api/upload_api.py` |
| Service | `core/app/services/conversation_service.py`, `message_service.py` |
| Repository / Model | `conversation_repository.py`, `message_repository.py`, `file_repository.py`; `models/conversation.py`, `message.py`, `file.py` |
| Worker | `core/agent/worker.py` (vòng đời, khoá theo hội thoại), `turn.py` (chạy 1 turn), `publisher.py`, `core/app/workers/agent_response_consumer.py` (chạy trong Core) |
| Agent | `core/agent/graph/` (`chat_graph.py` lọc intent → `graph/v1/pre_diagnosis_graph.py` tiền chẩn đoán (v1; v2 ở `graph/v2/`, chọn bằng `AGENT_GRAPH_VERSION`)), `tools/`, `middleware/`, `prompt/` |

## 2. API

Base `/api/v1`, response bọc `{"data": ...}`.

| Method | Path | Việc |
|---|---|---|
| GET | `/models` | danh sách model cho người dùng chọn (`AGENT_MODEL_CHOICES`) |
| GET | `/conversations?user_id=` | danh sách hội thoại của user |
| POST | `/conversations` | tạo hội thoại + tin đầu tiên (cần user đã có hồ sơ bệnh nhân) |
| PATCH | `/conversations/{id}/model` | đổi model, áp dụng từ turn kế tiếp |
| GET | `/conversations/{id}/messages` | lịch sử tin nhắn (kể cả assistant đang `question`) |
| POST | `/conversations/{id}/messages` | gửi tin, mở turn mới (202); hội thoại còn turn đang chạy / chờ trả lời → 409 |
| POST | `/conversations/{id}/questions/{question_id}/answer` | trả lời câu hỏi agent đang chờ (202) |
| GET | `/conversations/{id}/stream` | SSE dài hạn của "room" hội thoại (bệnh nhân, bác sĩ, agent) — forward nguyên văn event từ Redis, có heartbeat; chỉ chủ hội thoại hoặc bác sĩ liên quan được nghe |
| GET | `/doctor/consultations/stream` | SSE cho bác sĩ: ca tư vấn mới / đổi trạng thái (`consultation.updated`) |
| POST | `/uploads` | upload ảnh đính kèm → MinIO + bảng `files` |

## 3. Luồng một turn

```
FE                     Core                          Redis / RabbitMQ                 Agent Worker
│ GET /stream ─────▶ subscribe conversation:room:{conv}   (room, mở 1 lần khi vào hội thoại, không đóng ở [DONE])
│ POST /messages ──▶ lưu user msg (done)
│                    + assistant msg (queued)
│                    lưu TurnRequest vào key ──▶ agent:pending_turn:{conv}
│                    commit; room đã có người nghe → GETDEL pending_turn ─▶ agent_request_queue ─▶ consume, lock theo conv
│ ◀── 202 {user, assistant id}                                                  chạy agent_graph.astream()
│ ◀══ SSE event ══ forward nguyên văn ◀──────── conversation:room:{conv} ◀────────── message.* events
│                                                                               turn xong / hỏi lại
│                    response_consumer upsert ◀─ agent_response_queue ◀──────── AgentResponseMessage
```

Phạm vi xem của bác sĩ: từ đầu hội thoại tới hết phiên gần nhất của mình (tin mốc `consultation_resolved`).
`GET /messages` cắt tại mốc đó, còn `/stream` từ chối bác sĩ có phiên đã kết thúc và tự đóng ngay sau
`consultation.updated` (`status=resolved`). Chủ hội thoại không bị giới hạn.

Room dùng chung cho 3 bên. Ngoài event của agent còn có `message.created` (tin bệnh nhân/bác sĩ đã ghi DB, kèm
`message` dạng `MessageOutput`) và `consultation.updated` (`session_id`, `status`, `doctor_id`). Khi ca tư vấn
đang `active`, `POST /messages` chỉ ghi tin + phát `message.created`, **không** tạo turn (response
`assistant_message = null`); ca `pending` thì AI vẫn trả lời. Danh sách ca của bác sĩ nghe thêm kênh
`doctor:inbox`. Pub/Sub không replay nên client refetch `GET /messages` mỗi khi room nối lại.

Các điểm cần nhớ:

1. **Core tạo sẵn row assistant** (`status="queued"`) và trả `id` ngay trong response `POST`, FE gắn vào
   bubble mà không cần chờ event.
2. **Hoãn publish tới khi có người nghe room**: turn được để trong Redis `agent:pending_turn:{conv}`; nếu room
   đã có subscriber thì `POST` đẩy ngay vào RabbitMQ (sau khi commit DB), nếu chưa thì handler SSE
   `subscribe` xong mới `GETDEL` và đẩy. Lý do: Redis Pub/Sub không replay, publish sớm sẽ mất event đầu luồng.
3. **Core là pure forwarder** cho SSE — không biến đổi event. Event realtime có thể mất nếu FE rớt kết nối,
   nhưng kết quả cuối vẫn được ghi Postgres qua `agent_response_queue`.
4. **Chỉ Core ghi Postgres**: Worker gửi `AgentResponseMessage`, `response_consumer.py` upsert row assistant
   (`content`, `status`, `metadata.reasoning`, `metadata.choice`).
5. Lỗi giữa chừng (LLM 429, network...) → Worker vẫn kết thúc turn bằng `message.done` với câu xin lỗi, để
   row không kẹt `queued`.

### Trạng thái tin nhắn (`messages.status`)

| Status | Ý nghĩa |
|---|---|
| `queued` | row assistant vừa tạo, Worker chưa chạy |
| `question` | turn tạm dừng chờ người dùng trả lời `ask_user` |
| `done` | xong (user message luôn `done` ngay khi lưu) |

`sender`: `patient` / `ai` / `doctor`.

## 4. Event SSE

| `type` | Khi nào | Payload chính |
|---|---|---|
| `message.started` | Worker bắt đầu turn | `corr_id`, `conversation_id`, `message_id` |
| `message.thinking` | một bước lập luận của agent | `content` |
| `message.tool_result` | một tool chạy xong | `tool` (tên hiển thị), `input`, `content` |
| `message.delta` | token câu trả lời cuối | `delta` |
| `message.question` | agent gọi `ask_user`, turn tạm dừng | `choice` (`question_id`, `question`, `options`) |
| `message.done` | turn kết thúc | `content` |
| `[DONE]` | sentinel, Core đóng SSE | — |

`message.thinking` / `message.tool_result` do middleware phát (`agent/middleware/v1/model.py`, `agent/middleware/common/tool.py`),
`turn.py` chỉ forward token và chốt kết quả. Bước lập luận được lưu vào `metadata.reasoning` để FE dựng lại
khi tải lại trang.

## 5. Hỏi lại người dùng (`ask_user`) và một turn một lúc

**Hỏi lại**: tool `ask_user` gọi `interrupt()` của LangGraph → graph dừng và giữ state trong checkpointer →
Worker phát `message.question`, ghi row assistant `status="question"` + `metadata.choice` → SSE đóng.
Người dùng trả lời qua `POST .../questions/{question_id}/answer` (không tạo message mới) → Core hoãn một
`TurnRequest(type="resume")` → FE mở lại SSE → Worker `Command(resume=answer)` chạy tiếp đúng chỗ đã dừng.

**Một turn một lúc** (không có Steer): Redis `agent:active_turn:{conv}` giữ id row assistant từ lúc mở turn
tới khi `message.done` (kể cả khi đang chờ trả lời `ask_user`). Trong thời gian đó `POST .../messages` trả
**409**, FE cũng khoá nút gửi khi đang stream. Worker vẫn giữ một `asyncio.Lock` cho mỗi hội thoại làm lớp
bảo vệ cuối, vì `create_agent` không cho chạy song song trên cùng `thread_id`.

## 6. Agent

Agent gồm hai graph. **Chat graph** (`chat_graph.py`) lọc intent: tin xã giao / hỏi về trợ lý / ngoài phạm vi da liễu được trả lời luôn, còn lại chuyển sang **graph tiền chẩn đoán** (`pre_diagnosis_graph.py`), dùng `create_agent` (LangChain) — vòng lặp ReAct có sẵn — với:

- **`thread_id = conversation_id`**: checkpointer nối mọi turn của một hội thoại (short-term memory).
- **Model theo hội thoại**: `conversations.model` lưu id ngắn, Worker map sang `"provider:model"` qua
  `AGENT_MODEL_CHOICES`; middleware `select_model` áp dụng, rỗng thì dùng `AGENT_MODEL`. Gọi LLM qua OpenRouter.
- **Middleware** đang bật: `select_model`, `inject_long_term_memory`, `force_reasoning`,
  `enforce_initial_reasoning`, `emit_tool_result`. Đang tắt: `critic_review` (LLM chấm bản nháp),
  `SummarizationMiddleware`.

### Tool

| Tool | Việc | Nguồn |
|---|---|---|
| `record_reasoning` | ghi lập luận có cấu trúc (hiện thành bước suy luận trên UI) | — |
| `ask_user` | hỏi lại người dùng, có lựa chọn | `interrupt()` |
| `hybrid_retrieval` | tool tra cứu **mặc định** cho yêu cầu chung: sách giáo khoa đã số hoá + đồ thị tri thức, chạy semantic + BM25 + KG (trích thực thể → DermO → PrimeKG, bệnh ứng viên) rồi rerank bằng Qwen3-Reranker (OpenRouter); trả đoạn kèm nguồn (sách, mục, trang) | Qdrant `derma_document_chunks` + Neo4j PrimeKG/DermO |
| `semantic_search` | (chuyên biệt) tra sách giáo khoa đã số hoá theo ngữ nghĩa (embedding → Qdrant), rerank bằng Qwen3-Reranker (OpenRouter); trả đoạn kèm nguồn (sách, mục, trang) | Qdrant `derma_document_chunks` |
| `keyword_search` | (chuyên biệt) tra sách giáo khoa theo từ khoá (BM25 do Qdrant chấm trên sparse vector) — bắt tên thuốc, thuật ngữ; cùng dạng kết quả với `semantic_search` | Qdrant `derma_document_chunks` |
| `knowledge_graph_query` | (tool riêng) template Cypher theo `intent` (8 intent: ứng viên theo triệu chứng, phân biệt, hồ sơ bệnh, triệu chứng, cờ đỏ/nguy cơ, điều trị, chống chỉ định, hồ sơ thuốc) trên PrimeKG/DermO; `red_flags_risk` hiện luôn trả rỗng (đồ thị không còn dữ liệu BYT), `symptoms_of_disease` / `disease_overview` chỉ có dữ liệu cho một số bệnh; chỉ là gợi ý, không phải bằng chứng | Neo4j PrimeKG/DermO |
| `classify_skin_image` | CNN 22 lớp phân loại ảnh da — chỉ là **giả thuyết** | MinIO + PyTorch |
| `analyze_skin_image_multimodal` | (chỉ đăng ký khi `AGENT_VISION_MODEL` không rỗng) model multimodal (vd MedGemma qua Ollama) mô tả hình thái/phân bố + giả thuyết, bổ sung cho CNN — không phải bằng chứng. Xem [notice](../notice/medgemma-image-description.md) | MinIO + model theo `AGENT_VISION_MODEL` |
| `search_trusted_web`, `fetch_trusted_page` | tra web trong danh sách domain uy tín | Tavily |

### Long-term memory

Memory theo **hồ sơ bệnh nhân** (xuyên hội thoại), lưu Postgres (schema `langgraph`), không embedding. Đọc: tối đa 10 bản
mới nhất chèn vào system prompt (v2 đọc một lần ở node `load_memory`, v1 qua `inject_long_term_memory`). Ghi: không còn
tool; sau khi trả lời, worker chạy nền gom tin người dùng vào bộ đệm rồi cập nhật memory theo batch (đối chiếu với memory
cũ: thêm / ghi đè / bỏ qua) và gom định kỳ. Chi tiết: `core/app/kien-truc-memory.md`.

## 7. Ảnh đính kèm

FE `POST /uploads` trước → nhận `FileDto` → gửi kèm trong `attached_files` của `POST .../messages`. Core
kiểm tra file đã tồn tại, nối vào tin qua `message_files`; chỉ ảnh được forward cho Worker để
`classify_skin_image` đọc từ MinIO.

## 8. Hạn chế / đơn giản hoá có chủ ý

- Chưa có auth: `user_id` truyền từ client (FE dùng `user-1`).
- Checkpoint hội thoại (lịch sử của agent và `diag`) và long-term memory đều lưu Postgres (schema `langgraph`); chỉ chạy 1 Worker vì khoá chống chạy đè theo hội thoại nằm trong tiến trình.
- Không có Steer: người dùng phải chờ turn xong (hoặc trả lời câu hỏi đang chờ) mới gửi được tin mới.
- Row assistant có thể kẹt `queued` nếu FE gửi tin nhưng không mở SSE (key Redis có TTL, row DB thì không);
  chưa có job dọn.
- Chưa trả `sources` (trích dẫn) có cấu trúc cho FE.
- Tư vấn với bác sĩ (`consultation_sessions`, `sender="doctor"`, `video_calls`) mới có schema.
