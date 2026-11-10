.PHONY: infra infra-down services-db services-up services-down services-build test \
        identity consultation clinical gateway knowledge knowledge-worker knowledge-migrate ai frontend \
        identity-test consultation-test clinical-test gateway-test knowledge-test ai-test shared-test \
        reindex-cases data-export data-restore

# ---- hạ tầng (Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO, coturn) ----
infra:
	docker compose -f deploy/docker-compose.yml up -d

infra-down:
	docker compose -f deploy/docker-compose.yml down

# tạo database identity/consultation/clinical/knowledge/ai trong Postgres đang chạy; chạy lại không sao, không đụng database có sẵn
services-db:
	sh scripts/init-service-databases.sh

# xuất / khôi phục 4 volume (postgres, minio, qdrant, neo4j) vào scripts/backup; tắt stack trước (make infra-down)
data-export:
	$(if $(VOL_PREFIX),VOL_PREFIX=$(VOL_PREFIX)) ./scripts/transfer-data.sh export

data-restore:
	$(if $(VOL_PREFIX),VOL_PREFIX=$(VOL_PREFIX)) ./scripts/transfer-data.sh restore

# ---- chạy từng service trực tiếp (mỗi lệnh một terminal): gateway :3040, identity :3051, consultation :3052, clinical :3053, knowledge :3054, ai :3055 ----
gateway:
	cd gateway_service && ./mvnw -q spring-boot:run

identity:
	cd identity_service && ./mvnw -q spring-boot:run

consultation:
	cd consultation_service && ./mvnw -q spring-boot:run

clinical:
	cd clinical_service && ./mvnw -q spring-boot:run

knowledge:
	cd knowledge_service && uv run python main.py

# worker chạy các bước pipeline sách; không chạy thì bấm "Chạy" ở /admin/documents không có tác dụng
knowledge-worker:
	cd knowledge_service && uv run python -u -m app.workers.document_ingest_worker

knowledge-migrate:
	cd knowledge_service && uv run alembic upgrade head

ai:
	cd ai_service && uv run python main.py

# FE gọi qua gateway (:3040); đổi BACKEND_URL nếu gateway chạy chỗ khác
frontend:
	cd fe && BACKEND_URL=$(or $(BACKEND_URL),http://localhost:3040) pnpm dev

# nạp lại Qdrant + đồ thị bệnh nhân từ báo cáo kết luận đã chốt ở clinical (knowledge phải đang chạy)
reindex-cases:
	curl -sS -X POST http://localhost:3054/internal/cases/reindex -H "X-Internal-Key: $${INTERNAL_API_KEY:-derma-internal-key-change-in-production}"

# ---- chạy bằng Docker: 6 service + worker (cần make infra và make services-db trước; OPENROUTER_API_KEY lấy từ .env ở gốc repo) ----
services-build:
	docker compose -f deploy/docker-compose.services.yml --env-file .env build

services-up:
	docker compose -f deploy/docker-compose.services.yml --env-file .env up -d

services-down:
	docker compose -f deploy/docker-compose.services.yml --env-file .env down

# ---- test ----
identity-test:
	cd identity_service && ./mvnw -q -B clean test

consultation-test:
	cd consultation_service && ./mvnw -q -B clean test

clinical-test:
	cd clinical_service && ./mvnw -q -B clean test

gateway-test:
	cd gateway_service && ./mvnw -q -B clean test

knowledge-test:
	cd knowledge_service && uv run python -m unittest discover -s tests -t . && uv run python -m unittest discover -s pipeline/document_ingest/tests -t .

ai-test:
	cd ai_service && uv run python -m unittest discover -s tests -t . && uv run python -m unittest discover -s agent/graph/v2/tests -t .

shared-test:
	cd shared && uv run python -m unittest tests.test_shared

# bốn service Spring + shared + ai (knowledge-test chạy riêng: còn 2 test graph_schema lỗi từ trước)
test: identity-test consultation-test clinical-test gateway-test shared-test ai-test
