"""PostgreSQL dùng chung"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings


class PostgresClient:
    def __init__(self, url: str) -> None:
        # URL trong cấu hình có thể còn driver async (`+asyncpg`); service này chỉ dùng driver đồng bộ
        self.engine = create_engine(url.replace("+asyncpg", "+psycopg"), pool_pre_ping=True)
        self.sync_session_factory: sessionmaker[Session] = sessionmaker(bind=self.engine, expire_on_commit=False)

    @classmethod
    def from_settings(cls) -> "PostgresClient":
        return cls(settings.DATABASE_URL)

    async def close(self) -> None:
        self.engine.dispose()
