"""Cấu hình service ai: kế thừa phần dùng chung từ `derma_shared`, thêm LLM, CNN và địa chỉ các service khác."""

import logging
from pathlib import Path

from derma_shared.settings import SharedSettings

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(SharedSettings):
    PROJECT_NAME: str = "Derma AI Service"
    PORT: int = 3055

    # `/internal/*` của ai và mọi lời gọi sang service khác dùng header `X-Internal-Key`
    INTERNAL_API_KEY: str = "derma-internal-key-change-in-production"
    CONSULTATION_URL: str = "http://localhost:3052"
    CLINICAL_URL: str = "http://localhost:3053"
    KNOWLEDGE_URL: str = "http://localhost:3054"

    # DB riêng của ai: chỉ chứa schema `langgraph` (memory dài hạn + checkpoint hội thoại)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai"

    # Ảnh đính kèm tin nhắn nằm ở bucket này; agent chỉ đọc (phân loại ảnh, tạo URL ca bệnh)
    MINIO_BUCKET: str = "derma-attachments"

    RERANKER_MODEL: str = "qwen/qwen3-reranker-8b"
    AGENT_MODEL: str = "openrouter:google/gemma-4-26b-a4b-it"
    AGENT_TEMPERATURE: float = 0.3
    AGENT_MODEL_CHOICES: dict[str, str] = {
        "deepseek-v4-pro": "deepseek:deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek:deepseek-flash",
        "gemma4-26b": "openrouter:google/gemma-4-26b-a4b-it",
    }
    AGENT_DEFAULT_MODEL_ID: str = "gemma4-26b"
    AGENT_TRIAGE_ENABLED: bool = True
    AGENT_TRIAGE_MODEL: str = ""
    AGENT_FINALIZE_REPORT_SEARCH_ENABLED: bool = True
    AGENT_MEMORY_BATCH_INTERVAL_MIN: int = 60
    AGENT_MEMORY_BATCH_MAX_PENDING: int = 20
    AGENT_MEMORY_CONSOLIDATE_AT: int = 15
    AGENT_MEMORY_CONSOLIDATE_DAYS: int = 7
    AGENT_THINKING_LEVEL: str = "medium"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    LOCAL_LLM_BASE_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_API_KEY: str = "local"
    LOCAL_LLM_TIMEOUT: float = 300.0
    SKIN_CNN_CHECKPOINT_PATH: str = str(
        _REPO_ROOT
        / "ml"
        / "model"
        / "model_output"
        / "AdaptiveCNN_SkinDisease_v5_best.pth"
    )
    AGENT_VISION_MODEL: str = ""
    AGENT_VISION_TIMEOUT: float = 120.0


settings = Settings()


def log_startup_infra() -> None:
    logger = logging.getLogger("infra")
    logger.info("PostgreSQL -> %s (schema langgraph)", settings.DATABASE_URL.split("@")[-1])
    logger.info("Redis      -> %s:%s/db%s", settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
    logger.info("MinIO      -> %s (bucket=%s)", settings.MINIO_ENDPOINT, settings.MINIO_BUCKET)
    logger.info("Knowledge  -> %s | Clinical -> %s | Consultation -> %s", settings.KNOWLEDGE_URL, settings.CLINICAL_URL, settings.CONSULTATION_URL)
