import asyncio
import dataclasses
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_api
from app.api.deps import get_document_graph_service, get_knowledge_graph_service, get_retrieval_service
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.services.kg_intent_service import run_intent
from app.services.retrieval_corpus import DOCUMENT_CORPUS

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


async def fake_embed(_: str) -> list[float]:
    return [0.1, 0.2]


class FakeRetrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dense(self, corpus: Any, *, vector: list[float], limit: int, filter: Any) -> list[Any]:
        self.calls.append(("dense", {"corpus": corpus.name, "vector": vector, "limit": limit, "eq": filter.eq}))
        return [SimpleNamespace(payload={"chunk_id": "c1"}), SimpleNamespace(payload=None)]

    async def sparse(self, corpus: Any, *, query: str, limit: int, filter: Any) -> list[Any]:
        self.calls.append(("sparse", {"corpus": corpus.name, "query": query, "limit": limit}))
        return [SimpleNamespace(payload={"chunk_id": "c2"})]

    async def fetch(self, corpus: Any, ids: list[str]) -> list[dict[str, Any]]:
        return [{"chunk_id": i} for i in ids]


class FakeDocGraph:
    async def chunks_for_entities(self, names: list[str], limit: int) -> list[str]:
        return [f"chunk-{n}" for n in names][:limit]

    async def query_document_graph(self, entity: str, relation: str | None, limit: int) -> list[dict[str, Any]]:
        return [{"subject": entity, "relation": relation or "ANY"}]


class FakeKg:
    async def discriminating_questions(self, diseases: list[str], known: list[str] | None, top_k: int) -> dict[str, Any]:
        return {"questions": [], "note": f"{len(diseases)} bệnh, top_k={top_k}"}


class InternalApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_api.router)
        self.retrieval = FakeRetrieval()
        app.dependency_overrides[get_retrieval_service] = lambda: self.retrieval
        app.dependency_overrides[get_document_graph_service] = lambda: FakeDocGraph()
        app.dependency_overrides[get_knowledge_graph_service] = lambda: FakeKg()
        self.client = TestClient(app)
        corpus = dataclasses.replace(DOCUMENT_CORPUS, embed_query=fake_embed)
        patcher = patch.dict(internal_api.CORPORA, {"document": corpus})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rejects_missing_or_wrong_key(self) -> None:
        body = {"query": "vảy nến"}
        self.assertEqual(self.client.post("/internal/search/bm25", json=body).status_code, 403)
        self.assertEqual(self.client.post("/internal/search/bm25", json=body, headers={"X-Internal-Key": "sai"}).status_code, 403)

    def test_semantic_embeds_query_and_drops_points_without_payload(self) -> None:
        r = self.client.post("/internal/search/semantic", json={"query": "ngứa", "limit": 5, "eq": {"document_id": "d1"}}, headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"], [{"chunk_id": "c1"}])
        self.assertEqual(self.retrieval.calls[0][1], {"corpus": "document", "vector": [0.1, 0.2], "limit": 5, "eq": {"document_id": "d1"}})

    def test_bm25_returns_payloads(self) -> None:
        r = self.client.post("/internal/search/bm25", json={"query": "vảy nến"}, headers=HEADERS)
        self.assertEqual(r.json()["data"], [{"chunk_id": "c2"}])

    def test_graph_search_fetches_chunks_of_entities(self) -> None:
        r = self.client.post("/internal/search/graph", json={"names": ["eczema", "acne"], "limit": 1}, headers=HEADERS)
        self.assertEqual(r.json()["data"], [{"chunk_id": "chunk-eczema"}])

    def test_document_query_and_discriminating_questions(self) -> None:
        r = self.client.post("/internal/graph/document-query", json={"entity": "acne"}, headers=HEADERS)
        self.assertEqual(r.json()["data"], [{"subject": "acne", "relation": "ANY"}])
        r = self.client.post("/internal/kg/discriminating-questions", json={"diseases": ["a", "b"], "top_k": 2}, headers=HEADERS)
        self.assertEqual(r.json()["data"]["note"], "2 bệnh, top_k=2")

    def test_rejects_unknown_corpus(self) -> None:
        r = self.client.post("/internal/search/bm25", json={"query": "x", "corpus": "khac"}, headers=HEADERS)
        self.assertEqual(r.status_code, 422)

    def test_run_intent_reports_invalid_intent_and_missing_entities(self) -> None:
        facts, notes, _ = asyncio.run(run_intent(None, "khong_co", ["acne"], 5))  # type: ignore[arg-type]
        self.assertEqual(facts, [])
        self.assertIn("không hợp lệ", notes[0])
        _, notes, _ = asyncio.run(run_intent(None, "treatments", [" "], 5))  # type: ignore[arg-type]
        self.assertIn("Thiếu `entities`", notes[0])

    def test_kg_intents_lists_known_intents(self) -> None:
        r = self.client.get("/internal/kg/intents", headers=HEADERS)
        self.assertIn("treatments", r.json()["data"])


if __name__ == "__main__":
    unittest.main()
