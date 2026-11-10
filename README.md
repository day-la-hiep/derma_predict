# Derma Hospital

Đồ án tốt nghiệp: hệ thống hỗ trợ tư vấn da liễu bằng AI, chia thành 7 module (mã `M1`–`M7` khớp [yêu cầu](docs/overview/requirements.md) và [phân rã chức năng](docs/overview/phan-ra-chuc-nang.md)):

| Module | Người dùng | Làm gì | Service |
|---|---|---|---|
| **M1. Tài khoản & hồ sơ bệnh nhân** | mọi người dùng | đăng ký / đăng nhập (JWT), vai trò bệnh nhân / bác sĩ / admin, một tài khoản nhiều hồ sơ bệnh nhân, dị ứng / tiền sử | `identity` |
| **M2. Chatbot tư vấn AI** | bệnh nhân | chat với trợ lý AI (kèm ảnh da): agent LangGraph lọc intent, suy luận nhiều bước, tra sách / đồ thị tri thức / ca bệnh tương tự / phân loại ảnh, hỏi lại khi thiếu thông tin | `consultation` + `ai` |
| **M3. Tư vấn với bác sĩ** | bệnh nhân, bác sĩ | xin tư vấn từ hội thoại AI; bác sĩ nhận ca, nhắn trực tiếp, gọi video (WebRTC), chốt báo cáo kết luận | `consultation` + `clinical` |
| **M4. Kho tri thức: số hoá tài liệu** | admin | upload PDF → đọc chữ → AI đọc mục lục (người duyệt) → cắt đoạn theo mục lục → nạp Qdrant | `knowledge` |
| **M5. Đồ thị tri thức** | admin, chatbot | PrimeKG + DermO, cạnh quan hệ AI trích từ sách, schema loại thực thể / quan hệ do admin định nghĩa | `knowledge` |
| **M6. Ca bệnh & dữ liệu ảnh** | bác sĩ | báo cáo kết luận đã chốt (kèm ảnh) được nạp Qdrant + đồ thị bệnh nhân để chatbot tra ca tương tự | `clinical` → `knowledge` |
| **M7. Đặt lịch khám** | bệnh nhân, bác sĩ | bệnh nhân đặt lịch cho một đợt bệnh đã đủ thông tin; bác sĩ xác nhận, bắt đầu khám, chốt kết luận (đóng lần khám, lịch hẹn, đợt bệnh) | `clinical` |

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**. Guideline đang chờ bác sĩ duyệt.

Kiến trúc hiện tại là **microservice**. Monolith cũ (`archive/core/`) được giữ nguyên để tham khảo, không còn chạy bằng `make`. Các tài liệu trong `docs/` phần lớn vẫn mô tả monolith cũ; phần khác biệt của kiến trúc mới: [docs/notice/microservice-split.md](docs/notice/microservice-split.md).

## 1. Kiến trúc

```
                       ┌──────────────────────────────────────────────────────────┐
┌──────────────┐ REST  │ Gateway :3040 (Spring Cloud Gateway, chỉ định tuyến)     │
│ FE (Next.js) │──────▶│  /auth, /patient-profiles           → identity     :3051 │
│ :3010        │◀──SSE─│  /conversations, /doctor/consult…   → consultation :3052 │
└──────────────┘       │  /appointments, /doctor/appoint…,                        │
                       │  /…/finalize*, /…/episodes          → clinical     :3053 │
                       │  /admin/**                          → knowledge    :3054 │
                       └──────────────────────────────────────────────────────────┘

 consultation ──REST /internal/turns──▶ ai :3055 (LangGraph)
 ai ──REST──▶ knowledge (tìm kiếm sách / đồ thị / ca bệnh), consultation (lịch sử, kết quả lượt), clinical (fact, giả thuyết)
 ai ──Redis Stream conversation:events:{id}──▶ consultation ──SSE──▶ FE
 clinical ──REST──▶ knowledge (nạp ca đã chốt), consultation (đóng phiên), identity (hồ sơ)
 knowledge ──RabbitMQ document_ingest_queue──▶ Ingest Worker (pipeline sách)

 Mỗi service một database Postgres riêng (identity / consultation / clinical / knowledge / ai); Qdrant + Neo4j + MinIO do knowledge và ai dùng.
```

| Service | Công nghệ | Cổng | Sở hữu |
|---|---|---|---|
| `gateway_service` | Spring Cloud Gateway | 3040 | định tuyến theo đường dẫn, không verify JWT |
| `identity_service` | Spring Boot | 3051 | tài khoản, bác sĩ, hồ sơ bệnh nhân, token |
| `consultation_service` | Spring Boot | 3052 | hội thoại, tin nhắn, phiên tư vấn, cuộc gọi video, báo cáo tiền tư vấn |
| `clinical_service` | Spring Boot | 3053 | đợt bệnh, fact, giả thuyết, lịch hẹn, lần khám, báo cáo kết luận |
| `knowledge_service` | Python / FastAPI | 3054 | pipeline sách, Qdrant, Neo4j, tìm kiếm cho agent |
| `ai_service` | Python / LangGraph | 3055 | agent chat, phân loại ảnh da (CNN) |

- **Giao tiếp**: REST `/internal/*` giữa các service (header `X-Internal-Key`, không đi qua gateway); Redis Stream cho event chat (SSE có replay 30 giây, FE gửi `Last-Event-ID` khi nối lại); Redis Pub/Sub cho danh sách ca của bác sĩ và cuộc gọi; RabbitMQ chỉ còn cho pipeline sách. Hợp đồng chi tiết: [contracts/README.md](contracts/README.md).
- **Xác thực**: chỉ `identity` phát JWT (HS256, khoá chung `JWT_SECRET_KEY`); mỗi service tự verify.
- **Dữ liệu**: mỗi bảng thuộc đúng một service, tham chiếu chéo service chỉ bằng id (không FK). Chốt báo cáo không có transaction phân tán: lưu ở clinical trước, rồi mới gọi knowledge / consultation (xem mục 6).

## 2. Cấu trúc thư mục

```
fe/                    Next.js App Router (/chats, /doctor, /admin); chat dùng Zustand + SSE, admin dùng TanStack Query
gateway_service/       Spring Cloud Gateway: route trong src/main/resources/application.yml
identity_service/      Spring Boot: controller → service → repository, Flyway, JWT (Nimbus), bcrypt
consultation_service/  Spring Boot: hội thoại, SSE, phiên tư vấn, video call, upload ảnh (MinIO)
clinical_service/      Spring Boot: đợt bệnh, lịch hẹn, lần khám, báo cáo kết luận
knowledge_service/     Python: app/ (api → services → repositories), pipeline/document_ingest/, migrations/ (Alembic)
ai_service/            Python: agent/ (graph, tools, prompt), app/ (REST nhận lượt chạy)
shared/                thư viện Python dùng chung cho knowledge và ai (settings, log, JWT, Redis, MinIO, RabbitMQ)
contracts/             hợp đồng liên service (README.md) + đặc tả route của monolith cũ
deploy/                docker-compose.yml (hạ tầng), docker-compose.services.yml (6 service), docker-compose.prod.yml (core cũ), DEPLOY.md
ml/                    model/ (checkpoint CNN), notebook/ (huấn luyện), data/ (dataset, gitignore)
report/                bao_cao_latex/ (báo cáo), vp_derma/ (Visual Paradigm), thi_t_k_database.md
scripts/               init-service-databases.sh, transfer-data.sh, reset-and-gen-data.sh
docs/                  overview/ (tổng quan, bảng DB, yêu cầu), module/, notice/, pending/, benchmark/
archive/core/          monolith cũ (FastAPI + agent + pipeline), đóng băng
tmp/                   nháp, kế hoạch tạm (gitignore)
```

Service Spring dùng Lombok (`@AllArgsConstructor`, `@Slf4j`) và MapStruct (`mapper/`) cho phần ghép entity → DTO.

## 3. Chạy dev

Yêu cầu: Docker Compose v2, JDK 21 (dùng `./mvnw` có sẵn), Python 3.12+ và [`uv`](https://docs.astral.sh/uv/), Node.js 20+ và `pnpm`, API key OpenRouter.

```bash
# 1. cấu hình (file .env đã gitignore)
cp fe/.env.local.example fe/.env.local            # NEXT_PUBLIC_USE_MOCK=false để gọi backend thật
# ai_service/.env và knowledge_service/.env: điền OPENROUTER_API_KEY và QDRANT_API_KEY (các biến khác có mặc định)

# 2. hạ tầng + database
make infra                # Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO, coturn
make services-db          # tạo 5 database identity/consultation/clinical/knowledge/ai (chạy lại không sao)
make knowledge-migrate    # alembic cho database knowledge (service Spring tự chạy Flyway khi khởi động)

# 3. service: mỗi lệnh một terminal
make gateway              # :3040
make identity             # :3051
make consultation         # :3052
make clinical             # :3053
make knowledge            # :3054
make knowledge-worker     # worker pipeline sách; không chạy thì nút "Chạy" ở /admin/documents không có tác dụng
make ai                   # :3055 — bắt buộc để agent trả lời
make frontend             # FE http://localhost:3010, gọi qua gateway :3040
```

**Chạy trong IntelliJ IDEA**: thư mục `.run/` chứa sẵn các cấu hình chạy dùng chung (IDE tự nhận):

| Cấu hình | Chạy |
|---|---|
| `AiApplication` | `ai_service/main.py` (:3055) |
| `KnowledgeApplication` | `knowledge_service/main.py` (:3054) |
| `KnowledgeWorker` | `python -m app.workers.document_ingest_worker` |
| `KnowledgeMigrate` | `python -m alembic upgrade head` (chạy một lần) |
| `DermaAll` | bật cùng lúc 4 service Spring (`GatewayApplication`, `IdentityApplication`, `ConsultationApplication`, `ClinicalApplication`) + 3 cấu hình Python ở trên |

Các cấu hình Python dùng interpreter `<tên>_service/.venv` và thư mục làm việc là thư mục service (để đọc `.env`), nên cần chạy `uv sync` trong `ai_service` và `knowledge_service` một lần trước. Để chúng hiện trong cửa sổ **Services**: bấm `+` → *Run Configuration Type* → chọn *Python*. Hạ tầng (`make infra`, `make services-db`) vẫn chạy ngoài IDE.

Chạy cả 6 service bằng Docker thay cho các lệnh `make <service>`: `make services-build && make services-up` (đọc `OPENROUTER_API_KEY` từ `.env` ở gốc repo).

**Tài khoản mẫu** (migration Flyway của identity, mật khẩu `123456`): `user-1` (bệnh nhân), `doctor-1` (bác sĩ), `admin-1` (admin). Đăng nhập ở `http://localhost:3010`; `/doctor/*` cần tài khoản bác sĩ, `/admin/*` cần admin.

**Dữ liệu tri thức**: database `knowledge` mới còn trống. Sách đã số hoá ở monolith cũ cần copy bảng (`documents`, `document_stages`, `document_overrides`, `files`) từ `derma_hospital_db` sang `knowledge` (trong `psql`: `COPY (SELECT <cột> FROM …) TO STDOUT` rồi `COPY … FROM STDIN`, liệt kê cột tường minh vì thứ tự cột hai DB khác nhau); file nằm ở MinIO và vector ở Qdrant nên giữ nguyên. Đồ thị nền PrimeKG + DermO nạp bằng script trong `archive/core/graph_base/` (xem [README của nó](archive/core/graph_base/README.md); makefile không còn target này). Nạp lại Qdrant + đồ thị bệnh nhân từ các báo cáo đã chốt: `make reindex-cases`.

Một số tính năng cần thêm cấu hình: tool `classify_skin_image` cần checkpoint CNN ở `ml/model/model_output/` (`SKIN_CNN_CHECKPOINT_PATH`); mô tả ảnh bằng model vision cần `AGENT_VISION_MODEL` (mặc định trỏ model chạy local qua Ollama, không chạy thì bước này báo lỗi rồi bỏ qua, CNN vẫn chạy); gọi video giữa hai mạng khác nhau cần TURN (`TURN_URL`, `TURN_SECRET`; coturn có trong `deploy/docker-compose.yml`).

### Chuyển dữ liệu sang máy khác

Dữ liệu nằm ở 4 volume Docker (Postgres, MinIO, Qdrant, Neo4j) nên phải chuyển cả 4. Script đóng gói vào `scripts/backup/` (gitignore):

```bash
make infra-down            # máy cũ: tắt stack (không -v)
make data-export
# copy scripts/backup/ sang cùng vị trí ở máy mới

# máy mới: clone repo, điền .env của ai_service/knowledge_service, stack đang tắt
make data-restore          # hỏi 'yes' vì ghi đè 4 volume
make infra                 # KHÔNG chạy lại make services-db / knowledge-migrate
```

Copy **toàn bộ** 4 volume (cả hội thoại, báo cáo, ảnh đính kèm); Redis và RabbitMQ không theo sang. Máy mới dùng cùng phiên bản image và cùng model embedding / tên collection Qdrant. Prod: thêm `VOL_PREFIX=derma-hospital-prod_`.

### Biến môi trường chính

Service Spring đọc biến môi trường (có mặc định cho dev); service Python đọc thêm `.env` trong thư mục của chính nó.

| Biến | Dùng cho |
|---|---|
| `DATABASE_URL`, `DATABASE_USER`, `DATABASE_PASSWORD` | database của từng service (mặc định `localhost:5432`, `postgres`/`postgres`, tên DB theo service) |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `RABBITMQ_URL`, `QDRANT_URL`, `QDRANT_API_KEY`, `NEO4J_*`, `MINIO_*` | hạ tầng; mặc định khớp `deploy/docker-compose.yml` |
| `JWT_SECRET_KEY` | khoá ký JWT dùng chung; **đổi khi deploy** |
| `INTERNAL_API_KEY` | khoá cho các lời gọi `/internal/*` giữa service; **đổi khi deploy** |
| `IDENTITY_URL`, `CONSULTATION_URL`, `CLINICAL_URL`, `KNOWLEDGE_URL`, `AI_URL` | địa chỉ các service (mặc định `localhost:305x`) |
| `OPENROUTER_API_KEY` (hoặc key provider khác), `AGENT_MODEL`, `AGENT_TEMPERATURE` | model mặc định của agent; model người dùng chọn là `AGENT_MODEL_CHOICES` trong settings |
| `AGENT_GRAPH_VERSION`, `AGENT_TRIAGE_ENABLED`, `AGENT_VISION_MODEL` | chọn graph tiền chẩn đoán, bước lọc intent, model mô tả ảnh (đổi phải restart `ai`) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RERANKER_MODEL`, `QDRANT_DOCUMENT_COLLECTION` | embedding + rerank qua OpenRouter; đổi model / số chiều thì phải reindex |
| `TURN_URL`, `TURN_SECRET`, `STUN_URLS` | video call khi hai bên khác mạng |
| `NEXT_PUBLIC_USE_MOCK`, `NEXT_PUBLIC_API_URL`, `BACKEND_URL` | FE dùng mock hay backend thật, URL backend (`make frontend` đặt `BACKEND_URL` là gateway) |

Giá trị mặc định đầy đủ: `<tên>_service/src/main/resources/application.yml` (Spring), `<tên>_service/app/config/settings.py` và `shared/derma_shared/settings.py` (Python). `.env` không được commit.

## 4. Kiểm tra

```bash
make test              # 4 service Spring + shared + ai
make knowledge-test    # chạy riêng: còn 2 test test_graph_schema lỗi từ trước (KeyError 'skipped'), không do kiến trúc mới
cd fe && pnpm exec tsc --noEmit && pnpm lint
```

Test của service Spring dùng H2 (chế độ PostgreSQL) và mock client sang service khác; test Python dùng MinIO giả, SQLite, Qdrant in-memory. Test chưa thay được lần chạy thật với Postgres, Redis và LLM; luồng chat + ảnh + chốt báo cáo đã được chạy tay qua gateway và FE.

## 5. Quy ước

Chi tiết trong các skill ở `.claude/skills/`:

| Khu vực | Skill |
|---|---|
| Viết / chuyển code trong các `<tên>_service/`, gateway, hợp đồng liên service | [derma-microservice-migration](.claude/skills/derma-microservice-migration/SKILL.md) |
| `fe/` (trang, component, store, hook, SSE event) | [derma-fe-conventions](.claude/skills/derma-fe-conventions/SKILL.md) |
| Monolith cũ: `archive/core/app`, `agent` | [derma-core-conventions](.claude/skills/derma-core-conventions/SKILL.md) |
| Monolith cũ: pipeline sách | [derma-pipeline-conventions](.claude/skills/derma-pipeline-conventions/SKILL.md) |
| Chạy FE, chụp màn hình | [run-fe](.claude/skills/run-fe/SKILL.md) |
| Báo cáo đồ án (`report/bao_cao_latex/`) | [derma-report-writing](.claude/skills/derma-report-writing/SKILL.md) |

**Backend (mọi service)**
- Phân lớp `controller` / `api` (chỉ map request/response) → `service` (nghiệp vụ) → `repository`; ít wrapper, tên hàm là động từ, comment tiếng Việt giải thích **vì sao**.
- Wire dùng snake_case, response bọc `{"data": ...}`, lỗi `{"detail": "..."}`.
- Mỗi bảng chỉ một service ghi; tham chiếu chéo service bằng id, tên hiển thị lưu sẵn (denormalize).
- Spring: JPA entity field public, DTO là `record`, MapStruct cho entity → DTO, schema đổi bằng file Flyway viết tay (đọc lại trước khi chạy, giữ dữ liệu). Java gọi Python phải ép HTTP/1.1.
- Python: `knowledge` đổi schema bằng Alembic; stage pipeline chỉ biến đổi dữ liệu, nhận mọi thứ qua `StageContext`.

**Frontend**
- `app/` chỉ là route mỏng; logic theo tính năng ở `features/<feature>/`; gọi HTTP ở `services/`.
- Chat: Zustand store, event SSE chuẩn hoá trong `store.ts`. Admin: TanStack Query hooks.

## 6. Hạn chế đã biết

- Không có transaction phân tán và không có outbox: chốt báo cáo lưu ở clinical trước; nếu gọi knowledge lỗi thì ca thiếu trong Qdrant tới khi `make reindex-cases`; nếu đóng phiên ở consultation lỗi thì trả 502 và bác sĩ gửi lại (không tạo báo cáo thứ hai).
- Ảnh chỉ gắn vào đợt bệnh khi xác định được duy nhất (giả thuyết trùng nhãn CNN top-1, hoặc hội thoại chỉ có một vùng); không thì bỏ ảnh và ghi cảnh báo ở clinical.
- Database `knowledge` cần copy dữ liệu sách thủ công từ DB cũ; chưa có script.
- Chưa kiểm: `interrupt()` resume bằng câu hỏi chọn, cuộc gọi video qua service mới, build image Docker và chạy `docker-compose.services.yml`.
- Mỗi hội thoại một lượt một lúc; đang chờ trả lời câu hỏi thì không gửi được tin mới. Provider LLM đôi lúc trả 429; agent tự chuyển graph tiền chẩn đoán.
- Upload PDF đi qua `knowledge`, DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi.
- Đồ thị trích từ sách còn thưa và truy vấn khớp theo chuỗi, tên bệnh tiếng Việt thường không khớp.
- Video call dùng WebRTC, không ghi hình; khác mạng cần TURN. Guideline và kết quả AI chưa được bác sĩ duyệt.
- Gateway dùng Spring Boot 4.0.6 (Spring Cloud 2025.1 chưa hỗ trợ 4.1), các service Spring còn lại dùng 4.1.2.

## 7. Tài liệu khác

- [docs/notice/microservice-split.md](docs/notice/microservice-split.md) — kiến trúc microservice: ranh giới, điểm dễ hiểu nhầm, phần đã/chưa kiểm.
- [contracts/README.md](contracts/README.md) — hợp đồng liên service (endpoint `/internal`, Redis, event SSE, JWT).
- [deploy/DEPLOY.md](deploy/DEPLOY.md) — deploy bằng Docker Compose (hiện mới mô tả stack monolith cũ).
- [docs/overview/](docs/overview/) — [tổng quan](docs/overview/system-overview.md), [bảng DB](docs/overview/db-tables.md), [yêu cầu](docs/overview/requirements.md), [phân rã chức năng](docs/overview/phan-ra-chuc-nang.md) (mô tả monolith cũ).
- [docs/module/](docs/module/) — [chat](docs/module/chat.md), [tư vấn với bác sĩ](docs/module/doctor-consultation.md), [pipeline sách](docs/module/book-ingest-pipeline.md), [đồ thị tri thức](docs/module/knowledge-graph.md) (mô tả monolith cũ; logic nghiệp vụ vẫn đúng).
- [docs/pending/](docs/pending/) — ý tưởng chưa làm; [docs/benchmark/](docs/benchmark/) — đo retrieval.
- [fe/docs/backend-contract.md](fe/docs/backend-contract.md) — hợp đồng REST + SSE với FE.
- `archive/core/` — monolith cũ: [kiến trúc agent](archive/core/app/kien-truc-agent.md), [kiến trúc memory](archive/core/app/kien-truc-memory.md), [pipeline](archive/core/pipeline/document_ingest/README.md), [benchmark](archive/core/benchmark/).
