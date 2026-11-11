# Hướng dẫn chạy local (không cần make)

Chạy toàn bộ hệ thống trên máy cá nhân: hạ tầng bằng Docker, 6 service + FE chạy trực tiếp bằng lệnh gốc (`docker`, `mvnw`, `uv`, `pnpm`). Dùng được với terminal, VS Code, IntelliJ, trên Linux, macOS và Windows (PowerShell). Không cần cài `make`.

Mọi lệnh bên dưới chạy từ **thư mục gốc repo**, trừ khi có `cd`.

## 1. Cần cài

| Công cụ | Phiên bản | Kiểm tra |
|---|---|---|
| Docker + Docker Compose | bản mới | `docker compose version` |
| Java (JDK) | 21 | `java -version` |
| uv (Python) | bản mới | `uv --version` |
| Node + pnpm | Node 20+ (đã thử với 24), pnpm 11 (`packageManager` trong `fe/package.json`) | `node -v`, `pnpm -v` |

Khác biệt khi dùng Windows PowerShell:
- Chạy Maven wrapper bằng `.\mvnw.cmd` thay cho `./mvnw`.
- Ký tự `\` xuống dòng của bash không dùng được; viết mỗi lệnh trên một dòng.
- Biến môi trường đặt bằng `$env:TEN="giatri"` (không dùng `TEN=giatri lenh`).
- Không có `sh`, `curl -X` dạng bash: dùng `curl.exe` hoặc `Invoke-RestMethod`.
- Cài Docker Desktop và bật WSL2 backend. Nếu Git bị đổi CRLF thì Linux/WSL báo `\r: command not found`: thêm `.gitattributes` với `*.sh text eol=lf` và `mvnw text eol=lf`.

## 2. Cấu hình (làm một lần)

File `.env` không có trong git. Tự tạo hoặc xin từ người trong nhóm.

| File | Cần có | Ghi chú |
|---|---|---|
| `ai_service/.env` | `OPENROUTER_API_KEY`, `AGENT_MODEL`, `QDRANT_API_KEY` | **Không đặt `REDIS_DB` khác 0.** ai_service ghi event chat vào Redis, consultation đọc ở db0; lệch db thì chat không stream. |
| `knowledge_service/.env` | `OPENROUTER_API_KEY`, `QDRANT_*`, `NEO4J_*`, `MINIO_*` | Giá trị mặc định khớp `deploy/docker-compose.yml`. |
| `fe/.env.local` | `BACKEND_URL=http://localhost:3040`, `NEXT_PUBLIC_API_URL=/api/v1`, `NEXT_PUBLIC_USE_MOCK=false` | Mẫu: `fe/.env.local.example`. `BACKEND_URL` mặc định đã là `:3040`. |
| `.env` (gốc) | `OPENROUTER_API_KEY` | Chỉ cần khi chạy toàn bộ bằng Docker (mục 7). |

4 service Spring không cần `.env`: mặc định trong `application.yml` đã khớp hạ tầng Docker (Postgres `postgres/postgres`, Redis `localhost:6379`...). Muốn đổi thì đặt biến môi trường (`DATABASE_URL`, `REDIS_HOST`, `INTERNAL_API_KEY`...).

## 3. Cài phụ thuộc và khởi tạo (lần đầu)

**Bước 1. Hạ tầng** (Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO, coturn):

```bash
docker compose -f deploy/docker-compose.yml up -d
```

**Bước 2. Tạo 5 database** trong Postgres đang chạy (chạy lại cũng được; database đã có thì báo `already exists`, bỏ qua):

```bash
docker exec derma-postgres psql -U postgres -c "CREATE DATABASE identity"
docker exec derma-postgres psql -U postgres -c "CREATE DATABASE consultation"
docker exec derma-postgres psql -U postgres -c "CREATE DATABASE clinical"
docker exec derma-postgres psql -U postgres -c "CREATE DATABASE knowledge"
docker exec derma-postgres psql -U postgres -c "CREATE DATABASE ai"
```

**Bước 3. Python:** tạo `.venv` cho từng service (uv đọc `pyproject.toml`):

```bash
cd knowledge_service && uv sync
cd ../ai_service && uv sync
cd ../shared && uv sync
cd ..
```

**Bước 4. Migration database `knowledge`** (4 service Spring tự chạy Flyway khi khởi động, kể cả nạp tài khoản mẫu cho identity):

```bash
cd knowledge_service && uv run alembic upgrade head && cd ..
```

**Bước 5. FE:**

```bash
cd fe && pnpm install && cd ..
```

**Bước 6. MinIO** (console http://localhost:9001, user `minio`, mật khẩu `minio123`): ảnh đính kèm cần bucket `derma-attachments`. Consultation không tự tạo bucket; nếu upload ảnh báo lỗi bucket thì tạo bucket này trên console.

Linux/macOS: nếu `./mvnw` báo `Permission denied` thì `chmod +x */mvnw`.

## 4. Chạy các service

Thứ tự khuyến nghị, **mỗi lệnh một terminal**:

| # | Service | Cổng | Lệnh |
|---|---|---|---|
| 1 | identity | 3051 | `cd identity_service` rồi `./mvnw spring-boot:run` |
| 2 | consultation | 3052 | `cd consultation_service` rồi `./mvnw spring-boot:run` |
| 3 | clinical | 3053 | `cd clinical_service` rồi `./mvnw spring-boot:run` |
| 4 | knowledge | 3054 | `cd knowledge_service` rồi `uv run python -m app.main` |
| 5 | knowledge worker | - | `cd knowledge_service` rồi `uv run python -u -m app.workers.document_ingest_worker` |
| 6 | ai | 3055 | `cd ai_service` rồi `uv run python -m app.main` |
| 7 | gateway | 3040 | `cd gateway_service` rồi `./mvnw spring-boot:run` |
| 8 | fe | 3010 | `cd fe` rồi `pnpm dev` |

Windows PowerShell: thay `./mvnw` bằng `.\mvnw.cmd`.

Worker (dòng 5) cần để nút "Chạy" ở `/admin/documents` có tác dụng. Mỗi lần đổi `.env` hoặc `.env.local` phải restart service tương ứng, vì giá trị chỉ đọc lúc khởi động.

Mở http://localhost:3010. Tài khoản mẫu, mật khẩu `123456`:

| Tài khoản | Vai trò |
|---|---|
| `user-1` | bệnh nhân (trang `/chats`) |
| `doctor-1` | bác sĩ (trang `/doctor`) |
| `admin-1` | admin (trang `/admin`) |

Kiểm tra nhanh: `curl http://localhost:3040/actuator/health` (PowerShell: `curl.exe`) phải trả `UP`.

## 5. Chạy trong IDE

Mở **thư mục gốc repo** trong IDE.

| Service | Cổng | Chạy bằng |
|---|---|---|
| gateway | 3040 | `GatewayApplication` (Spring) |
| identity | 3051 | `IdentityApplication` |
| consultation | 3052 | `ConsultationApplication` |
| clinical | 3053 | `ClinicalApplication` |
| knowledge | 3054 | `app/main.py` (+ worker) |
| ai | 3055 | `app/main.py` |
| fe | 3010 | `pnpm dev` |

### IntelliJ IDEA

1. `File > Open` thư mục gốc. IntelliJ nhận 4 module Maven (`gateway_service`, `identity_service`, `consultation_service`, `clinical_service`). Nếu chưa nhận: mở `pom.xml` của từng service, chuột phải, **Add as Maven Project**. Project SDK: JDK 21.
2. Chạy từng Spring service: mở class `*Application`, bấm nút run cạnh `main`. Hoặc dùng cửa sổ **Services** để chạy cả 4.
3. Python (knowledge, ai): cần plugin **Python** hoặc PyCharm. Tạo run configuration kiểu **Python**, script `app/main.py`, working directory là `knowledge_service/` hoặc `ai_service/`, interpreter là `.venv` của service (đã tạo ở mục 3 bước 3). Worker: chọn **Module name** `app.workers.document_ingest_worker`, working directory `knowledge_service/`.
4. FE: tạo run configuration kiểu **npm**, package.json `fe/package.json`, command `run`, script `dev`. Working directory là `fe/` nên Next tự đọc `fe/.env.local`; **không đặt biến trong ô Environment** vì nó đè `.env.local`.
5. Gộp thành một nút: **Run > Edit Configurations > + > Compound**, thêm các configuration trên.

### VS Code

Cài extension: **Extension Pack for Java**, **Spring Boot Extension Pack**, **Python**, **Debugpy**. Chọn JDK 21 cho Java.

Các cấu hình hiện có trong `.vscode/` còn trỏ về `core/` cũ, nên thay `.vscode/launch.json` bằng:

```json
{
  "version": "0.2.0",
  "configurations": [
    { "name": "gateway", "type": "java", "request": "launch", "mainClass": "vn.derma.gateway.GatewayApplication", "projectName": "gateway" },
    { "name": "identity", "type": "java", "request": "launch", "mainClass": "vn.derma.identity.IdentityApplication", "projectName": "identity" },
    { "name": "consultation", "type": "java", "request": "launch", "mainClass": "vn.derma.consultation.ConsultationApplication", "projectName": "consultation" },
    { "name": "clinical", "type": "java", "request": "launch", "mainClass": "vn.derma.clinical.ClinicalApplication", "projectName": "clinical" },
    {
      "name": "knowledge", "type": "debugpy", "request": "launch", "module": "app.main",
      "python": "${workspaceFolder}/knowledge_service/.venv/bin/python",
      "cwd": "${workspaceFolder}/knowledge_service", "envFile": "${workspaceFolder}/knowledge_service/.env"
    },
    {
      "name": "knowledge-worker", "type": "debugpy", "request": "launch", "module": "app.workers.document_ingest_worker",
      "python": "${workspaceFolder}/knowledge_service/.venv/bin/python",
      "cwd": "${workspaceFolder}/knowledge_service", "envFile": "${workspaceFolder}/knowledge_service/.env"
    },
    {
      "name": "ai", "type": "debugpy", "request": "launch", "module": "app.main",
      "python": "${workspaceFolder}/ai_service/.venv/bin/python",
      "cwd": "${workspaceFolder}/ai_service", "envFile": "${workspaceFolder}/ai_service/.env"
    }
  ],
  "compounds": [
    { "name": "Tất cả backend", "configurations": ["identity", "consultation", "clinical", "knowledge", "knowledge-worker", "ai", "gateway"] }
  ]
}
```

Trên Windows đổi `.venv/bin/python` thành `.venv/Scripts/python.exe`. `projectName` là tên artifact Maven; nếu VS Code không tìm thấy, xóa dòng đó.

FE: chạy trong terminal của VS Code (`cd fe && pnpm dev`) hoặc thêm task shell vào `.vscode/tasks.json`.

Chọn Python interpreter: `Ctrl+Shift+P > Python: Select Interpreter`, chọn `.venv` của service đang sửa.

### Chỉ dùng text editor

Mở 8 terminal (hoặc dùng `tmux`) và chạy các lệnh ở mục 4 theo thứ tự.

## 6. Reset dữ liệu người dùng về seed ban đầu

Xóa dữ liệu 3 database `identity`, `consultation`, `clinical` rồi nạp lại tài khoản mẫu. **Thao tác này xóa dữ liệu thật**; tắt các service trước khi chạy. Không đụng `knowledge`, `ai`, Qdrant, Neo4j, MinIO.

Linux/macOS/WSL (có `sh`), có hỏi xác nhận:

```bash
sh scripts/reseed-user-data.sh
```

Không có `sh` (PowerShell), làm tay. Lấy danh sách bảng của từng database rồi `TRUNCATE`:

```powershell
foreach ($db in "identity","consultation","clinical") {
  $t = docker exec derma-postgres psql -U postgres -d $db -tAc "SELECT string_agg(quote_ident(tablename), ',') FROM pg_tables WHERE schemaname='public' AND tablename <> 'flyway_schema_history'"
  docker exec derma-postgres psql -U postgres -d $db -c "TRUNCATE $t RESTART IDENTITY CASCADE"
}
Get-Content identity_service/src/main/resources/db/seed/V2__seed_demo.sql -Raw | docker exec -i derma-postgres psql -U postgres -d identity -v ON_ERROR_STOP=1
```

## 7. Chạy bằng Docker (không cần IDE)

Cần `OPENROUTER_API_KEY` trong `.env` ở gốc repo, và đã xong bước hạ tầng + database (mục 3 bước 1, 2).

```bash
docker compose -f deploy/docker-compose.services.yml --env-file .env build
docker compose -f deploy/docker-compose.services.yml --env-file .env up -d
cd fe && pnpm dev          # FE vẫn chạy local, trỏ gateway :3040
docker compose -f deploy/docker-compose.services.yml --env-file .env down   # dừng
```

## 8. Test

```bash
cd identity_service && ./mvnw -q -B clean test
cd consultation_service && ./mvnw -q -B clean test
cd clinical_service && ./mvnw -q -B clean test
cd gateway_service && ./mvnw -q -B clean test
cd shared && uv run python -m unittest tests.test_shared
cd ai_service && uv run python -m unittest discover -s tests -t .
cd knowledge_service && uv run python -m unittest discover -s tests -t .
cd fe && pnpm lint
```

(Mỗi dòng bắt đầu từ thư mục gốc repo; `knowledge_service` còn 2 test `graph_schema` lỗi từ trước.)

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chat gửi được nhưng không stream, tin AI kẹt `queued` | `REDIS_DB` của ai_service khác consultation (db0) | Đặt `REDIS_DB=0` trong `ai_service/.env`, restart ai |
| FE báo `ECONNREFUSED 127.0.0.1:3050` | `BACKEND_URL` còn trỏ core cũ | Đổi sang `http://localhost:3040` trong `fe/.env.local`, restart `pnpm dev` |
| Ảnh trong timeline bệnh nhân 404 | Chưa chạy lại gateway/consultation sau khi thêm `/files/{id}/view` | Restart gateway và consultation |
| Spring không khởi động: `database "x" does not exist` | Chưa tạo database | Chạy lại mục 3 bước 2 |
| Upload ảnh lỗi bucket | Chưa có bucket `derma-attachments` | Tạo trên MinIO console `:9001` |
| Nút "Chạy" ở `/admin/documents` không có tác dụng | Chưa chạy worker | Chạy dòng 5 ở mục 4 |
| `\r: command not found` khi chạy `mvnw`/script | File bị CRLF (Windows) | Thêm `.gitattributes` như mục 1, checkout lại |
| `./mvnw : not recognized` (PowerShell) | PowerShell không chạy script bash | Dùng `.\mvnw.cmd` |
| Đổi `.env` mà không thấy hiệu lực | Giá trị đọc lúc khởi động | Restart service |
| Cổng bị chiếm | Service cũ còn chạy | Linux/macOS: `lsof -ti:<cổng> -sTCP:LISTEN \| xargs -r kill` (chỉ tiến trình của bạn). Windows: `netstat -ano \| findstr :<cổng>` rồi `taskkill /PID <pid> /F` |

## 10. Tài liệu liên quan

- Tổng quan: `docs/overview/system-overview.md`
- Chia service: `docs/notice/microservice-split.md`, `contracts/README.md`
- Triển khai bằng Docker: `deploy/DEPLOY.md`
- Lệnh tắt cho người có `make`: `makefile` ở gốc repo (mỗi target là một lệnh ở các mục trên).
