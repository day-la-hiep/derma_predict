import unittest
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_api
from app.api.deps import get_knowledge_graph_service
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.services import knowledge_graph_service as kgs
from app.services import patient_graph_context_service as pgc
from app.services.knowledge_graph_service import KnowledgeGraphService

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


class FakeNeo4j:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if query is pgc._RESOLVE_SEEDS:
            return [{"eid": f"e-{p['id']}", "type": p["type"], "id": p["id"], "name": p["id"]} for p in params["pairs"] if p["id"] != "mất"]
        if query is pgc._CANDIDATES:
            return [{"id": "5083", "name": "psoriasis", "score": 3.0, "why": ["triệu chứng: x"]}, {"id": "1", "name": "B", "score": 1.5, "why": []}]
        if query is pgc._ABSENT_PHENOTYPES:
            return [{"name": "B", "absent": ["Fever"]}]
        if query is pgc._DRUG_EFFECTS:
            return [{"drug": "Ibuprofen", "symptom": "Pruritus"}]
        if query is pgc._CONTRAINDICATIONS:
            return []
        if query is kgs._DISEASE_PROFILE_QUERY:
            return [{"did": "5083", "dname": "psoriasis", "pid": "962", "pname": "Hyperkeratosis", "rel": "DISEASE_PHENOTYPE_POSITIVE", "degree": 1},
                    {"did": "5083", "dname": "psoriasis", "pid": "1945", "pname": "Fever", "rel": "DISEASE_PHENOTYPE_NEGATIVE", "degree": 100},
                    {"did": "7", "dname": "no edges", "pid": None, "pname": None, "rel": None, "degree": 0}]
        if query is kgs._DISEASE_PHENOTYPES_QUERY:
            return [{"did": d, "pid": "1945" if d == "5083" else "2", "pname": "Fever" if d == "5083" else "Other", "degree": 3} for d in params["dids"]]
        return []


class KgV3ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_api.router)
        self.neo = FakeNeo4j()
        app.dependency_overrides[get_knowledge_graph_service] = lambda: KnowledgeGraphService(self.neo)  # type: ignore[arg-type]
        self.client = TestClient(app)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        res = self.client.post(path, json=body, headers=HEADERS)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["data"]

    def test_rank_diseases_returns_ids_and_penalizes_absent(self):
        data = self.post("/internal/kg/rank-diseases", {
            "present": [{"type": "effect/phenotype", "id": "989"}, {"type": "effect/phenotype", "id": "mất"}],
            "absent": [{"type": "effect/phenotype", "id": "1945"}],
        })
        self.assertEqual([(d["id"], d["score"]) for d in data], [("5083", 3.0)])  # B: 1.5 - 2.0 < 0 → bỏ
        candidates = next(p for q, p in self.neo.calls if q is pgc._CANDIDATES)
        self.assertEqual((candidates["seed_ids"], candidates["edge_sources"]), (["e-989"], ["KG", "DOC"]))

    def test_rank_diseases_without_resolved_nodes_is_empty(self):
        self.assertEqual(self.post("/internal/kg/rank-diseases", {"present": [{"type": "effect/phenotype", "id": "mất"}]}), [])

    def test_disease_profile_weights(self):
        data = self.post("/internal/kg/disease-profile", {"disease_ids": ["5083", "7", "999"]})
        self.assertEqual(data["5083"]["positive"], [{"id": "962", "name": "Hyperkeratosis", "weight": 2.731}])
        self.assertEqual((data["5083"]["name"], data["5083"]["negative"][0]["id"]), ("psoriasis", "1945"))
        self.assertEqual(data["7"], {"name": "no edges", "positive": [], "negative": []})
        self.assertNotIn("999", data)

    def test_drug_notes(self):
        data = self.post("/internal/kg/drug-notes", {"drugs": [{"type": "drug", "id": "DB1"}], "symptoms": [{"type": "effect/phenotype", "id": "989"}]})
        self.assertEqual(data, ["Thuốc đang dùng Ibuprofen có thể gây Pruritus (tác dụng phụ ghi trong đồ thị)."])

    def test_discriminating_questions_by_ids_skips_name_lookup(self):
        data = self.post("/internal/kg/discriminating-questions", {"disease_ids": ["5083", "4980"], "known_phenotype_ids": []})
        self.assertIn(["5083"], [q["present_in"] for q in data["questions"]])
        params = next(p for q, p in self.neo.calls if q is kgs._DISEASE_PHENOTYPES_QUERY)
        self.assertEqual(params["edge_sources"], ["KG", "DOC"])


if __name__ == "__main__":
    unittest.main()
