import asyncio
import json
import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, patch

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, SparseVectorParams, VectorParams

from agent.tools.hybrid_retrieval.corpus import FINALIZE_REPORT_CORPUS, case_result
from agent.tools.hybrid_retrieval.kg import ExtractedEntity
from agent.tools.hybrid_retrieval.pipeline import HybridResult, run_hybrid
from agent.tools.search_finalize_report import search_finalize_report
from app.infra.bm25 import SPARSE_NAME, encode_document
from app.infra.qdrant_client import QdrantVectorClient
from app.services.retrieval_service import RetrievalService

COLLECTION = "test_finalize_reports"
CASES = {
    "c1": ("Vảy nến mảng", "Dặn dò: methotrexate liều thấp mỗi tuần, tránh rượu"),
    "c2": ("Chàm cơ địa", "Mảng da khô ngứa ở khuỷu tay, bôi kem dưỡng ẩm"),
    "c3": ("Mày đay", "Sẩn phù rải rác tự hết sau vài giờ"),
}
DENSE = {"c1": [1.0, 0.0, 0.0, 0.0], "c2": [0.0, 1.0, 0.0, 0.0], "c3": [0.0, 0.0, 1.0, 0.0]}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _entities(q: str) -> list[ExtractedEntity]:
    return []


async def _rerank(q: str, passages: list[str]) -> list[float] | None:
    return [1.0 if "methotrexate" in p else 0.1 for p in passages]


async def _embed_pointing_at_c3(q: str) -> list[float]:
    return DENSE["c3"]  # dense cố ý chỉ sai ca: chỉ BM25 mới đưa được c1 lên


def _hybrid_patches(svc: RetrievalService):
    return (
        patch("agent.tools.hybrid_retrieval.semantic.get_retrieval_service", return_value=svc),
        patch("agent.tools.hybrid_retrieval.bm25.get_retrieval_service", return_value=svc),
    )


class FinalizeCorpusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.qdrant = QdrantVectorClient("memory://", sync_client=None)
        self.qdrant._async = AsyncQdrantClient(":memory:")  # type: ignore[attr-defined]
        self.svc = RetrievalService(self.qdrant)
        self.corpus = replace(FINALIZE_REPORT_CORPUS, collections=lambda: [COLLECTION], embed_query=_embed_pointing_at_c3)

        async def seed() -> None:
            client = self.qdrant.client
            await client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=4, distance=Distance.COSINE),
                sparse_vectors_config={SPARSE_NAME: SparseVectorParams()},
            )
            await client.upsert(
                COLLECTION,
                [
                    PointStruct(
                        id=i,
                        vector={"": DENSE[cid], SPARSE_NAME: encode_document(text, "mixed")},
                        payload={"case_id": cid, "diagnosis": dx, "text": text, "images": [], "clinical_facts": [], "instructions": []},
                    )
                    for i, (cid, (dx, text)) in enumerate(CASES.items(), start=1)
                ],
            )

        run(seed())

    def test_bm25_finds_exact_keyword_when_dense_points_elsewhere(self) -> None:
        p1, p2 = _hybrid_patches(self.svc)
        with p1, p2:
            r = run(run_hybrid("methotrexate", corpus=self.corpus, entities_fn=_entities, rerank_fn=_rerank))
        self.assertEqual(r.bm25[0]["case_id"], "c1")
        self.assertEqual(r.semantic[0]["case_id"], "c3")
        self.assertEqual(r.ranked[0]["case_id"], "c1")
        self.assertTrue(r.reranked)
        self.assertEqual(sorted(c["_id"] for c in r.candidates), sorted(set(c["_id"] for c in r.candidates)))  # khử trùng theo case_id

    def test_case_result_keeps_fields_the_tool_formats(self) -> None:
        out = case_result({"case_id": "x", "diagnosis": "d", "gender": "nam", "age": 30, "reasoning": "r", "notes": "n", "text": "t", "images": [{"storage_key": "k"}]})
        self.assertEqual(
            (out["case_id"], out["patient_info"]["age"], out["doctor_assessment"], out["doctor_notes"], out["case_summary"], out["images"]),
            ("x", 30, "r", "n", "t", [{"storage_key": "k"}]),
        )


def _result(ranked: list[dict[str, Any]], reranked: bool = True, notes: list[str] | None = None) -> HybridResult:
    return HybridResult(bm25_query="q", notes=notes or [], candidates=ranked, ranked=ranked, reranked=reranked)


def _call(result: HybridResult, **args: Any) -> dict[str, Any]:
    fs = type("FS", (), {"presigned_url": staticmethod(lambda k: f"https://x/{k}")})()
    with patch("agent.tools.search_finalize_report.run_hybrid", AsyncMock(return_value=result)), patch(
        "agent.tools.search_finalize_report.get_file_store_service", return_value=fs
    ):
        return json.loads(run(search_finalize_report.ainvoke({"query": "q", **args})))


class SearchFinalizeReportToolTest(unittest.TestCase):
    def test_keeps_schema_and_adds_relevance_and_presigned_url(self) -> None:
        case = {**case_result({"case_id": "c1", "diagnosis": "Vảy nến", "images": [{"storage_key": "k1", "confirmed_label": "psoriasis"}]}), "_id": "c1", "_passage": "p", "score": 0.9}
        out = _call(_result([case]))
        self.assertTrue(out["evidence_found"])
        self.assertEqual((out["ranked_by"], out["total_cases"]), ("reranker", 1))
        c = out["cases"][0]
        self.assertEqual((c["relevance_score"], c["diagnosis"], c["images"][0]["url"]), (0.9, "Vảy nến", "https://x/k1"))
        self.assertNotIn("_id", c)
        self.assertNotIn("score", c)

    def test_no_rerank_is_reported_in_notes(self) -> None:
        case = {**case_result({"case_id": "c1"}), "_id": "c1", "_passage": "p"}
        out = _call(_result([case], reranked=False))
        self.assertEqual(out["ranked_by"], "rrf")
        self.assertIsNone(out["cases"][0]["relevance_score"])
        self.assertTrue(any("rerank" in n for n in out["notes"]))

    def test_empty_means_no_evidence_and_keeps_leg_notes(self) -> None:
        out = _call(_result([], notes=["Nhánh bm25 không dùng được: X"]))
        self.assertFalse(out["evidence_found"])
        self.assertEqual(out["cases"], [])
        self.assertIn("Nhánh bm25 không dùng được: X", out["notes"])

    def test_limit_is_capped(self) -> None:
        cases = [{**case_result({"case_id": f"c{i}"}), "_id": f"c{i}", "_passage": "p", "score": 0.5} for i in range(8)]
        self.assertEqual(_call(_result(cases), limit=99)["total_cases"], 5)


if __name__ == "__main__":
    unittest.main()
