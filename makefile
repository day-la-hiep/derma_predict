.PHONY: infra infra-down backend worker debug-app ingest-worker migrate migrate-new init-db reindex-qdrant load-primekg load-dermo load-kg kg-download kg-build kg-load kg-verify data-export data-restore frontend

infra:
	docker compose up -d

infra-down:
	docker compose down

backend:
	cd core && uv run python main.py

worker:
	cd core && uv run python -u -m agent.worker

# giao diện Streamlit debug luồng lập luận của agent, chạy graph trực tiếp (không cần backend/worker): make debug-app [port=8501]
debug-app:
	cd core && uv run streamlit run agent/test/debug_app.py $(if $(port),--server.port $(port))

ingest-worker:
	cd core && uv run python -u -m app.workers.document_ingest_worker

migrate:
	cd core && uv run alembic upgrade head

migrate-new:
	cd core && uv run alembic revision --autogenerate -m "$(m)"

# bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin); chạy sau migrate, chạy lại không tạo trùng
init-db:
	cd core && uv run python scripts/init_db.py

# nạp lại Qdrant từ MinIO/Postgres: make reindex-qdrant [only=documents|finalize-reports] [document=<id>] [prune=1|prune_only=1] [dry=1]  (prune=1: xoá điểm mồ côi, nên chạy dry=1 trước)
reindex-qdrant:
	cd core && uv run python scripts/reindex_qdrant.py $(if $(only),--only $(only)) $(if $(document),--document $(document)) $(if $(prune),--prune) $(if $(prune_only),--prune-only) $(if $(dry),--dry-run)

# nạp PrimeKG (label :Entity — quan hệ bệnh/triệu chứng/thuốc) vào Neo4j; chạy lại được, `make load-primekg reset=1` xoá :Entity cũ trước khi nạp
load-primekg:
	cd core && uv run python data_ingest/01_normalize/scripts/load_primekg.py $(if $(reset),--reset)

# nạp ontology thuật ngữ DermO vào Neo4j (nhánh KG của hybrid_retrieval); chạy lại được, `make load-dermo reset=1` xoá DermO cũ trước khi nạp
load-dermo:
	cd core && uv run python data_ingest/01_normalize/scripts/load_dermo.py $(if $(reset),--reset)

# nạp đủ knowledge graph cho tool KG: PrimeKG + DermO (thiếu một trong hai thì query báo label không tồn tại)
load-kg: load-primekg load-dermo

# graph nền (PrimeKG + DermO) dựng từ nguồn gốc: tải -> build -> nạp Neo4j -> kiểm tra; `make kg-load reset=1` xoá :Entity/:DermoTerm (kể cả cạnh DOC) rồi nạp lại
kg-download:
	cd core && uv run python -m graph_base.primekg.download && uv run python -m graph_base.dermo.download

kg-build:
	cd core && uv run python -m graph_base.primekg.build && uv run python -m graph_base.dermo.build

kg-load:
	cd core && uv run python -m graph_base.primekg.load $(if $(reset),--reset) && uv run python -m graph_base.dermo.load $(if $(reset),--reset)

kg-verify:
	cd core && uv run python -m graph_base.verify

# xuất / khôi phục 4 volume (postgres, minio, qdrant, neo4j) vào ./backup; tắt stack trước (docker compose down); prod: make data-export VOL_PREFIX=derma-hospital-prod_
data-export:
	$(if $(VOL_PREFIX),VOL_PREFIX=$(VOL_PREFIX)) ./scripts/transfer-data.sh export

data-restore:
	$(if $(VOL_PREFIX),VOL_PREFIX=$(VOL_PREFIX)) ./scripts/transfer-data.sh restore

frontend:
	cd fe && pnpm dev
