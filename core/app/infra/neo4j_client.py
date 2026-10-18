"""Neo4j dùng chung"""
from typing import Any, LiteralString

from neo4j import AsyncDriver, AsyncGraphDatabase, Driver, GraphDatabase, ManagedTransaction

from app.config.settings import settings


class Neo4jClient:
    def __init__(self, url: str, user: str, password: str) -> None:
        self._url, self._auth = url, (user, password)
        self._driver: AsyncDriver | None = None
        self._sync_driver: Driver | None = None  # bước pipeline chạy trong thread của ingest worker, không có event loop

    @classmethod
    def from_settings(cls) -> "Neo4jClient":
        return cls(settings.NEO4J_URL, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(self._url, auth=self._auth)  # pyright: ignore[reportUnknownMemberType]
        return self._driver

    async def run(self, query: LiteralString, **params: Any) -> list[dict[str, Any]]:
        async with self.driver.session() as session:  # pyright: ignore[reportUnknownMemberType]
            result = await session.run(query, **params)
            return [r.data() async for r in result]

    @property
    def sync_driver(self) -> Driver:
        if self._sync_driver is None:
            self._sync_driver = GraphDatabase.driver(self._url, auth=self._auth)  # pyright: ignore[reportUnknownMemberType]
        return self._sync_driver

    def run_sync(self, query: LiteralString, **params: Any) -> list[dict[str, Any]]:
        with self.sync_driver.session() as session:  # pyright: ignore[reportUnknownMemberType]
            return [r.data() for r in session.run(query, **params)]

    def write_sync(self, statements: list[tuple[LiteralString, dict[str, Any]]]) -> None:
        """Chạy nhiều câu ghi trong MỘT transaction: lỗi giữa chừng thì không để lại nửa dữ liệu."""

        def work(tx: ManagedTransaction) -> None:
            for query, params in statements:
                tx.run(query, **params).consume()

        with self.sync_driver.session() as session:  # pyright: ignore[reportUnknownMemberType]
            session.execute_write(work)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
        if self._sync_driver is not None:
            self._sync_driver.close()
            self._sync_driver = None
