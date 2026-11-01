# Derma Hospital

Đồ án tốt nghiệp: hệ thống hỗ trợ tư vấn da liễu bằng AI, chia thành 7 module (mã `M1`–`M7` khớp [yêu cầu](docs/overview/requirements.md) và [phân rã chức năng](docs/overview/phan-ra-chuc-nang.md)):

| Module | Người dùng | Làm gì | Tài liệu |
|---|---|---|---|
| **M1. Tài khoản & hồ sơ bệnh nhân** | mọi người dùng | đăng ký / đăng nhập (JWT), vai trò bệnh nhân / bác sĩ / admin, một tài khoản nhiều hồ sơ bệnh nhân | [docs/overview/requirements.md](docs/overview/requirements.md) |
| **M2. Chatbot tư vấn AI** | bệnh nhân | chat với trợ lý AI (kèm ảnh da). Agent LangGraph lọc intent, suy luận nhiều bước, tra sách / đồ thị tri thức / ca bệnh tương tự / phân loại ảnh, hỏi lại khi thiếu thông tin, stream realtime, nhớ thông tin bệnh nhân giữa các hội thoại | [docs/module/chat.md](docs/module/chat.md) |
| **M3. Tư vấn với bác sĩ** | bệnh nhân, bác sĩ | xin tư vấn từ hội thoại AI; Worker sinh báo cáo tiền tư vấn + dữ kiện lâm sàng; bác sĩ nhận ca, nhắn trực tiếp, gọi video (WebRTC), xem hồ sơ + đồ thị hành trình bệnh nhân, chốt báo cáo kết luận | [docs/module/doctor-consultation.md](docs/module/doctor-consultation.md), [patient-journey-graph](docs/module/patient-journey-graph.md) |
| **M4. Kho tri thức: số hoá tài liệu** | admin / bác sĩ | upload PDF → đọc chữ → AI đọc mục lục (người duyệt) → cắt chunk theo mục lục → nạp Qdrant | [docs/module/book-ingest-pipeline.md](docs/module/book-ingest-pipeline.md) |
| **M5. Đồ thị tri thức** | admin, chatbot | PrimeKG + DermO (dựng bằng `graph_base/`), cạnh quan hệ AI trích từ sách (các bước `graph` / `graph_index` của pipeline, người duyệt), schema loại thực thể / quan hệ do admin định nghĩa | [docs/module/knowledge-graph.md](docs/module/knowledge-graph.md), [knowledge-graph-flow](docs/module/knowledge-graph-flow.md) |
| **M6. Ca bệnh & dữ liệu ảnh** | bác sĩ | báo cáo kết luận đã chốt (kèm ảnh) được nạp Qdrant để chatbot tra ca tương tự; gán nhãn ảnh / xuất dataset CNN chưa làm | [docs/module/doctor-consultation.md](docs/module/doctor-consultation.md) |
| **M7. Đặt lịch khám** | bệnh nhân, bác sĩ | hoãn, ngoài scope đồ án hiện tại | — |

Tổng quan kiến trúc: [docs/overview/system-overview.md](docs/overview/system-overview.md).

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**. Guideline đang chờ bác sĩ duyệt.

## 1. Kiến trúc

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

- **FE** (`fe/`): Next.js App Router. Chat dùng Zustand + SSE; khu `/doctor` (bác sĩ + admin tài liệu / schema đồ thị) dùng TanStack Query và poll trạng thái.
- **Core** (`core/app/`): REST + SSE gateway, là nơi **duy nhất ghi Postgres** (ngoại lệ: Worker ghi schema `langgraph` của checkpoint / memory). Đăng nhập JWT (`/auth/*`).
  Không gọi LLM cho chat, chỉ publish turn sang Worker và forward nguyên văn event từ Redis ra SSE.
- **Agent Worker** (`core/agent/`): tiến trình riêng, consume `agent_request_queue`, chạy chat graph (lọc intent → graph tiền chẩn đoán
  **v1** `create_agent` + middleware hoặc **v2** `StateGraph` có hai làn chữ / ảnh, chọn bằng `AGENT_GRAPH_VERSION`), gọi LLM theo `AGENT_MODEL`
  (OpenRouter / DeepSeek / Gemini / local), trả kết quả về `agent_response_queue`.
- **Ingest Worker** (`core/app/workers/document_ingest_worker.py`): tiến trình riêng, consume `document_ingest_queue` và chạy từng bước pipeline sách. Core chỉ ghi `running` rồi publish.
- **Pipeline** (`core/pipeline/document_ingest/`): chỉ biến đổi dữ liệu (`ingest → toc → chunks → index`, nhánh `chunks → graph → graph_index`).
- **Hạ tầng**: Postgres (dữ liệu nghiệp vụ), Redis (Pub/Sub + key turn), RabbitMQ (Core ⇄ Worker, Core → Ingest Worker),
  Qdrant (chunk sách, báo cáo kết luận), Neo4j (PrimeKG + DermO + cạnh trích từ sách), MinIO (ảnh đính kèm, file tài liệu).

## 2. Cấu trúc thư mục

```
fe/                      Next.js
  app/                   route: /chats, /doctor (ca tư vấn), /doctor/records, /admin/documents, /admin/graph-schema
  features/chat/         store Zustand, types, components chat
  features/{auth,doctor,patient-profile,video-call,settings}/  đăng nhập, khu bác sĩ, hồ sơ bệnh nhân, gọi video
  features/document-pipeline/  api, hooks TanStack Query, components admin
  features/graph-schema/ admin schema đồ thị (loại thực thể, quan hệ)
  services/              HTTP client, SSE, adapter wire ↔ UI
  components/ui/         UI primitive
core/
  main.py                entrypoint Core
  app/                   api → services → repositories → models; dto/{base,request,response}; infra/
  agent/                 worker.py, turn.py, graph/{v1,v2}, tools/, middleware/, prompt/, state/, test/ (debug app)
  app/workers/           agent_response_consumer, document_ingest_worker
  pipeline/document_ingest/   stages/, mapping.py, tests/
  graph_base/            dựng đồ thị nền PrimeKG + DermO (download → build → load → verify)
  benchmark/             benchmark retrieval / graph / RAG / e2e
  migrations/            Alembic
  data_ingest/           dữ liệu tĩnh cũ (nguồn guideline), chưa dọn
scripts/                 script gốc repo (transfer-data.sh; scripts/backup/ gitignore)
docs/overview/           tổng quan, bảng DB, yêu cầu, phân rã chức năng
docs/module/             tài liệu từng module (chat, pipeline, đồ thị, tư vấn bác sĩ, video call, ...)
docs/pending/            ý tưởng / hướng mở rộng chưa làm
docs/benchmark/         kết quả đo retrieval
docker-compose.yml       hạ tầng dev (Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO, coturn)
docker-compose.prod.yml  stack production (xem DEPLOY.md)
```

## 3. Chạy dev

Yêu cầu: Docker Compose v2, Python 3.12+ và [`uv`](https://docs.astral.sh/uv/), Node.js 20+ và `pnpm`,
API key OpenRouter.

```bash
cp core/.env.example core/.env          # điền OPENROUTER_API_KEY
cp fe/.env.local.example fe/.env.local  # NEXT_PUBLIC_USE_MOCK=false để gọi Core thật

make infra       # docker compose up -d: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
make migrate     # alembic upgrade head
make init-db     # bucket MinIO + dữ liệu mẫu — chạy sau migrate, chạy lại không tạo trùng
make backend     # Core http://localhost:3050 (Swagger: /docs)
make worker      # Agent Worker — bắt buộc để agent trả lời
make ingest-worker  # Ingest Worker — bắt buộc để nút "Chạy" ở /admin/documents có tác dụng
make frontend    # FE http://localhost:3010

make migrate-new m="mô tả"   # khi đổi model: sinh migration, đọc lại file trước khi `make migrate`
make debug-app   # (tuỳ chọn) Streamlit chạy graph agent trực tiếp để xem luồng lập luận, không cần backend / worker

make reindex-qdrant  # (khi đổi model embedding / nạp lại kho tri thức) nạp lại Qdrant từ MinIO/Postgres; dry=1 để xem trước
```

**Nạp dữ liệu đồ thị tri thức** (Neo4j mới tạo đang trống; chunk sách vào Qdrant qua giao diện `/admin/documents`), chạy ở thư mục gốc repo:

```bash
make kg-download    # tải PrimeKG (~1 GB) và DermO từ nguồn gốc
make kg-build
make kg-load        # thêm reset=1 để xoá đồ thị cũ trước khi nạp (xoá cả cạnh trích từ sách)
make kg-verify
```

**Tài khoản mẫu** (`make init-db`, mật khẩu `123456`): `user-1` (bệnh nhân), `doctor-1` (bác sĩ), `admin-1` (admin). Đăng nhập ở `http://localhost:3010`; khu `/doctor/*` cần tài khoản bác sĩ.

Chi tiết đồ thị nền: [core/graph_base/README.md](core/graph_base/README.md). (Script cũ trong `core/data_ingest/` chưa dọn, không dùng cho đồ thị nền nữa.)

Chạy tối thiểu để chat: `make infra`, `migrate`, `init-db`, `backend`, `worker`, `frontend`. Muốn agent trả lời có căn cứ thì cần thêm chunk sách (Qdrant, qua `/admin/documents` + `make ingest-worker`) và đồ thị nền (`make kg-*`).

Tool `classify_skin_image` cần checkpoint CNN tại `SKIN_CNN_CHECKPOINT_PATH`. Tool `analyze_skin_image_multimodal` chỉ bật khi `AGENT_VISION_MODEL` không rỗng.
Gọi video giữa hai mạng khác nhau cần TURN (`TURN_URL`, `TURN_SECRET`; coturn có trong `docker-compose.yml`), xem [docs/module/doctor-consultation.md](docs/module/doctor-consultation.md).

### Chuyển dữ liệu sang máy khác

Dữ liệu sách BYT nằm ở Postgres, MinIO, Qdrant và Neo4j nên phải chuyển cả 4. Script đóng gói 4 volume vào `scripts/backup/` (gitignore):

```bash
# máy cũ: tắt stack (không -v) rồi export
docker compose down
make data-export

# copy thư mục scripts/backup/ sang cùng vị trí ở máy mới (USB, scp -r, ...)

# máy mới: clone repo, tạo core/.env, stack đang tắt
make data-restore          # hỏi 'yes' vì ghi đè 4 volume
docker compose up -d       # KHÔNG chạy make migrate / make init-db
```

- Copy **toàn bộ** 4 volume (cả chat, báo cáo kết luận, ảnh đính kèm), không chỉ sách BYT; Redis/RabbitMQ không theo sang.
- Máy mới dùng cùng phiên bản image và cùng model embedding / tên collection Qdrant.
- Prod: thêm `VOL_PREFIX=derma-hospital-prod_` (ví dụ `make data-export VOL_PREFIX=derma-hospital-prod_`).
- Chỉ cần nạp lại Qdrant (đổi model embedding, mất collection) thì không cần chuyển volume: `make reindex-qdrant`, xem [docs/module/book-ingest-pipeline.md](docs/module/book-ingest-pipeline.md) mục Lưu trữ.

### Biến môi trường chính

| Biến | Dùng cho |
|---|---|
| `DATABASE_URL`, `REDIS_*`, `RABBITMQ_URL`, `QDRANT_URL`, `NEO4J_*`, `MINIO_*` | kết nối hạ tầng, mặc định khớp `docker-compose.yml` |
| `AGENT_MODEL`, `AGENT_TEMPERATURE`, `OPENROUTER_API_KEY` (hoặc key của provider khác) | model mặc định của agent; model người dùng được chọn là `AGENT_MODEL_CHOICES` trong `settings.py` |
| `AGENT_GRAPH_VERSION` (`v1` mặc định, `v2`), `AGENT_TRIAGE_ENABLED`, `AGENT_VISION_MODEL` | chọn graph tiền chẩn đoán, bước lọc intent, model mô tả ảnh (đổi phải restart Worker) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RERANKER_MODEL`, `QDRANT_DOCUMENT_COLLECTION` | embedding + rerank qua OpenRouter; đổi model / số chiều thì phải reindex |
| `JWT_SECRET_KEY`, `JWT_*_EXPIRE_*` | đăng nhập; **đổi `JWT_SECRET_KEY` khi deploy** |
| `MINIO_DOCUMENTS_BUCKET`, `SKIN_CNN_CHECKPOINT_PATH` | bucket file tài liệu; checkpoint CNN phân loại ảnh |
| `TURN_URL`, `TURN_SECRET` | TURN cho video call khi hai bên khác mạng |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` | (tuỳ chọn) trace agent trên LangSmith |

Đầy đủ biến và giá trị mặc định: `core/.env.example`, `core/app/config/settings.py`.
| `NEXT_PUBLIC_USE_MOCK`, `NEXT_PUBLIC_API_URL` | FE dùng mock hay Core thật, URL Core |

`.env` không được commit.

## 4. Kiểm tra

```bash
cd core && .venv/bin/python -m pyright app pipeline     # kiểu Python
cd core && python -m unittest pipeline.document_ingest.tests.test_document_pipeline \
  pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index \
  pipeline.document_ingest.tests.test_graph pipeline.document_ingest.tests.test_graph_schema
cd core && python -m unittest discover -s tests -t .     # memory, retrieval, reindex, video call, state tiền chẩn đoán
cd fe && pnpm exec tsc --noEmit && pnpm lint
```

Test pipeline không cần service thật (MinIO giả + SQLite + Qdrant in-memory).

## 5. Quy ước

Chi tiết trong các skill ở `.claude/skills/`; dưới đây là các điểm hay nhầm.

| Khu vực | Skill |
|---|---|
| `core/app/`, `core/agent/` (endpoint, DTO, model, service, tool, middleware, prompt) | [derma-core-conventions](.claude/skills/derma-core-conventions/SKILL.md) |
| `core/pipeline/document_ingest/`, `app/services/document_*.py`, `document_repository.py` | [derma-pipeline-conventions](.claude/skills/derma-pipeline-conventions/SKILL.md) |
| `fe/` (trang, component, store, hook, SSE event) | [derma-fe-conventions](.claude/skills/derma-fe-conventions/SKILL.md) |
| Chạy Core / Worker, gửi tin thử, pyright | [run-core](.claude/skills/run-core/SKILL.md) |
| Chạy FE, chụp màn hình | [run-fe](.claude/skills/run-fe/SKILL.md) |
| Thử prompt / model / tool của agent | [experiment-agent-flow](.claude/skills/experiment-agent-flow/SKILL.md) |

**Backend**
- Phân lớp `api` (chỉ map request/response) → `services` (nghiệp vụ) → `repositories` (stateless, nhận id trực
  tiếp) → `models` (ORM).
- Entity nghiệp vụ ở `app/dto/base/`, tách khỏi ORM (`app/models/`) và DTO wire (`app/dto/request|response/`).
  Đổi `dto/base` phải được duyệt trước rồi mới cascade xuống model/repo/service.
- Wire dùng snake_case, response bọc `{"data": ...}`.
- Chỉ Core ghi Postgres; Worker trả kết quả qua RabbitMQ.
- `pipeline/` không import `app.services` / `app.repositories`; stage nhận mọi thứ qua `StageContext`.
  Lỗi người dùng sửa được dùng `StageError` / `InvalidError` (hiển thị nguyên văn trên UI).
- Schema đổi qua Alembic (`make migrate-new m="..."`), **đọc lại file sinh ra**, không để autogenerate drop bảng có dữ liệu.
- Python snake_case; docstring và comment tiếng Việt, giải thích **vì sao**.

**Frontend**
- `app/` chỉ là route mỏng; logic theo tính năng nằm ở `features/<feature>/`; gọi HTTP ở `services/`.
- Chat: state trong Zustand store, event SSE được chuẩn hoá trong `store.ts`. Admin: TanStack Query hooks.

## 6. Hạn chế đã biết

- Chat, hồ sơ, tư vấn, video call đã dùng JWT; API admin tài liệu / schema đồ thị (`/admin/*`) **chưa kiểm tra JWT / vai trò phía server**.
- Checkpoint hội thoại (lịch sử của agent và `diag`) và long-term memory đều lưu Postgres (schema `langgraph`); chỉ chạy 1 Worker vì khoá chống chạy đè theo hội thoại nằm trong tiến trình.
- Mỗi hội thoại một turn một lúc (không có Steer); đang chờ trả lời câu hỏi thì không gửi được tin mới.
- Upload PDF đi qua Core; DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi.
- v2 (hai làn chữ / ảnh) chưa chạy qua Worker + RabbitMQ + API thật và không có `ask_user`; mặc định vẫn là v1 (xem [docs/module/chat.md](docs/module/chat.md) mục Agent).
- Video call dùng WebRTC, không ghi âm / ghi hình; khác mạng cần TURN. Guideline và kết quả AI chưa được bác sĩ duyệt.
- Đồ thị trích từ sách còn thưa và truy vấn khớp theo chuỗi, tên bệnh tiếng Việt thường không khớp.

## 7. Tài liệu khác

- [DEPLOY.md](DEPLOY.md) — deploy production bằng Docker Compose (hiện mới mô tả phần chat).
- [core/app/kien-truc-agent.md](core/app/kien-truc-agent.md), [core/app/kien-truc-memory.md](core/app/kien-truc-memory.md) —
  thiết kế agent và memory (một phần mô tả thiết kế cũ; khi lệch, ưu tiên `docs/module/`).
- [docs/overview/](docs/overview/) — [bảng DB](docs/overview/db-tables.md), [yêu cầu](docs/overview/requirements.md), [phân rã chức năng](docs/overview/phan-ra-chuc-nang.md).
- [docs/module/](docs/module/) — [chat](docs/module/chat.md), [tư vấn với bác sĩ](docs/module/doctor-consultation.md), [pipeline sách](docs/module/book-ingest-pipeline.md), [đồ thị tri thức](docs/module/knowledge-graph.md) ([flow](docs/module/knowledge-graph-flow.md)), [đồ thị hành trình bệnh nhân](docs/module/patient-journey-graph.md).
- [docs/pending/](docs/pending/) — ý tưởng chưa làm; [docs/benchmark/](docs/benchmark/) — đo retrieval; [core/benchmark/](core/benchmark/) — code benchmark.
- [fe/docs/backend-contract.md](fe/docs/backend-contract.md) — hợp đồng REST + SSE với FE.
- [core/pipeline/document_ingest/README.md](core/pipeline/document_ingest/README.md) — chi tiết pipeline.
