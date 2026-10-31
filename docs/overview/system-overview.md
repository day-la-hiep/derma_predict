# Tổng quan hệ thống Derma Hospital

Derma Hospital chia thành **7 module** (mã khớp [requirements.md](requirements.md), [phan-ra-chuc-nang.md](phan-ra-chuc-nang.md)) dùng chung một Core (FastAPI) và một bộ hạ tầng:

| Module | Người dùng | Làm gì | Code chính | Tài liệu |
|---|---|---|---|---|
| **M1. Tài khoản & hồ sơ bệnh nhân** | mọi người dùng | JWT, vai trò, nhiều hồ sơ / tài khoản | `auth_*`, `patient_profile_*`; FE `features/auth`, `patient-profile` | [requirements.md](requirements.md) |
| **M2. Chatbot tư vấn AI** | bệnh nhân | chat, agent suy luận, tra sách / đồ thị / ca bệnh / ảnh, memory | `conversation_*`, `message_service`, `core/agent/`; FE `features/chat` | [chat.md](../module/chat.md) |
| **M3. Tư vấn với bác sĩ** | bệnh nhân, bác sĩ | xin tư vấn, báo cáo tiền tư vấn, chat, video, báo cáo kết luận, đồ thị hành trình | `consultation_*`, `finalize_report_*`, `video_call_*`, `patient_graph_service`; FE `features/doctor`, `video-call` | [doctor-consultation.md](../module/doctor-consultation.md), [patient-journey-graph.md](../module/patient-journey-graph.md) |
| **M4. Kho tri thức: số hoá tài liệu** | admin / bác sĩ | PDF → chữ → mục lục → chunk → Qdrant | `document_*`, `pipeline/document_ingest`, Ingest Worker; FE `features/document-pipeline` | [book-ingest-pipeline.md](../module/book-ingest-pipeline.md) |
| **M5. Đồ thị tri thức** | admin, chatbot | PrimeKG + DermO, cạnh trích từ sách, schema admin | `graph_base/`, `document_graph_service`, `graph_schema_*`; FE `features/graph-schema` | [knowledge-graph.md](../module/knowledge-graph.md) |
| **M6. Ca bệnh & dữ liệu ảnh** | bác sĩ | ca đã chốt nạp Qdrant cho chatbot tra; nhãn ảnh CNN | `finalize_report_index_service`, `qdrant_reindex_service` | [doctor-consultation.md](../module/doctor-consultation.md) |
| **M7. Đặt lịch khám** | — | hoãn | — | — |

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**.

## 1. Thành phần

```
┌──────────────┐  REST + SSE  ┌──────────────────┐  RabbitMQ   ┌───────────────┐
│ FE (Next.js) │─────────────▶│  Core (FastAPI)  │────────────▶│ Agent Worker  │
│ /chats       │◀─────────────│  :3050 /api/v1   │◀────────────│ (LangGraph)   │
│ /doctor/...  │              └──┬────┬────┬─────┘             └───────┬───────┘
└──────────────┘                 │    │    │ document_ingest_queue     │
                                 │    │    ▼                           │
                                 │    │  ┌───────────────┐             │
                                 │    │  │ Ingest Worker │             │
                                 │    │  │ (pipeline sách)│            │
                                 │    │  └───────────────┘   Redis Pub/Sub (event chat)
        ┌──────────────┬─────────┴┐  ┌┴──────────┬──────────┐
        │ PostgreSQL   │  MinIO   │  │ Qdrant    │  Neo4j   │
        └──────────────┴──────────┘  └───────────┴──────────┘
```

| Thành phần | Vai trò | Vị trí code |
|---|---|---|
| **FE** | Next.js App Router. `/chats` (Zustand store + SSE), `/doctor` (ca tư vấn, hồ sơ), `/doctor/documents`, `/doctor/graph-schema` (TanStack Query, poll) | `fe/app/`, `fe/features/{chat,doctor,video-call,document-pipeline,graph-schema,...}/` |
| **Core** | REST + SSE gateway, JWT, ghi Postgres, publish turn sang Worker, consume kết quả, publish yêu cầu chạy bước pipeline | `core/app/` (`api/`, `services/`, `repositories/`, `models/`, `dto/`, `infra/`, `workers/agent_response_consumer.py`) |
| **Agent Worker** | Tiến trình riêng, consume `agent_request_queue`, chạy chat graph (lọc intent → tiền chẩn đoán v1 / v2), stream event lên Redis, ghi checkpoint + memory vào schema `langgraph` | `core/agent/` (`worker.py`, `turn.py`, `graph/`, `tools/`, `middleware/`, `persistence.py`) |
| **Ingest Worker** | Tiến trình riêng, consume `document_ingest_queue`, chạy từng bước pipeline tài liệu; dừng qua Redis | `core/app/workers/document_ingest_worker.py` |
| **Pipeline tài liệu** | Chỉ biến đổi dữ liệu (PDF → trang → mục lục → chunk → vector; chunk → quan hệ → Neo4j) | `core/pipeline/document_ingest/` |
| **PostgreSQL** | Nguồn sự thật: user, hồ sơ bệnh nhân, hội thoại, tin nhắn, ca tư vấn, báo cáo, file, tài liệu + trạng thái bước, schema đồ thị | migration Alembic `core/migrations/` |
| **Redis** | Pub/Sub event realtime (room hội thoại, inbox bác sĩ, cuộc gọi); key turn đang chạy / chờ đẩy; cờ dừng pipeline | `app/infra/redis_client.py` |
| **RabbitMQ** | `agent_request_queue` (Core → Worker), `agent_response_queue` (Worker → Core), `document_ingest_queue` (Core → Ingest Worker) | `app/infra/rabbitmq_client.py` |
| **Qdrant** | `derma_document_chunks_v4` (chunk sách; agent tra bằng `hybrid_retrieval` / `semantic_search` / `keyword_search`), `derma_finalize_reports` (báo cáo kết luận; tool `search_finalize_report*`) | `app/infra/qdrant_client.py` |
| **Neo4j** | PrimeKG (`:Entity`) + ontology DermO (`:DermoTerm`) + cạnh trích từ sách (`source='DOC'`); đồ thị hành trình bệnh nhân | dựng bằng `core/graph_base/`, cạnh sách do pipeline |
| **MinIO** | ảnh đính kèm tin nhắn; mọi file của tài liệu dưới `document/<id>/` | `app/infra/minio_client.py` |

## 2. Nguyên tắc kiến trúc chung

- **Chỉ Core ghi Postgres** (bảng nghiệp vụ). Agent Worker gửi kết quả về qua `agent_response_queue`; Ingest Worker dùng
  repository của Core để ghi trạng thái bước. Ngoại lệ: Agent Worker ghi trực tiếp schema `langgraph` (checkpoint, long-term memory).
- **Core không gọi LLM cho chat** — chỉ publish turn và forward event. LLM chạy ở Worker, nên request HTTP luôn
  trả nhanh. (Pipeline tài liệu gọi LLM ở bước `toc` và `graph`, nhưng chạy ở Ingest Worker; API chỉ ghi `running` rồi trả ngay.)
- **Phân lớp trong `core/app/`**: `api` (map request/response) → `services` (nghiệp vụ) → `repositories`
  (truy cập DB, stateless) → `models` (ORM). Entity nghiệp vụ nằm ở `dto/base/`, khác DTO wire
  (`dto/request|response/`) và ORM.
- **`pipeline/` không import `app.services`/`app.repositories`** — nhận mọi thứ qua `StageContext`.
- Wire dùng **snake_case**, envelope `{"data": ...}`.

## 3. Dữ liệu chính (Postgres)

| Nhóm | Bảng |
|---|---|
| Người dùng | `users`, `patient_profiles`, `doctors`, `admins` |
| Chat | `conversations`, `messages` (cột `metadata` JSONB: reasoning, choice, ...), `files`, `message_files` |
| Tư vấn bác sĩ | `consultation_sessions`, `video_calls`, `pre_consultation_reports` |
| Báo cáo / lâm sàng | `finalize_reports`, `patient_images`, `clinical_fact_templates`, `clinical_facts`, `clinical_provenances` |
| Tài liệu | `documents` (+ cột `profile` JSON), `document_stages`, `document_overrides` |
| Schema đồ thị (admin) | `graph_entity_types`, `graph_relations` |

Chi tiết: [`db-tables.md`](db-tables.md), sơ đồ [`db-diagram.dbml`](db-diagram.dbml).

## 4. Chạy dự án

```bash
make infra     # docker compose: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
make migrate   # alembic upgrade head
make init-db   # bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin)
make backend   # Core :3050
make worker    # Agent Worker
make ingest-worker  # Ingest Worker (pipeline tài liệu)
make frontend  # Next.js :3010
```

Đồ thị nền nạp bằng `make kg-download kg-build kg-load kg-verify` (`core/graph_base/`); chunk sách nạp qua giao diện `/doctor/documents`; `make reindex-qdrant` nạp lại Qdrant.

## 5. Tài liệu liên quan

- [`fe/docs/backend-contract.md`](../../fe/docs/backend-contract.md) — hợp đồng REST + SSE; Swagger của Core ở `http://localhost:3050/docs`.
- [`requirements.md`](requirements.md), [`phan-ra-chuc-nang.md`](phan-ra-chuc-nang.md) — yêu cầu và phân rã chức năng.
- [`../module/knowledge-graph.md`](../module/knowledge-graph.md), [`../notice/agent-graph-versions.md`](../notice/agent-graph-versions.md).
- [`core/app/kien-truc-agent.md`](../../core/app/kien-truc-agent.md), [`kien-truc-memory.md`](../../core/app/kien-truc-memory.md).
- [`core/pipeline/document_ingest/README.md`](../../core/pipeline/document_ingest/README.md).

## 6. Hạn chế chung (đồ án)

- Chat, hồ sơ, tư vấn, video call dùng JWT (`/auth/*`, vai trò `patient` / `doctor`); API `/admin/*` (tài liệu, schema đồ thị) chưa kiểm tra JWT / vai trò phía server.
- Checkpoint hội thoại (lịch sử của agent và `diag`) và long-term memory đều lưu Postgres (schema `langgraph`); chỉ chạy 1 Worker vì khoá chống chạy đè theo hội thoại nằm trong tiến trình.
- DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi.
- Graph tiền chẩn đoán v2 chưa chạy qua Worker + RabbitMQ + API thật; mặc định vẫn là v1 (`AGENT_GRAPH_VERSION`).
- Video call cần TURN khi hai bên khác mạng; chưa có ghi âm / ghi hình.
