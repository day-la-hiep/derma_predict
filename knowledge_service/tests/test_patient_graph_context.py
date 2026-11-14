import unittest
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_patient_fact_api
from app.api.deps import get_patient_graph_context_service
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.dto.patient_fact import PatientFactOutput, PatientFactsOutput, PatientGraphContextOutput
from app.infra.neo4j_client import Neo4jClient
from app.services import patient_graph_context_service as module
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.patient_fact_graph_service import PatientFactGraphService
from app.services.patient_fact_relations import get_expansion_relations
from app.services.patient_graph_context_service import MAX_SEEDS, PatientGraphContextService

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}
PH = "effect/phenotype"


def out(label: str, relation: str = "PT_HAS_SYMPTOM", node: str | None = "n1", object_type: str = PH, **kwargs: Any) -> PatientFactOutput:
    data: dict[str, Any] = {
        "lesion_id": None, "category": 1, "relation": relation, "label": label, "kg_name": label.upper(), "object_type": object_type,
        "kg_node_id": node, "present": True, "status": "current", "stale": False,
    }
    return PatientFactOutput(**{**data, **kwargs})


class FakeFacts:
    def __init__(self, facts: list[PatientFactOutput]) -> None:
        self.facts = facts

    async def get_current_facts(self, patient_id: str, include_history: bool = False) -> PatientFactsOutput:
        return PatientFactsOutput(lesions=[], facts=self.facts)


class FakeKg:
    def __init__(self, candidates: list[dict[str, Any]], absent: list[dict[str, Any]] | None = None) -> None:
        self.candidates, self.absent = candidates, absent or []
        self.queries: dict[str, dict[str, Any]] = {}

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if query is module._RESOLVE_SEEDS:
            return [{"eid": f"e-{p['id']}", "type": p["type"], "id": p["id"], "name": f"nút {p['id']}"} for p in params["pairs"] if p["id"] != "mất"]
        name = {module._CANDIDATES: "candidates", module._ABSENT_PHENOTYPES: "absent", module._DRUG_EFFECTS: "effects", module._CONTRAINDICATIONS: "contra"}[query]  # type: ignore[index]
        self.queries[name] = params
        return {"candidates": self.candidates, "absent": self.absent, "effects": [{"drug": "Ibuprofen", "symptom": "Pruritus"}], "contra": [{"drug": "Ibuprofen", "disease": "A"}]}[name]

    async def discriminating_questions(self, diseases: list[str], known: list[str], top_k: int) -> dict[str, Any]:
        self.queries["questions"] = {"diseases": diseases, "known": known}
        return {"questions": [{"phenotype": "Fever", "present_in": [diseases[0]], "absent_in": diseases[1:]}]}


class FakeDocs:
    async def query_document_graph(self, entity: str, relation: str | None, limit: int) -> list[dict[str, Any]]:
        return [{"display": "phenotype present", "object": "Pruritus", "evidence": f"{entity} gây ngứa", "pages": [7], "document_id": "d1"}, {"evidence": ""}]


def service(facts: list[PatientFactOutput], kg: FakeKg) -> PatientGraphContextService:
    return PatientGraphContextService(FakeFacts(facts), kg, FakeDocs())  # type: ignore[arg-type]


class ExpansionRelationsTest(unittest.TestCase):
    def test_table(self) -> None:
        self.assertEqual(get_expansion_relations("PT_HAS_SYMPTOM"), ("DISEASE_PHENOTYPE_POSITIVE",))
        self.assertEqual(get_expansion_relations("PT_HAS_MORPHOLOGY", present=False), ("DISEASE_PHENOTYPE_NEGATIVE",))
        self.assertIn("DRUG_EFFECT", get_expansion_relations("PT_TAKES_DRUG"))
        self.assertEqual(get_expansion_relations("PT_HAS_HISTORY"), ("DISEASE_DISEASE",))
        self.assertEqual(get_expansion_relations("PT_EXPOSED_TO"), ("EXPOSURE_DISEASE",))
        self.assertEqual(get_expansion_relations("PT_TRIGGERED_BY"), ("EXPOSURE_DISEASE",))
        self.assertEqual(get_expansion_relations("PT_HAS_ATTRIBUTE"), ())


class ContextServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_expands_from_matched_nodes_only(self) -> None:
        kg = FakeKg([{"name": "A", "score": 3.0, "why": ["triệu chứng: x"]}, {"name": "B", "score": 2.0, "why": []}, {"name": "C", "score": 1.0, "why": []}])
        facts = [out("ngứa", node="1"), out("chưa khớp", node=None), out("kích thước", relation="PT_HAS_ATTRIBUTE", node=None), out("ibuprofen", "PT_TAKES_DRUG", "DB1", "drug", kind="taking")]
        result = await service(facts, kg).get_context("p1")
        self.assertEqual([c.name for c in result.candidates], ["A", "B", "C"])
        self.assertEqual(result.unmatched, ["chưa khớp"])  # thuộc tính chữ không tính là "chưa khớp"
        self.assertEqual(kg.queries["candidates"]["seed_ids"], ["e-1", "e-DB1"])
        self.assertEqual(kg.queries["candidates"]["edge_sources"], ["KG", "DOC"])  # cả cạnh trích từ sách, không theo KG_EDGE_SOURCES toàn cục
        self.assertEqual(kg.queries["questions"], {"diseases": ["A", "B", "C"], "known": ["1"]})
        self.assertEqual(result.drug_notes[0], "Thuốc đang dùng Ibuprofen có thể gây Pruritus (tác dụng phụ ghi trong đồ thị).")
        self.assertIn("chống chỉ định với A", result.drug_notes[1])
        self.assertEqual([(e.disease, e.evidence, e.pages) for e in result.book_evidence[:1]], [("A", "A gây ngứa", [7])])

    async def test_absent_symptom_penalizes_but_does_not_remove_unless_score_drops_to_zero(self) -> None:
        kg = FakeKg(
            [{"name": "A", "score": 3.0, "why": []}, {"name": "B", "score": 2.5, "why": []}, {"name": "C", "score": 2.0, "why": []}],
            absent=[{"name": "A", "absent": ["Fever"]}, {"name": "C", "absent": ["Fever"]}],
        )
        facts = [out("ngứa", node="1"), out("sốt", node="2", relation="PT_HAS_SYMPTOM", category=1, present=False)]
        result = await service(facts, kg).get_context("p1")
        self.assertEqual([(c.name, c.score, c.absent) for c in result.candidates], [("B", 2.5, []), ("A", 1.0, ["Fever"])])  # C: 2.0 - 2.0 = 0 → bỏ
        self.assertEqual(kg.queries["absent"]["absent_ids"], ["e-2"])
        self.assertEqual(kg.queries["questions"]["known"], ["1", "2"])  # triệu chứng đã biết có/không đều không hỏi lại

    async def test_family_history_and_allergy_do_not_seed(self) -> None:
        kg = FakeKg([])
        facts = [
            out("chàm của mẹ", "PT_HAS_HISTORY", "D1", "disease", of="family"),
            out("penicillin", "PT_TAKES_DRUG", "DB2", "drug", kind="allergy"),
            out("chàm", "PT_HAS_HISTORY", "D2", "disease", of="self"),
        ]
        result = await service(facts, kg).get_context("p1")
        self.assertEqual(kg.queries["candidates"]["seed_ids"], ["e-D2"])
        self.assertEqual([m.label for m in result.matched], ["chàm"])

    async def test_no_matched_node_returns_note_without_query(self) -> None:
        kg = FakeKg([])
        result = await service([out("khó chịu", node=None)], kg).get_context("p1")
        self.assertEqual((result.candidates, result.matched), ([], []))
        self.assertIn("Chưa có dữ kiện nào khớp nút", result.notes[0])
        self.assertEqual(kg.queries, {})

    async def test_node_missing_from_graph_is_logged_and_skipped(self) -> None:
        kg = FakeKg([{"name": "A", "score": 1.0, "why": []}])
        with self.assertLogs("app.services.patient_graph_context_service", level="WARNING"):
            result = await service([out("ngứa", node="1"), out("lạ", node="mất")], kg).get_context("p1")
        self.assertEqual(kg.queries["candidates"]["seed_ids"], ["e-1"])
        self.assertEqual(len(result.candidates), 1)

    async def test_caps_seed_count_with_note(self) -> None:
        kg = FakeKg([])
        facts = [out(f"f{i}", node=str(i)) for i in range(MAX_SEEDS + 5)]
        result = await service(facts, kg).get_context("p1")
        self.assertEqual(len(kg.queries["candidates"]["seed_ids"]), MAX_SEEDS)
        self.assertIn(f"{MAX_SEEDS}/{MAX_SEEDS + 5}", result.notes[0])


class FakeContextService:
    async def get_context(self, patient_id: str, top_k: int = 5) -> PatientGraphContextOutput:
        return PatientGraphContextOutput(matched=[], unmatched=[patient_id, str(top_k)], candidates=[], questions=[], drug_notes=[], book_evidence=[], notes=[])


class ContextApiTest(unittest.TestCase):
    def test_endpoint_clamps_top_k(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_patient_fact_api.router)
        app.dependency_overrides[get_patient_graph_context_service] = lambda: FakeContextService()
        client = TestClient(app)
        self.assertEqual(client.get("/internal/patient-facts/p1/context").status_code, 403)
        self.assertEqual(client.get("/internal/patient-facts/p1/context?top_k=99", headers=HEADERS).json()["data"]["unmatched"], ["p1", "10"])
        self.assertEqual(client.get("/internal/patient-facts/p1/context?top_k=0", headers=HEADERS).json()["data"]["unmatched"], ["p1", "1"])


class ContextIntegrationTest(unittest.IsolatedAsyncioTestCase):
    PATIENT = "test-ptfact-ctx"

    async def asyncSetUp(self) -> None:
        self.neo4j = Neo4jClient.from_settings()
        try:
            await self.neo4j.run("RETURN 1 AS ok")
        except Exception:  # noqa: BLE001
            await self.neo4j.close()
            self.skipTest("cần Neo4j dev đang chạy (make infra)")
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.neo4j.close()

    async def _cleanup(self) -> None:
        await self.neo4j.run("MATCH (p:Patient {id: $pid}) OPTIONAL MATCH (p)-[:PT_HAS_LESION]->(l:PtLesion) DETACH DELETE l, p", pid=self.PATIENT)
        await self.neo4j.run("MATCH (o:PtLiteral) WHERE o.key STARTS WITH $pid DETACH DELETE o", pid=self.PATIENT)

    async def test_patient_facts_expand_through_real_graph_and_never_reach_pt_edges(self) -> None:
        from app.dto.patient_fact import PatientFactInput as Input

        facts = PatientFactGraphService(self.neo4j)
        lesion = "test-ptfact-ctx-l1"
        await facts.apply_facts(self.PATIENT, [
            Input(category=1, label="ngứa", object_type=PH, kg_node_id="989", lesion_id=lesion),
            Input(category=2, label="ban đỏ", object_type=PH, kg_node_id="10783", lesion_id=lesion),
            Input(category=5, label="ibuprofen", object_type="drug", kg_node_id="DB01050", kind="taking"),
            Input(category=1, label="khó chịu", lesion_id=lesion),  # chưa khớp nút
        ])
        result = await PatientGraphContextService(facts, KnowledgeGraphService(self.neo4j), FakeDocs()).get_context(self.PATIENT)  # type: ignore[arg-type]
        self.assertEqual([m.kg_name for m in result.matched], ["Pruritus", "Erythema", "Ibuprofen"])
        self.assertEqual(result.unmatched, ["khó chịu"])
        self.assertTrue(result.candidates)
        self.assertTrue(all(any("Pruritus" in w or "Erythema" in w for w in c.why) for c in result.candidates))
        self.assertTrue(any("Ibuprofen" in n and "Pruritus" in n for n in result.drug_notes))
        names = {c.name for c in result.candidates}
        self.assertFalse(names & {"Pruritus", "Erythema", "Ibuprofen"})  # chỉ ra bệnh, không lẫn nút phenotype/thuốc đầu vào


if __name__ == "__main__":
    unittest.main()
