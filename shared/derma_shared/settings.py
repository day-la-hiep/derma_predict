"""Cấu hình dùng chung của các service Python: mỗi service kế thừa `SharedSettings` rồi thêm field riêng."""

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Biến không khai báo trong class (vd khoá provider LLM) chỉ đọc được qua os.environ nên phải nạp .env ở đây
load_dotenv(find_dotenv(usecwd=True) or None)


class SharedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["*"]

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    RABBITMQ_URL: str = "amqp://derma:derma@localhost:5672/"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123"
    MINIO_SECURE: bool = False

    # Khoá/thuật toán phải khớp với identity (Spring) và mọi service verify token
    JWT_SECRET_KEY: str = "derma-secret-key-change-in-production-datn-2026"
    JWT_ALGORITHM: str = "HS256"


settings = SharedSettings()
