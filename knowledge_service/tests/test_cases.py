import asyncio
import unittest
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_case_api
from app.api.deps import get_case_index_service, get_clinical_http, get_patient_journey_service
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.dto.request.case import CaseInput
from app.services.case_index_service import CaseIndexService, build_case_payload, get_point_id
from app.services.patient_journey_service import PatientJourneyService

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


def make_case(report_id: str = "r1", **overrides: Any) -> CaseInput:
    data: dict[str, Any] = {
        "report_id": report_id,
        "patient_profile_id": "pp-1",
        "doctor_id": "d1",
        "encounter_id": "e1",
        "diagnosis": "Eczema",
        "notes": "tái khám 2 tuần",
        "is_reference_case": True,
        "created_at": datetime(2026, 3, 1, tzinfo=UTC),
        "snapshot": {
            "patient_profile": {"gender": "female", "dob": date(1990, 5, 1), "allergies": "penicillin", "full_name": "Nguyễn Văn A", "phone": "0900"},
            "assessment": {"reasoning": "mảng đỏ ngứa", "urgency": "routine", "instructions": ["tránh xà phòng"]},
            "clinical_facts": [{"fact_type": "symptom", "label": "Ngứa", "detail": "về đêm"}],
        },
        "images": [{"file_id": "f1", "storage_key": "k/1.jpg", "body_site": "tay", "confirmed_label": "eczema"}],
    }
    data.update(overrides)
    return CaseInput.model_validate(data)


class FakeEmbedding:
    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        return [[0.1, 0.2] for _ in texts], 2, "fake"


class FakeQdrant:
    def __init__(self) -> None:
        self.points: list[Any] = []

    def ensure_collection_sync(self, *args: Any, **kwargs: Any) -> None:
        pass

    def upsert_points_sync(self, collection: str, points: list[Any]) -> None:
        self.points += points


class FakeNeo4j:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.rows = rows or []

    def write_sync(self, statements: list[tuple[str, dict[str, Any]]]) -> None:
        self.statements = statements

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return self.rows


class CaseIndexTest(unittest.TestCase):
    def test_payload_is_anonymous_and_has_labels_from_images(self) -> None:
        payload = build_case_payload(make_case())
        self.assertEqual(payload["case_id"], "r1")
        self.assertEqual(payload["age"], datetime.now(UTC).year - 1990)
        self.assertNotIn("Nguyễn Văn A", payload["text"])
        self.assertNotIn("0900", payload["text"])
        self.assertIn("Nhãn ảnh xác nhận: eczema", payload["text"])
        self.assertIn("- [symptom] Ngứa: về đêm", payload["text"])
        self.assertEqual(payload["images"], [{"storage_key": "k/1.jpg", "file_name": "", "body_site": "tay", "description": "", "confirmed_label": "eczema"}])

    def test_index_case_upserts_one_point_with_stable_id(self) -> None:
        qdrant = FakeQdrant()
        CaseIndexService(qdrant, FakeEmbedding()).index_case(make_case())  # type: ignore[arg-type]
        self.assertEqual(len(qdrant.points), 1)
        self.assertEqual(qdrant.points[0].id, get_point_id("r1"))
        self.assertEqual(qdrant.points[0].payload["diagnosis"], "Eczema")


class PatientJourneyTest(unittest.TestCase):
    def test_sync_case_runs_all_statements_in_one_write(self) -> None:
        neo4j = FakeNeo4j()
        asyncio.run(PatientJourneyService(neo4j).sync_case(make_case()))  # type: ignore[arg-type]
        self.assertEqual(len(neo4j.statements), 5)  # phiên, fact, chốt, lời khuyên, ảnh
        self.assertEqual(neo4j.statements[1][1]["facts"][0]["id"], "e1:0")

    def test_sync_case_skips_empty_parts(self) -> None:
        case = make_case(snapshot={"patient_profile": {}, "assessment": {}}, images=[])
        neo4j = FakeNeo4j()
        asyncio.run(PatientJourneyService(neo4j).sync_case(case))  # type: ignore[arg-type]
        self.assertEqual(len(neo4j.statements), 2)  # chỉ phiên + chốt

    def test_history_hints_dedupes_and_keeps_order(self) -> None:
        rows = [{"conditions": ["A", "B"], "advice": ["x"]}, {"conditions": ["B", "C"], "advice": ["x", "y"]}]
        conditions, advice = asyncio.run(PatientJourneyService(FakeNeo4j(rows)).get_history_hints("pp-1"))  # type: ignore[arg-type]
        self.assertEqual((conditions, advice), (["A", "B", "C"], ["x", "y"]))

    def test_journey_graph_links_same_body_site_in_next_session(self) -> None:
        base = dict.fromkeys(["p", "s", "s_next", "f", "d", "c", "a", "img", "img_fact", "img_cond"])
        s1, s2 = {"id": "s1", "date": "2026-01-01"}, {"id": "s2", "date": "2026-02-01"}
        rows = [
            {**base, "p": {"id": "pp-1"}, "s": s1, "s_next": s2, "img": {"id": "i1", "body_site": "Tay"}},
            {**base, "p": {"id": "pp-1"}, "s": s2, "img": {"id": "i2", "body_site": "tay "}},
        ]
        graph = asyncio.run(PatientJourneyService(FakeNeo4j(rows)).get_journey_graph("pp-1"))  # type: ignore[arg-type]
        follows = [e for e in graph.edges if e.type == "FOLLOWS"]
        self.assertEqual([(e.source, e.target) for e in follows], [("i1", "i2")])
        self.assertEqual(next(n.name for n in graph.nodes if n.id == "s1"), "Phiên 2026-01-01")


class FakeIndex:
    def __init__(self) -> None:
        self.indexed: list[str] = []

    async def index_case_async(self, case: CaseInput) -> None:
        if case.report_id == "bad":
            raise RuntimeError("embedding lỗi")
        self.indexed.append(case.report_id)


class FakeJourney:
    def __init__(self) -> None:
        self.synced: list[str] = []

    async def sync_case(self, case: CaseInput) -> None:
        self.synced.append(case.report_id)


class CaseApiTest(unittest.TestCase):
    def build_client(self, pages: dict[int, list[str]]) -> TestClient:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Internal-Key"] == settings.INTERNAL_API_KEY
            ids = pages.get(int(request.url.params["page"]), [])
            return httpx.Response(200, json={"data": [make_case(i).model_dump(mode="json") for i in ids]})

        self.index, self.journey = FakeIndex(), FakeJourney()
        clinical = httpx.AsyncClient(base_url="http://clinical", transport=httpx.MockTransport(handler), headers={"X-Internal-Key": settings.INTERNAL_API_KEY})
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_case_api.router)
        app.dependency_overrides[get_case_index_service] = lambda: self.index
        app.dependency_overrides[get_patient_journey_service] = lambda: self.journey
        app.dependency_overrides[get_clinical_http] = lambda: clinical
        return TestClient(app)

    def test_post_case_indexes_and_syncs_graph(self) -> None:
        client = self.build_client({})
        r = client.post("/internal/cases", json=make_case("r9").model_dump(mode="json"), headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((self.index.indexed, self.journey.synced), (["r9"], ["r9"]))
        self.assertEqual(client.post("/internal/cases", json={}, headers=HEADERS).status_code, 422)
        self.assertEqual(client.post("/internal/cases", json={}).status_code, 403)

    def test_reindex_reads_every_page_and_reports_failures(self) -> None:
        client = self.build_client({1: ["a", "bad"], 2: ["c"]})
        with patch.object(internal_case_api, "REINDEX_PAGE_SIZE", 2):
            r = client.post("/internal/cases/reindex", headers=HEADERS)
        self.assertEqual(r.json()["data"], {"indexed": 2, "failed": ["bad"]})
        self.assertEqual(self.journey.synced, ["a", "c"])


if __name__ == "__main__":
    unittest.main()
