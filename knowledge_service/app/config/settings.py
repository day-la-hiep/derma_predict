"""Cấu hình service knowledge: kế thừa phần dùng chung từ `derma_shared`, thêm Postgres/Qdrant/Neo4j/LLM của riêng nó."""

import logging
from pathlib import Path

from derma_shared.settings import SharedSettings

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(SharedSettings):
    PROJECT_NAME: str = "Derma Knowledge Service"
    DEBUG: bool = False
    PORT: int = 3054
    API_V1_PREFIX: str = "/api/v1"

    # Gọi `/internal/*`: service khác gửi kèm header `X-Internal-Key`
    INTERNAL_API_KEY: str = "derma-internal-key-change-in-production"
    # Địa chỉ clinical để reindex ca tham khảo (`GET /internal/finalize-reports`)
    CLINICAL_URL: str = "http://localhost:3053"

    # DB riêng của service (migration khởi tạo viết tay trong `migrations/`)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/knowledge"

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    # v4: Qwen3-Embedding-8B (4096 chiều); collection cũ khác số chiều nên không dùng lại được
    QDRANT_DOCUMENT_COLLECTION: str = "derma_document_chunks_v4"
    QDRANT_FINALIZE_REPORT_COLLECTION: str = "derma_finalize_reports"

    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "derma12345"
    # "KG" = cạnh PrimeKG/DermO gốc, "DOC" = cạnh trích từ sách (bước graph_index)
    KG_EDGE_SOURCES: list[str] = ["KG"]
    # Từ điển khớp thực thể cho bước đồ thị: đọc dữ liệu đã build của `archive/core/graph_base` (chỉ đọc, không sao chép 220MB)
    GRAPH_LEXICON_DIR: str = str(_REPO_ROOT / "archive" / "core" / "graph_base" / "data" / "build")

    MINIO_DOCUMENTS_BUCKET: str = "derma-documents"

    # Provider LLM và embedding (OpenRouter), dùng cho bước đọc mục lục và bước index
    EMBEDDING_MODEL: str = "qwen/qwen3-embedding-8b"
    EMBEDDING_DIM: int = 4096
    AGENT_MODEL: str = "openrouter:google/gemma-4-26b-a4b-it"
    AGENT_TEMPERATURE: float = 0.3
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: str = ""


settings = Settings()


def log_startup_infra() -> None:
    logger = logging.getLogger("infra")
    logger.info("PostgreSQL -> %s", settings.DATABASE_URL.split("@")[-1])
    logger.info("Redis      -> %s:%s/db%s", settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
    logger.info("RabbitMQ   -> %s", settings.RABBITMQ_URL.split("@")[-1])
    logger.info("Qdrant     -> %s (chunk sách: %s)", settings.QDRANT_URL, settings.QDRANT_DOCUMENT_COLLECTION)
    logger.info("Neo4j      -> %s (user=%s)", settings.NEO4J_URL, settings.NEO4J_USER)
    logger.info("MinIO      -> %s (bucket=%s)", settings.MINIO_ENDPOINT, settings.MINIO_DOCUMENTS_BUCKET)
