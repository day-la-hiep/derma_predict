import asyncio
import unittest
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS
from app.infra.qdrant_client import QdrantVectorClient
from app.services.retrieval_service import RetrievalCorpus, RetrievalService


def _pid(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class FetchTest(unittest.TestCase):
    def test_fetch_keeps_order_and_skips_missing(self) -> None:
        async def scenario() -> list[str]:
            qdrant = QdrantVectorClient("http://unused")
            qdrant.__dict__["_async"] = AsyncQdrantClient(":memory:")  # Qdrant in-memory, không cần service thật
            await qdrant.client.create_collection("c", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
            await qdrant.client.upsert("c", [PointStruct(id=_pid(i), vector=[1.0, 0.0], payload={"chunk_id": i}) for i in ("a", "b")])
            corpus = RetrievalCorpus(**{**DOCUMENT_CORPUS.__dict__, "collections": lambda: ["c"]})
            return [p["chunk_id"] for p in await RetrievalService(qdrant).fetch(corpus, ["b", "zzz", "a"])]

        self.assertEqual(asyncio.run(scenario()), ["b", "a"])


if __name__ == "__main__":
    unittest.main()
