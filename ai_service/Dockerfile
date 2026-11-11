# Image service ai (tác nhân LangGraph). Build context phải là REPO ROOT: cần `shared` (path dependency) và checkpoint CNN ở `model/`:
#   docker build -f ai_service/Dockerfile -t derma-ai .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

# libgomp1: runtime của torch (OpenMP) trên slim image
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# `../shared` trong pyproject phải tồn tại cạnh thư mục service, nên giữ nguyên cấu trúc /app/<tên>_service và /app/shared
WORKDIR /app/ai_service
COPY shared /app/shared
COPY ai_service .

# Mirror PyPI chậm hay làm `uv sync` timeout giữa chừng: tăng thời gian chờ và số lần thử lại
ENV UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=8
RUN uv sync --frozen --no-dev

# Checkpoint CNN 44MB chỉ nằm trong image ai
COPY ml/model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth /model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth

ENV PATH="/app/ai_service/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    SKIN_CNN_CHECKPOINT_PATH=/model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth

EXPOSE 3055
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3055"]
