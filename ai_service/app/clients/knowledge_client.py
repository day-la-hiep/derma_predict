from typing import Any

import httpx


class KnowledgeClient:
    """Gọi knowledge (retrieval sách/ca bệnh, đồ thị tri thức); lỗi HTTP ném lên để tool tự báo cho model."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        response = await self._http.post(path, json=body)
        response.raise_for_status()
        return response.json()["data"]

    async def search_semantic(self, query: str, limit: int, *, corpus: str = "document", eq: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._post("/internal/search/semantic", {"corpus": corpus, "query": query, "limit": limit, "eq": eq or {}})

    async def search_bm25(self, query: str, limit: int, *, corpus: str = "document", eq: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._post("/internal/search/bm25", {"corpus": corpus, "query": query, "limit": limit, "eq": eq or {}})

    async def search_by_graph(self, names: list[str], limit: int) -> list[dict[str, Any]]:
        return await self._post("/internal/search/graph", {"names": names, "limit": limit})

    async def query_document_graph(self, entity: str, relation: str | None, limit: int) -> list[dict[str, Any]]:
        return await self._post("/internal/graph/document-query", {"entity": entity, "relation": relation, "limit": limit})

    async def run_kg_intent(self, intent: str, entities: list[str], limit: int, translate: bool = True) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
        data = await self._post("/internal/kg/intent", {"intent": intent, "entities": entities, "limit": limit, "translate": translate})
        return data["facts"], data["notes"], data["resolved"]

    async def get_discriminating_questions(self, diseases: list[str], known_phenotype_ids: list[str] | None = None, top_k: int = 3) -> dict[str, Any]:
        return await self._post("/internal/kg/discriminating-questions", {"diseases": diseases, "known_phenotype_ids": known_phenotype_ids, "top_k": top_k})
