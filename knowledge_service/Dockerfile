# Image service knowledge: API (:3054) và ingest worker dùng chung, khác nhau ở lệnh chạy (compose override `command`).
# Build context phải là REPO ROOT: cần `shared` và từ điển đồ thị nền của `archive/core/graph_base`:
#   docker build -f knowledge_service/Dockerfile -t derma-knowledge .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

# libgomp1: runtime của torch/docling (OpenMP) trên slim image
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/knowledge_service
COPY shared /app/shared
COPY knowledge_service .

ENV UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=8
RUN uv sync --frozen --no-dev

# Từ điển khớp thực thể (`GRAPH_LEXICON_DIR` mặc định trỏ tới đúng đường dẫn này), 219MB
COPY archive/core/graph_base/data/build /app/archive/core/graph_base/data/build

ENV PATH="/app/knowledge_service/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

EXPOSE 3054
# Áp migration DB `knowledge` rồi chạy API; ingest worker override: python -u -m app.workers.document_ingest_worker
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 3054"]
