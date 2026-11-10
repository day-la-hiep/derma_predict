---
name: derma-microservice-migration
description: Conventions for migrating the Derma `archive/core/` modular monolith into gateway + 5 services (identity, consultation, clinical, knowledge, ai) under gốc repo (`<tên>_service/`) — step order, aggregate boundaries, soft-id references instead of cross-service FKs, HTTP clients, per-service database, shared library, folder layout, Spring-vs-Python split, and the done-checklist per step. Use whenever the user mentions microservice, tách service, gateway, identity/consultation/clinical/knowledge service, gốc repo (`<tên>_service/`), tách database, cắt FK, hay todo/plan trong `tmp/plan`, or asks where a piece of code/table should live after the split — even if they don't say "convention".
---

# Chuyển `archive/core/` sang microservice

**Nguồn sự thật là `tmp/plan/`**, không phải `docs/pending/`:
- Thiết kế: `tmp/plan/2026-11-09-microservice-split.md` (service = bounded context, aggregate, bất biến)
- Kế hoạch: `tmp/plan/2026-11-09-ke-hoach-trien-khai-service.md` (giai đoạn A–E, hiện trạng đo được, rủi ro)
- Todo (đánh dấu tiến độ ở đây): `tmp/plan/todo/2026-11-09-trien-khai-service.md` (bước 0–8)

Skill này là **quy ước làm từng bước**; khi mâu thuẫn với plan/todo thì plan/todo thắng, và phải sửa skill.
Quy ước tầng code theo `derma-core-conventions` (api → service → repository). Đây là đồ án: ưu tiên
flow demo chạy được và dễ giải thích; không saga, service mesh, tracing, event sourcing, outbox thật
(cần thì ghi `docs/pending/`).

## Quy tắc vàng: `archive/core/` đóng băng, code mới vào gốc repo (`<tên>_service/`)

- **Không sửa, không xoá, không `git mv` code trong `archive/core/`** (cả `archive/core/app`, `archive/core/agent`, `archive/core/pipeline`, `migrations/`, `makefile` target cũ). `archive/core/` là bản chạy cũ và là đặc tả để đối chiếu; `make backend/worker/ingest-worker` vẫn chạy như trước.
- Mọi code mới nằm trong `<tên>_service/`. Service Python: **sao chép** (`cp -r`) file cần từ `archive/core/` sang rồi sửa bản trong gốc repo (`<tên>_service/`); service Spring: viết mới theo `archive/core/` làm đặc tả.
- Muốn đổi cấu trúc/tên/sạch lỗi thì làm ở bản trong gốc repo (`<tên>_service/`), không quay lại sửa `archive/core/`. Lỗi sẵn có của `archive/core/` chỉ ghi vào todo.
- Quy ước tầng, tên hàm, ít wrapper áp dụng cho code trong gốc repo (`<tên>_service/`), không áp dụng ngược cho `archive/core/`.
- Dữ liệu cũ chỉ **đọc/copy** (`pg_dump`, `reindex`), không sửa hay xoá DB/bucket cũ.

## Nhịp làm việc

1. Mở todo, làm **đúng một mục** (hoặc một cụm con) tiếp theo, không nhảy bước.
2. Nhịp: sửa → test liên quan → `pyright` → chạy thử. Xong mới tick `[x]` trong todo.
3. Mỗi giai đoạn kết thúc, hệ thống vẫn chạy end-to-end (strangler). Không để repo dở sang bước sau.
4. Phát hiện mới (lệch kiến trúc, lỗi sẵn có) ghi vào mục todo liên quan, không sửa lan.
5. Việc cần bạn duyệt (bước 0, `dto/base`, `DROP`...) dừng và hỏi, không tự quyết.

## Service và ranh giới

| Service | Cổng | Aggregate chính |
|---|---|---|
| gateway (Spring) | 3050 | — (proxy theo prefix, CORS, JWT thô; SSE/WebSocket pass-through) |
| identity (Spring) | 3051 | `User`(→Doctor, Admin), `PatientProfile` |
| consultation (Spring) | 3052 | `Conversation`(→Message), `ConsultationSession`(→VideoCall, PreConsultationReport) |
| clinical (Spring) | 3053 | `ClinicalEpisode`, `ClinicalFact`, `Appointment`(→Encounter), `FinalizeReport` |
| knowledge (Python) | 3054 | `Document`(→Stage, Override), `GraphSchema` |
| ai (Python) | 3055 | không aggregate; DB riêng `ai` chỉ chứa schema `langgraph` (memory dài hạn + checkpoint hội thoại) |

- **Service = ranh giới triển khai; aggregate = ranh giới nhất quán** trong code. Mỗi aggregate một root, có repository riêng.
- Aggregate tham chiếu nhau **chỉ bằng id**, kể cả cùng service; không join chéo aggregate. FK trong DB chỉ giữ khi cùng service.
- Mỗi transaction ghi một aggregate; đụng nhiều aggregate đi qua orchestrator trong service (hoặc event nếu qua service khác).
- Một service ghi mỗi bảng. Không service nào đọc bảng của service khác; `ai` không đọc bảng của service khác (chỉ dùng DB riêng của nó).
- Retrieval và Qdrant/Neo4j đều ở `knowledge` (sách, tri thức, ca tham khảo, PJKG); `clinical` chỉ publish sự kiện.
- `File` không phải aggregate: mỗi service giữ bảng `files` riêng, dùng chung thư viện MinIO.

## Thứ tự (theo todo)

0 chốt thiết kế → 1 nền tảng trong gốc repo (`<tên>_service/`) (shared + hợp đồng) → 2 knowledge → 3 identity → 4 ai → 5 consultation → 6 clinical → 7 gateway + hạ tầng → 8 tài liệu & dọn dẹp.
Tách ít phụ thuộc trước (knowledge) để rút ra khuôn rồi áp cho phần khó.

## Cắt phụ thuộc

**Bước 1 là nền tảng trong gốc repo (`<tên>_service/`), không đụng `archive/core/`:**
- `shared/` (Python, cho `knowledge` và `ai`): sao chép từ `archive/core/` phần không mang nghiệp vụ (settings cơ sở, `log.py`, JWT verify, client Redis/RabbitMQ/MinIO, lỗi chuẩn). Nghiệp vụ dùng chung hai service thì thuộc về một service, service kia gọi qua client.
- Gọi chéo service dùng **client HTTP cụ thể** (`httpx`, timeout, log lỗi), đặt ở service gọi: `KnowledgeClient`, `ClinicalClient`, `ConsultationClient`, `IdentityClient`. Không Protocol, không bản in-process (không còn monolith để gọi in-process); mỗi client là class mỏng một-lớp, không bọc thêm.
- `ai_service/` (tên cũ `agent`) sao chép từ `archive/core/agent` rồi bỏ mọi `import app.*`: thay `from app.api.deps import ...` bằng client; `context/builder.py` và `handler/consultation_report.py` không đọc Postgres (context nằm sẵn trong `agent_request`). Việc này làm ở bước 4, trong `services/agent/`.
- `dto/base` mới theo `*_id` ở các chỗ cắt qua aggregate đặt trong từng service; **phải được người dùng duyệt trước**. `archive/core/app/dto/base/` giữ nguyên.

**Cắt FK chéo service** (danh sách trong plan, mục "Cắt phụ thuộc trong code và DB"): giữ cột + index làm id mềm, bỏ `ForeignKey`.
Mỗi service có migration khởi tạo **viết tay và đọc lại**; không để autogenerate drop/create bảng có dữ liệu. `ondelete CASCADE/SET NULL` mất theo FK → xoá/cập nhật tường minh trong service sở hữu. Join chéo đổi thành hai bước qua client.

## Giao tiếp

| Nhu cầu | Cách dùng |
|---|---|
| Cần kết quả ngay từ service khác | REST nội bộ `/internal/...` (không qua gateway, FE không gọi) qua client HTTP của service gọi |
| Việc nền (ai chạy lượt, index ca) | cũng REST: `POST /internal/turns` (202) rồi callback `/internal/turns/{id}/result`; `POST knowledge /internal/cases` + reindex bù; không RabbitMQ xuyên service |
| Realtime tới FE | Redis **Streams** `conversation:events:{id}` (SSE `XREAD`, có replay); Pub/Sub chỉ cho inbox/call tạm thời; không dùng để gọi nghiệp vụ |
| Nội bộ knowledge | RabbitMQ `document_ingest_queue` (Python ⇄ Python) |

- Mọi `/internal/*` kiểm header `X-Internal-Key` (không qua gateway); ai ghi thẳng vào chủ dữ liệu (lâm sàng → clinical, câu trả lời → consultation); agent kéo context bằng id; trạng thái lượt chạy nằm trong DB (tin `queued`/`question`), không khoá Redis.
- Tên stream/channel là hằng số, không hardcode; địa chỉ service lấy từ settings.
- **Xác thực:** identity phát JWT; JWT khoá chung, **mỗi service tự verify** (gateway chỉ xác thực thô). Giữ nguyên route, JSON snake_case, envelope `ApiResponse` để FE không đổi (FE vẫn gọi cổng 3050).
- SSE qua gateway không được buffer; test sớm.

## Dữ liệu và hạ tầng

- Một Postgres, 5 database (`identity`, `consultation`, `clinical`, `knowledge`, `ai`), script init tạo; mỗi service Alembic riêng, tên bảng giữ nguyên.
- Chỉ migrate dữ liệu **sách giáo khoa + Qdrant** (knowledge: `pg_dump` bảng document/graph, giữ key MinIO `document/<id>/` và payload Qdrant `document_id`, kiểm `make reindex-qdrant dry=1`, so số point). Còn lại seed tối thiểu (user-1, bác sĩ, admin).
- Không `DROP`/`docker compose down -v`/xoá bucket khi chưa hỏi. Không đổi tên route/stage đã chốt (`/documents/{id}/toc`, stage `toc`).
- Mỗi service: `pyproject.toml` (Spring: `pom.xml`), `deps.py`, Alembic (Spring: Flyway), `Dockerfile`, cổng riêng; thêm `make <service>`. CNN 44MB chỉ vào image `agent`.

## Cấu trúc thư mục

```
services/
  shared/  gateway/  identity/  consultation/  clinical/  knowledge/  ai/
```

Khuôn một service Python (`<tên>_service/`; service Spring xem mục Ngôn ngữ):

```
app/
  api/            <tài nguyên>_api.py          chỉ map request/response
  services/       <tài nguyên>_service.py      nghiệp vụ
  repositories/   <tài nguyên>_repository.py   truy vấn DB
  models/  dto/  config/
  deps.py         lắp dependency, ngắn
main.py  migrations/  alembic.ini  Dockerfile  pyproject.toml  tests/
```

- Giữ hậu tố `_api` / `_service` / `_repository`; mỗi tài nguyên một bộ ba file cùng tên gốc; không tạo thư mục con khi dưới ~10 file.
- Phần đặc thù đặt cạnh `app/`: `knowledge/pipeline/` (sao chép từ `archive/core/pipeline`, `graph_base`, `data_ingest`), `agent/` (sao chép từ `archive/core/agent`), `workers/`.
- Sao chép (`cp`), không `git mv`; mỗi lần một cụm rồi chạy pyright + test của service. Skill `derma-core-conventions` mô tả `archive/core/` cũ nên giữ nguyên; quy ước riêng cho gốc repo (`<tên>_service/`) nằm ở skill này.

## Ngôn ngữ: Spring cho nghiệp vụ, Python cho AI (đã chốt)

| Service | Ngôn ngữ |
|---|---|
| gateway | Spring Boot (Spring Cloud Gateway) |
| identity, consultation, clinical | Spring Boot |
| knowledge, ai | Python |

- **Viết thẳng bằng Java**, lấy `archive/core/` làm đặc tả; không dựng bản Python trung gian. `archive/core/` nguyên vẹn và vẫn phục vụ cho tới khi gateway trỏ sang service mới (strangler); sau đó vẫn giữ lại làm bản tham chiếu. Làm `identity` trước, `consultation` (rủi ro cao nhất: SSE, AMQP, Redis, WebSocket) sau.
- **Phần AI không viết bằng Java.** Qdrant ca tham khảo + Neo4j PJKG thuộc `knowledge`: `clinical` gọi `POST knowledge /internal/cases` sau khi chốt (có `/internal/cases/reindex` bù), `knowledge` phục vụ `/internal/similar-cases`. Service Spring không có client Qdrant/Neo4j.
- **Hợp đồng giữa hai ngôn ngữ** (todo 1.5): `openapi.json` (route, JSON snake_case, envelope `ApiResponse`), endpoint `/internal` + schema event Redis Stream (xem `contracts/README.md`), JWT cùng khoá/thuật toán/claim (`sub`, `role`, `username`, `type`), bcrypt giữ nguyên (`BCryptPasswordEncoder`). Đổi một phía phải đổi phía kia cùng lúc.
- **`shared/` chỉ cho Python.** Phía Spring tự có JWT verify và envelope; không dựng thư viện Java dùng chung khi chưa có ≥ 2 service cần y hệt.
- **Migration:** Flyway `V1__init.sql` viết tay từ models và đọc lại (không migrate dữ liệu cũ, chỉ seed); `ddl-auto=validate`, Hibernate không tự tạo/sửa bảng. Alembic chỉ còn cho `knowledge`.
- **Client giữa service:** Python (ai) gọi Spring bằng client HTTP trong `IdentityClient`/`ClinicalClient`/`ConsultationClient`; Spring gọi nhau và gọi `knowledge` bằng `RestClient`. Mỗi lời gọi có timeout và log lỗi.
- **Khuôn Spring** map 1-1 với khuôn Python, cùng ba tầng:

```
<tên>_service/
  src/main/java/vn/derma/<tên>/
    controller/   (= api)  <TàiNguyên>Controller
    service/               <TàiNguyên>Service
    repository/            <TàiNguyên>Repository  (Spring Data JPA)
    entity/  dto/ (record)  config/
  src/main/resources/ application.yml, db/migration/
  pom.xml hoặc build.gradle, Dockerfile, src/test/
```

- **Bẫy đã gặp (Spring Boot 4 / Jackson 3):** `RestClient.Builder` chỉ có bean khi thêm `spring-boot-starter-restclient` (test mock client sẽ che lỗi này: luôn có một test nạp context với client thật); record/`Optional` không phân biệt "không gửi" với "gửi null" (Jackson 3 gán `Optional.empty` cho trường vắng), PATCH cần xoá trường bằng null thì dùng class + setter ghi nhận có gửi; file `application.yml` trong `src/test/resources` che hẳn file chính, dùng `application.properties` cho test; sau khi xoá/đổi file resource phải `./mvnw clean`.
- **Bẫy tích hợp đã gặp:** `HttpClient` của JDK mặc định thử nâng lên h2c và làm **mất body POST** khi gọi server Python (uvicorn) → ép HTTP/1.1 cho mọi `RestClient` gọi service khác (`common/Http11.java`); Jackson 3 coi trường `boolean` nguyên thuỷ trong record là bắt buộc (400 khi FE không gửi) → dùng `Boolean`; test mock client che lỗi khởi động/mạng → luôn chạy thử thật một lần giữa hai service.
- **Java ít wrapper:** gọi Spring Data JPA thẳng, không bọc thêm lớp DAO; DTO dùng `record`; Lombok: `@AllArgsConstructor` thay constructor tiêm dependency (class chỉ có field `private final`), `@Slf4j` thay logger; entity giữ field public; MapStruct (`mapper/`, `defaultComponentModel=spring`) cho phần ghép entity → DTO, trường dẫn xuất tính ở service rồi truyền vào mapper; tên trùng giữa hai nguồn phải chỉ rõ `source`; không tầng ngoài `controller → service → repository`. Tên phương thức là động từ camelCase (`getPatientProfileByUserId`).
- Dev: `make identity|consultation|clinical|gateway` (chạy Spring) cạnh `make knowledge|ai`.

## Viết code dễ đọc, hạn chế wrapper

- **Gọi thẳng, không bọc.** Không thêm hàm/class chỉ để chuyển tiếp lời gọi (`XxxManager`, `XxxHelper`, `XxxFacade`, client bọc client). Chỉ tách hàm khi có ≥ 2 chỗ dùng **và** hàm đó thêm logic (retry, map lỗi, đổi DTO).
- **Hàm làm một việc, đọc từ trên xuống.** Cần nhảy qua > 2 file để hiểu một endpoint là dấu hiệu thừa lớp.
- **Không tổng quát hoá sớm:** không interface/abstract/registry khi chỉ có một cài đặt; không tham số "cho sau này".
- **Tên rõ nghĩa thay cho comment**; comment tiếng Việt chỉ nói *vì sao* ở đúng dòng khó hiểu.
- **Tên hàm là động từ** (`get_`, `build_`, `create_`, `update_`, `find_`, `send_`, `check_`...): `get_patient_profile_by_user_id`, không phải `patient_profile`; hàm trả `bool` dùng `is_/has_`; class là danh từ. Java dùng camelCase cùng quy tắc.
- Gọi sang service khác đi qua client HTTP cụ thể, đặt tên nói rõ (`get_user_name_from_identity`) để thấy chỗ có độ trễ/lỗi mạng.
- `except` luôn `logger.warning/error` kèm nguyên nhân.

## Checklist "xong một bước"

- [ ] Làm đúng mục todo đang mở; tick trong `tmp/plan/todo/2026-11-09-trien-khai-service.md`.
- [ ] `archive/core/` không bị sửa (`git diff --stat -- core` rỗng); pyright của service mới không có lỗi; test liên quan pass; service Spring: `mvn test`/`gradle test` + khớp `openapi.json`.
- [ ] Chạy lại flow demo liên quan end-to-end (chat; upload PDF → index; đặt lịch → khám → chốt báo cáo).
- [ ] Migration đã đọc lại, không mất dữ liệu; còn đường quay lại tới hết bước sau.
- [ ] Code mới không có wrapper chỉ chuyển tiếp; hàm đặt tên động từ.
- [ ] Cập nhật skill `derma-*` liên quan + `rsync` sang `.agents/skills/`, `diff -rq` sạch (trừ `__pycache__`).
- [ ] Điều dễ hiểu nhầm ghi `docs/notice/`; đơn giản hoá có chủ ý ghi vào "Hạn chế" (không transaction phân tán, không outbox, ranh giới aggregate chỉ bằng quy ước).
- [ ] Nói rõ phần UI chưa test trên trình duyệt (nếu có).

## Hỏi người dùng trước khi làm

- Bước 0: duyệt bảng service/aggregate, `dto/base` mới theo `*_id`, và hệ quả chuyển Qdrant ca/PJKG sang `knowledge`.
- Mọi đổi `app/dto/base/`.
- Chuyển file hàng loạt hoặc cắt FK nhóm có dữ liệu thật: trình bày danh sách rồi mới làm.
- Lệnh huỷ dữ liệu (`DROP`, `docker compose down -v`, xoá bucket).
