from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import BaseStore
from langgraph.store.postgres import AsyncPostgresStore

from app.config.settings import settings


class _Saver(AsyncPostgresSaver):
    # `CREATE INDEX CONCURRENTLY` đợi mọi transaction đang mở của cả database (kể cả phiên "idle in transaction" của Core / Streamlit) nên `setup()` treo vô hạn,
    # và nếu bị ngắt giữa chừng sẽ để lại index INVALID. Bảng còn nhỏ lúc khởi động nên tạo index thường.
    MIGRATIONS = [m.replace("CREATE INDEX CONCURRENTLY", "CREATE INDEX") for m in AsyncPostgresSaver.MIGRATIONS]


@asynccontextmanager
async def postgres_persistence() -> AsyncIterator[tuple[BaseStore, BaseCheckpointSaver[str]]]:
    """Memory dài hạn và checkpoint của chat graph, cùng nằm trong schema `langgraph` để Alembic của Core không đụng tới; tự tạo bảng khi mở."""
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    sep = "&" if "?" in url else "?"
    scoped = f"{url}{sep}options=-csearch_path%3Dlanggraph"
    async with AsyncPostgresStore.from_conn_string(scoped) as store, _Saver.from_conn_string(scoped) as saver:
        await store.setup()
        await saver.setup()
        yield store, saver
