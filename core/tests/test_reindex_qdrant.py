import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config.settings import settings
from app.infra.bm25 import SPARSE_NAME, encode_document
from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.models.finalize_report import FinalizeReport
from app.services.finalize_report_index_service import FinalizeReportIndexService
from app.services.qdrant_reindex_service import QdrantReindexService
from pipeline.document_ingest.profile import default_profile
from pipeline.document_ingest.tests.test_document_pipeline import DIM, Base


class BrokenEmbedding:
    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        raise ConnectionError("OpenRouter không phản hồi")


class CaseEmbedding:
    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        if any("LOI" in t for t in texts):
            raise ConnectionError("embedding lỗi")
        return [[1.0] + [0.0] * (settings.EMBEDDING_DIM - 1) for _ in texts], settings.EMBEDDING_DIM, "fake-case"


def report(rid: str, diagnosis: str) -> FinalizeReport:
    return FinalizeReport(
        id=rid, patient_profile_id="p", diagnosis=diagnosis, notes="", is_reference_case=False,
        snapshot={"assessment": {"reasoning": "r"}, "clinical_facts": []}, created_at=datetime.now(UTC),
    )


class ReindexDocumentsTest(Base):
    def setUp(self) -> None:
        super().setUp()
        self.run_toc({"pages": "2-3"})
        self.fix_pustular()
        self.runner.run_stage("tbook", "chunks", {}, force=True)
        self.runner.run_stage("tbook", "index", {}, force=True)
        self.runner.approve("tbook", "index")
        self.lines: list[str] = []
        self.service = QdrantReindexService(self.runner, self.repo, SimpleNamespace(collection="unused"), self.qdrant, log=self.lines.append)  # type: ignore[arg-type]

    def points(self) -> int:
        return self.qdrant.count_sync(self.vectors.collection, eq_filter("document_id", "tbook"))

    def index_state(self) -> str:
        return self.repo.status("tbook")["stages"]["index"]["state"]

    def test_restores_points_and_keeps_stage_approved(self) -> None:
        expected = self.points()
        self.qdrant.delete_by_filter_sync(self.vectors.collection, eq_filter("document_id", "tbook"))
        self.assertEqual(self.points(), 0)
        r = self.service.reindex_documents()
        self.assertEqual((r.ok, r.failed), (["tbook"], {}))
        self.assertEqual((self.points(), self.index_state()), (expected, "approved"))
        self.assertEqual(self.repo.status("tbook")["stages"]["chunks"]["state"], "pending_review")  # bước trước không đổi

    def test_skips_document_whose_index_stage_never_ran(self) -> None:
        self.repo.create("Other", {}, default_profile("other"), {}, document_id="other")
        r = self.service.reindex_documents()
        self.assertEqual(r.ok, ["tbook"])
        self.assertIn("other", r.skipped)

    def test_embedding_error_keeps_old_points_and_other_documents_still_run(self) -> None:
        expected = self.points()
        self.runner._embedding = BrokenEmbedding()  # type: ignore[attr-defined]
        r = self.service.reindex_documents(["missing", "tbook"])
        self.assertEqual(sorted(r.failed), ["missing", "tbook"])
        self.assertIn("ConnectionError", r.failed["tbook"])
        self.assertEqual(self.points(), expected)  # embedding chạy trước khi xoá nên điểm cũ còn nguyên
        self.assertEqual(self.index_state(), "approved")

    def test_dry_run_writes_nothing(self) -> None:
        self.qdrant.delete_by_filter_sync(self.vectors.collection, eq_filter("document_id", "tbook"))
        r = self.service.reindex_documents(dry_run=True)
        self.assertEqual(r.ok, ["tbook"])
        self.assertEqual(self.points(), 0)

    def test_collection_without_sparse_vector_reports_how_to_fix(self) -> None:
        client = self.qdrant.sync_client
        client.delete_collection(self.vectors.collection)
        client.create_collection(self.vectors.collection, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE))
        r = self.service.reindex_documents()
        self.assertIn("QDRANT_DOCUMENT_COLLECTION", r.failed["tbook"])


    def ghost(self, pid: int, **payload: Any) -> None:
        self.qdrant.sync_client.upsert(
            self.vectors.collection,
            [PointStruct(id=pid, vector={"": [0.1] * DIM, SPARSE_NAME: encode_document("ma")}, payload=payload)],
        )

    def test_prune_removes_points_of_documents_missing_from_db_only(self) -> None:
        expected = self.points()
        self.ghost(900001, document_id="ghost")
        self.ghost(900002, document_id="ghost")
        self.ghost(900003, chunk_id="no-document-field")
        r = self.service.prune_documents()
        self.assertEqual((r.removed, r.failed, r.refused), ({"ghost": 2}, {}, ""))
        self.assertEqual(self.qdrant.count_sync(self.vectors.collection, eq_filter("document_id", "ghost")), 0)
        self.assertEqual(self.points(), expected)
        self.assertEqual(self.qdrant.count_sync(self.vectors.collection, eq_filter("chunk_id", "no-document-field")), 1)  # thiếu field id: không đụng

    def test_prune_dry_run_counts_but_keeps_points(self) -> None:
        self.ghost(900001, document_id="ghost")
        r = self.service.prune_documents(dry_run=True)
        self.assertEqual(r.removed, {"ghost": 1})
        self.assertEqual(self.qdrant.count_sync(self.vectors.collection, eq_filter("document_id", "ghost")), 1)

    def test_prune_refuses_when_db_has_no_documents(self) -> None:
        expected = self.points()
        service = QdrantReindexService(self.runner, SimpleNamespace(list_ids=lambda: []), SimpleNamespace(collection="unused"), self.qdrant, log=self.lines.append)  # type: ignore[arg-type]
        r = service.prune_documents()
        self.assertTrue(r.refused)
        self.assertEqual((r.removed, self.points()), ({}, expected))


class ReindexFinalizeReportsTest(unittest.TestCase):
    def make(self, embedding: Any) -> tuple[QdrantReindexService, FinalizeReportIndexService, QdrantVectorClient]:
        qdrant = QdrantVectorClient("http://unused", sync_client=QdrantClient(":memory:"))
        index = FinalizeReportIndexService(qdrant, embedding)
        return QdrantReindexService(None, None, index, qdrant, log=lambda m: None), index, qdrant  # type: ignore[arg-type]

    def test_every_report_becomes_a_point_with_sparse_vector(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        r = service.reindex_finalize_reports([(report("r1", "Vảy nến"), None, []), (report("r2", "Chàm"), None, [])])
        self.assertEqual((sorted(r.ok), r.failed), (["r1", "r2"], {}))
        self.assertEqual(qdrant.count_sync(index.collection), 2)
        self.assertIn(SPARSE_NAME, qdrant.sync_client.get_collection(index.collection).config.params.sparse_vectors or {})

    def test_one_failing_report_does_not_stop_the_rest(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        r = service.reindex_finalize_reports([(report("bad", "LOI"), None, []), (report("r2", "Chàm"), None, [])])
        self.assertEqual((r.ok, list(r.failed)), (["r2"], ["bad"]))
        self.assertEqual(qdrant.count_sync(index.collection), 1)

    def test_rerun_is_idempotent_and_dry_run_writes_nothing(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        service.reindex_finalize_reports([(report("r1", "Vảy nến"), None, [])], dry_run=True)
        self.assertEqual(qdrant.count_sync(index.collection), 0)
        for _ in range(2):
            service.reindex_finalize_reports([(report("r1", "Vảy nến"), None, [])])
        self.assertEqual(qdrant.count_sync(index.collection), 1)


    def test_prune_removes_cases_missing_from_db(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        service.reindex_finalize_reports([(report(i, "d"), None, []) for i in ("r1", "r2", "gone")])
        r = service.prune_finalize_reports(["r1", "r2"])
        self.assertEqual((r.removed, r.failed), ({"gone": 1}, {}))
        self.assertEqual(qdrant.count_sync(index.collection), 2)

    def test_prune_dry_run_and_refuse_on_empty_db_keep_everything(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        service.reindex_finalize_reports([(report(i, "d"), None, []) for i in ("r1", "gone")])
        self.assertEqual(service.prune_finalize_reports(["r1"], dry_run=True).removed, {"gone": 1})
        self.assertTrue(service.prune_finalize_reports([]).refused)
        self.assertEqual(qdrant.count_sync(index.collection), 2)

    def test_prune_failure_on_one_id_does_not_stop_the_rest(self) -> None:
        service, index, qdrant = self.make(CaseEmbedding())
        service.reindex_finalize_reports([(report(i, "d"), None, []) for i in ("keep", "a", "b")])
        real = qdrant.delete_by_filter_sync

        def flaky(name: str, f: Any) -> None:
            if "a" == f.must[0].match.value:
                raise ConnectionError("qdrant mất kết nối")
            real(name, f)

        qdrant.delete_by_filter_sync = flaky  # type: ignore[method-assign]
        r = service.prune_finalize_reports(["keep"])
        self.assertEqual((list(r.removed), list(r.failed)), (["b"], ["a"]))
        self.assertEqual(qdrant.count_sync(index.collection), 2)


if __name__ == "__main__":
    unittest.main()
