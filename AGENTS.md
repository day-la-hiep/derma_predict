# AGENTS.md — Derma Hospital

Hướng dẫn cho Agent / Gemini khi làm việc trong repo này.

## 0. Bối cảnh & phạm vi

- Đây là **đồ án tốt nghiệp**, không phải sản phẩm production. Ưu tiên: đúng nghiệp vụ, flow đi thông
  suốt từ đầu đến cuối, dễ giải thích khi bảo vệ. Không cần tối ưu hiệu năng, hardening, scale,
  hay viết test phủ kín.
- Vẫn giữ những thứ không thương lượng: không để lộ secret, không commit `.env`, không làm hỏng dữ liệu
  đã nhập (migration phải giữ dữ liệu), và kết quả AI luôn ghi rõ **không phải chẩn đoán y khoa**.
- Nếu cần chọn giữa "làm gọn để demo chạy được" và "làm đúng kiến trúc lớn", ưu tiên cái chạy được
  và giải thích được, rồi ghi chú phần còn thiếu.

## 1. Repo gồm 2 hệ thống

| Hệ thống | Mô tả | Đọc thêm |
|---|---|---|
| **Chat tư vấn da liễu** | FE chat + Core API + Agent Worker (LangGraph) tra guideline, knowledge graph, phân loại ảnh da | `README.md`, `docs/overview/system-overview.md`, `archive/core/app/kien-truc-agent.md` |
| **Pipeline số hoá sách giáo khoa** (`document_ingest`) | Admin upload PDF → OCR/đọc chữ → AI đọc mục lục (người duyệt) → cắt chunk theo mục lục → nạp Qdrant | `archive/core/pipeline/document_ingest/README.md` |

Cấu trúc thư mục:

```
fe/        Next.js App Router: /chats (chat), /doctor (ca tư vấn, hồ sơ), /doctor/documents (pipeline admin), /doctor/graph-schema
archive/core/      FastAPI (app/), agent LangGraph (agent/), pipeline (pipeline/document_ingest/),
           migrations Alembic (migrations/), dữ liệu nạp (data_ingest/)
deploy/             docker-compose.yml (hạ tầng dev), docker-compose.services.yml (6 service), docker-compose.prod.yml (core cũ), DEPLOY.md
ml/                 model/ (checkpoint CNN), notebook/ (huấn luyện), data/ (dataset, không theo dõi git)
report/             báo cáo đồ án: bao_cao_latex/ (LaTeX), vp_derma/ (Visual Paradigm), thi_t_k_database.md
scripts/            tiện ích: init-service-databases.sh, reseed-user-data.sh, transfer-data.sh
docs/      tài liệu kiến trúc + hướng dẫn chung; docs/notice/ = các lưu ý dễ bỏ sót,
           docs/pending/ = ý tưởng / hướng mở rộng chưa làm (xem mục 8)
tmp/       nháp / kế hoạch tạm (không theo dõi git)
```

## 2. Chạy dự án

> **Kiến trúc hiện tại là microservice** (các thư mục `<tên>_service/` ở gốc repo, xem `docs/notice/microservice-split.md`
> và skill `derma-microservice-migration`). `archive/core/` là monolith cũ, đóng băng: makefile không còn target cho nó; skill
> `derma-core-conventions`, `derma-pipeline-conventions`, `run-core`, `experiment-agent-flow` và phần lớn `docs/` mô tả core cũ.

```bash
make infra          # hạ tầng: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO (deploy/docker-compose.yml)
make services-db    # tạo 5 database identity/consultation/clinical/knowledge/ai (chạy lại không sao)
make knowledge-migrate   # alembic cho database knowledge (các service Spring tự chạy Flyway khi khởi động)
make gateway        # :3040  (mỗi lệnh dưới đây một terminal)
make identity       # :3051
make consultation   # :3052
make clinical       # :3053
make knowledge      # :3054
make knowledge-worker    # worker pipeline sách (không chạy thì nút "Chạy" ở /admin/documents không có tác dụng)
make ai             # :3055
make frontend       # Next.js :3010, gọi qua gateway :3040
make reindex-cases  # nạp lại Qdrant + đồ thị từ báo cáo kết luận (knowledge đang chạy)
make services-up    # hoặc chạy cả 6 service + worker bằng Docker (make services-build trước)
make test           # test 4 service Spring + shared + ai; make knowledge-test chạy riêng (2 test graph_schema lỗi từ trước)
```

- Spring dùng `./mvnw` (Java 21), Python dùng `uv` (venv tại `<tên>_service/.venv`). `ai_service/.env` và `knowledge_service/.env` chứa key LLM/Qdrant (đã gitignore).
- Tài khoản mẫu (migration Flyway của identity): `user-1`, `doctor-1`, `admin-1`, mật khẩu `123456`.
- Migration mới: Spring dùng file Flyway `src/main/resources/db/migration/V<n>__*.sql` (viết tay, **đọc lại** trước khi chạy); knowledge dùng `uv run alembic revision`. Không để autogenerate drop/create bảng có dữ liệu.

## 3. Luồng nghiệp vụ chính

### 3.1 Chat tư vấn
1. FE gửi tin nhắn tới Core (REST) → Core ghi `messages`, publish "turn request" lên RabbitMQ.
2. Agent Worker chạy LangGraph (Turn → Step → Reasoning), gọi tool (guideline, KG, ảnh), publish
   từng bước lên Redis Pub/Sub.
3. Core forward nguyên văn event qua SSE (`/conversations/{id}/stream`) cho FE hiển thị realtime.
4. Kết quả cuối quay về Core qua RabbitMQ, Core ghi Postgres. Chỉ Core ghi Postgres.
5. Khi thiếu thông tin, agent dùng `interrupt()` để hỏi người dùng; người dùng trả lời để resume.

### 3.2 Pipeline số hoá sách (admin)
Các bước theo thứ tự, mỗi bước phải được người duyệt **approve** trước khi bước sau chạy:

| Bước (`stage`) | Làm gì | LLM |
|---|---|---|
| `ingest` | PDF → chữ theo trang (`pages.jsonl`) | không |
| `toc` | AI đọc trang mục lục → cây mục; người duyệt sửa qua override | có |
| `chunks` | cắt đoạn theo khung mục lục (`chunks.jsonl`) | không |
| `index` | embedding (OpenRouter) + nạp Qdrant | không |

- Trạng thái: `not_started → running → pending_review → approved`; `failed`/`cancelled`; `stale`
  khi bước phía trước chạy lại. Thứ tự và phụ thuộc: `app/models/document_stage.py::STAGES`.
- Core chỉ ghi `running` rồi publish `document_ingest_queue`; **Ingest Worker** (`app/workers/document_ingest_worker.py`, `make ingest-worker`) chạy bước. Dừng qua Redis; FE poll `GET /admin/documents/{id}` để xem tiến độ.
- Sửa tay của người duyệt lưu trong `document_overrides` (không ghi đè kết quả máy).

### 3.3 Lưu trữ tài liệu
- **Postgres**: record `documents` (metadata + cột `profile` JSON), `document_stages`,
  `document_overrides`.
- **MinIO** (bucket `MINIO_DOCUMENTS_BUCKET`): mọi file của một tài liệu nằm dưới `document/<id>/`
  (`source.pdf`, `pages.jsonl`, `toc.json`, `chunks.jsonl`, `logs/`...). `<id>` là UUID do DB sinh.
- **Qdrant**: một point cho mỗi chunk, payload có `document_id`.
- Upload: file đi qua Core (stream vào thư mục tạm, kiểm tra `%PDF` và kích thước ≤ 500 MB), rồi
  `DocumentRepository.create` ghi record + file trong một luồng, lỗi thì rollback DB và xoá file.

## 4. Kiến trúc & quy ước cần nhớ

- **Entity nghiệp vụ** ở `archive/core/app/dto/base/` (`Document`, `File`, `DocumentStage`, `DocumentChunk`, ...)
  khác với ORM (`app/models/`) và DTO wire (`app/dto/request|response/`). **Đổi `dto/base` phải hỏi
  người dùng duyệt trước** rồi mới cascade sang models/repo/service.
- **Repository là stateless**: `DocumentRepository` nhận `document_id` trực tiếp. Override nằm ở
  `DocumentOverrideRepository` (field `repo.overrides`). Không có object "mở sẵn 1 tài liệu".
- **`pipeline/` chỉ làm biến đổi dữ liệu.** Stage nhận `StageContext` (`document_id`, `files`,
  `meta()`, `overrides()`, `log()`, `progress()`), không import `app.services`/`app.repositories`.
- **Service** (`DocumentService`, `DocumentIngestPipelineService`) điều phối nghiệp vụ;
  **API** (`app/api/document_api.py`) chỉ map request/response.
- Route admin: `/api/v1/admin/documents/*`, mục lục của một tài liệu ở `/documents/{id}/toc`.
  Stage `toc` và `toc.json` là dữ liệu mục lục, tên đó đúng — đừng đổi.
- Lỗi người dùng sửa được → `StageError` / `InvalidError` (hiển thị nguyên văn trên UI).
- Tên và comment: Python dùng snake_case; docstring và comment **tiếng Việt**, giải thích **vì sao**,
  không mô tả **cái gì** đã rõ trong code. Không viết docstring nhiều đoạn.

## 5. Kỹ năng & quy ước thư mục

Khi làm việc trong một khu vực, tham khảo các quy ước chi tiết:
- `archive/core/app/`: endpoint, DTO, model, service, tool, middleware, prompt agent.
- `archive/core/pipeline/document_ingest/`: quy ước pipeline xử lý PDF, OCR, chunking, indexing.
- `fe/`: trang Next.js, component, hook, store, SSE event.

Quy tắc dùng chung:
- Quy ước `dto/base` (entity nghiệp vụ) nằm trong `derma-core-conventions`; đổi `dto/base` vẫn phải hỏi duyệt trước.
- Khi có mâu thuẫn giữa các tài liệu, hướng dẫn chuyên biệt cho từng module được ưu tiên.
- Nếu đổi quy ước (tên module, route, cấu trúc thư mục), cập nhật tài liệu tương ứng cùng lúc với code.

## 6. Việc hay làm trong đồ án

- Thêm một **nghiệp vụ mới** thường là: entity/DTO (`dto/base` — hỏi trước) → model + migration →
  repository → service → endpoint → màn hình FE. Làm trọn một flow rồi mới mở rộng.
- Khi demo, dữ liệu mẫu nằm ở `archive/core/data_ingest/`; đặt lại dữ liệu người dùng bằng `make reseed-users`.
- Ghi chú các điểm **chưa làm / đơn giản hoá có chủ ý** (ví dụ: DB và MinIO không cùng transaction
  thật, không có tài liệu người dùng đăng nhập theo quyền, chưa có job dọn file mồ côi) vào mục
  "Hạn chế" khi viết báo cáo, không cần sửa ngay.

## 7. Hạn chế đã biết (đồ án)

- Không có auth đa người dùng cho khu admin (API chưa kiểm tra JWT phía server).
- Upload PDF đi qua Core; chưa có presigned upload trực tiếp lên MinIO.
- Không có job dọn object MinIO mồ côi khi rollback thất bại.
- Chưa có tài liệu hướng dẫn triển khai cho pipeline; `deploy/DEPLOY.md` chỉ mô tả chat.
- Kết quả AI chỉ là gợi ý hỗ trợ, không phải chẩn đoán; guideline đang chờ bác sĩ duyệt.

## 8. Khi làm việc với Agent / Gemini

- Trả lời ngắn gọn, bằng tiếng Việt. Thuật ngữ kỹ thuật giữ nguyên tiếng Anh.
- Thay đổi nhỏ, rõ ràng: sửa đúng chỗ cần sửa, không refactor kèm theo.
- Trước khi báo "xong": chạy pyright + test liên quan (backend) hoặc `pnpm tsc --noEmit` (frontend). Với thay đổi UI, nói rõ nếu chưa test trên trình duyệt.
- **Ghi lưu ý vào `docs/notice/`**: khi làm việc phát sinh điểm dễ bỏ sót (hành vi không hiển nhiên, quy tắc
  phân quyền/phạm vi, giới hạn, rủi ro, việc chưa làm có chủ ý), chọn lọc và ghi vào một file theo chủ đề trong
  `docs/notice/` (mẫu: `doctor-chat-access.md`: quy tắc, lý do, điểm cần lưu ý). Chỉ ghi điều thật sự dễ gây hiểu
  nhầm, không ghi chuyện hiển nhiên; file đã có thì cập nhật, không tạo trùng. Không tự sửa AGENTS.md/skill chỉ để
  mô tả thay đổi, trừ khi được yêu cầu.
- **Ghi ý tưởng / hướng mở rộng vào `docs/pending/`**: khi phát sinh ý tưởng, hướng mở rộng hoặc việc cố ý chưa
  làm (ví dụ cắt vùng tổn thương trước khi cho CNN), ghi vào một file theo chủ đề trong `docs/pending/` thay vì
  cài đặt luôn hay để mất. Tiêu đề `# [Pending] ...`; mẫu: `kb-enrichment.md` (vấn đề, luồng đề xuất, câu hỏi cần
  chốt, phụ thuộc). File đã có thì cập nhật, không tạo trùng. Đây là ghi chú, không phải cam kết; không tự làm
  theo nếu chưa được yêu cầu. Khác `docs/notice/`: notice = điều dễ hiểu nhầm của hệ thống hiện tại, pending =
  thứ chưa có.
- Không tự commit, không push, không chạy lệnh huỷ dữ liệu (`docker compose down -v`, xoá bucket, `DROP`)
  nếu chưa được hỏi.
