import asyncio
import unittest
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_patient_fact_api
from app.api.deps import get_patient_fact_graph_service
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.dto.patient_fact import PatientFactInput, PatientFactsApplyOutput, PatientFactsOutput, ProfileFactItem
from app.infra.neo4j_client import Neo4jClient
from app.services.patient_fact_graph_service import PatientFactError, derive_fact_type, PatientFactGraphService, build_upsert_query, resolve_spec
from app.services.patient_fact_linker import PatientFactLinker, build_exact_query

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


def fact(category: int, label: str, **kwargs: Any) -> PatientFactInput:
    return PatientFactInput(category=category, label=label, **kwargs)


class ResolveSpecTest(unittest.TestCase):
    def test_each_category_maps_to_expected_relation(self) -> None:
        cases = [
            (fact(1, "ngứa"), "PT_HAS_SYMPTOM", "lesion", False),
            (fact(1, "sốt", scope="body"), "PT_HAS_SYMPTOM", "patient", False),
            (fact(2, "dát đỏ"), "PT_HAS_MORPHOLOGY", "lesion", False),
            (fact(2, "vảy tiết", kind="secondary"), "PT_HAS_MORPHOLOGY", "lesion", False),
            (fact(3, "đối xứng hai bên", name="distribution"), "PT_HAS_ATTRIBUTE", "lesion", True),
            (fact(3, "CRP 12", name="crp", scope="body"), "PT_HAS_ATTRIBUTE", "patient", True),
            (fact(4, "nắng", effect="aggravate"), "PT_TRIGGERED_BY", "lesion", False),
            (fact(4, "thợ làm tóc"), "PT_EXPOSED_TO", "patient", False),
            (fact(5, "ibuprofen", object_type="drug"), "PT_TAKES_DRUG", "patient", False),
            (fact(5, "chàm", object_type="disease"), "PT_HAS_HISTORY", "patient", False),
        ]
        for f, relation, subject, single in cases:
            with self.subTest(category=f.category, label=f.label):
                spec = resolve_spec(f)
                assert spec is not None
                self.assertEqual((spec.relation, spec.subject, spec.single_valued), (relation, subject, single))

    def test_location_has_no_edge(self) -> None:
        self.assertIsNone(resolve_spec(fact(3, "khuỷu tay", name="location")))
        self.assertIsNone(resolve_spec(fact(3, "khuỷu tay", name="Vị trí")))  # alias tiếng Việt

    def test_props_follow_category(self) -> None:
        self.assertEqual(resolve_spec(fact(2, "dát")).props, {"kind": "primary"})  # type: ignore[union-attr]
        self.assertEqual(resolve_spec(fact(2, "vảy", kind="secondary")).props, {"kind": "secondary"})  # type: ignore[union-attr]
        self.assertEqual(resolve_spec(fact(3, "tái phát", name="Diễn biến")).props, {"name": "course"})  # type: ignore[union-attr]
        self.assertEqual(resolve_spec(fact(5, "mẹ bị chàm", of="family")).props, {"of": "family"})  # type: ignore[union-attr]

    def test_fact_type_follows_category(self) -> None:
        self.assertEqual(derive_fact_type(1, "", ""), "symptom")
        self.assertEqual(derive_fact_type(3, "", ""), "lesion")
        self.assertEqual(derive_fact_type(3, "", "", on_body=True), "other")
        self.assertEqual(derive_fact_type(4, "", "", effect="trigger"), "other")
        self.assertEqual(derive_fact_type(4, "", ""), "history")
        self.assertEqual(derive_fact_type(5, "drug", "allergy"), "allergy")

    def test_invalid_input_raises(self) -> None:
        for f in [fact(3, "đỏ"), fact(4, "nắng", effect="khac"), fact(2, "dát", kind="khac"), fact(5, "x", object_type="drug", kind="khac")]:
            with self.subTest(category=f.category):
                with self.assertRaises(PatientFactError):
                    resolve_spec(f)

    def test_upsert_query_rejects_unknown_parts(self) -> None:
        with self.assertRaises(ValueError):
            build_upsert_query("Patient", "PT_HAS_SYMPTOM) DETACH DELETE (x", "literal")
        with self.assertRaises(ValueError):
            build_upsert_query("Person", "PT_HAS_SYMPTOM", "literal")


class FakeService:
    async def apply_facts(self, patient_id: str, facts: list[PatientFactInput]) -> PatientFactsApplyOutput:
        return PatientFactsApplyOutput(applied=len(facts), skipped=[], lesions=[])

    async def get_current_facts(self, patient_id: str, include_history: bool = False) -> PatientFactsOutput:
        return PatientFactsOutput(lesions=[], facts=[])

    async def get_long_term_facts(self, patient_ids: list[str]) -> dict[str, list[Any]]:
        return {pid: [] for pid in patient_ids}

    async def replace_profile_facts(self, patient_id: str, items: list[ProfileFactItem]) -> list[Any]:
        return []


class PatientFactApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_patient_fact_api.router)
        app.dependency_overrides[get_patient_fact_graph_service] = lambda: FakeService()
        self.client = TestClient(app)

    def test_requires_internal_key(self) -> None:
        self.assertEqual(self.client.get("/internal/patient-facts/p1").status_code, 403)

    def test_apply_and_get(self) -> None:
        body = {"patient_id": "p1", "facts": [{"category": 1, "label": "ngứa", "lesion_key": "l1"}]}
        r = self.client.post("/internal/patient-facts/apply", json=body, headers=HEADERS)
        self.assertEqual(r.json()["data"]["applied"], 1)
        self.assertEqual(self.client.get("/internal/patient-facts/p1", headers=HEADERS).json()["data"], {"lesions": [], "facts": []})

    def test_long_term_route_is_not_swallowed_by_patient_id_route(self) -> None:
        r = self.client.get("/internal/patient-facts/long-term?profile_ids=a, b,,c", headers=HEADERS)
        self.assertEqual(r.json()["data"], {"a": [], "b": [], "c": []})

    def test_profile_replace_validates_fact_type(self) -> None:
        ok = self.client.put("/internal/patient-facts/p1/profile", json={"facts": [{"fact_type": "allergy", "label": "penicillin"}]}, headers=HEADERS)
        self.assertEqual((ok.status_code, ok.json()["data"]), (200, []))
        bad = self.client.put("/internal/patient-facts/p1/profile", json={"facts": [{"fact_type": "symptom", "label": "ngứa"}]}, headers=HEADERS)
        self.assertEqual(bad.status_code, 422)

    def test_rejects_category_out_of_range(self) -> None:
        body = {"patient_id": "p1", "facts": [{"category": 6, "label": "x"}]}
        self.assertEqual(self.client.post("/internal/patient-facts/apply", json=body, headers=HEADERS).status_code, 422)


def _neo4j_available() -> bool:
    async def ping() -> bool:
        client = Neo4jClient.from_settings()
        try:
            await client.run("RETURN 1 AS ok")
            return True
        except Exception:  # noqa: BLE001  # không có Neo4j thì bỏ qua test tích hợp
            return False
        finally:
            await client.close()

    return asyncio.run(ping())


@unittest.skipUnless(_neo4j_available(), "cần Neo4j dev đang chạy (make infra)")
class PatientFactGraphIntegrationTest(unittest.IsolatedAsyncioTestCase):
    PATIENT = "test-ptfact-patient"
    OTHER = "test-ptfact-other"
    # id nút trong đồ thị nền dev (PrimeKG/HPO/DrugBank)
    PRURITUS, FEVER, IBUPROFEN = "989", "1945", "DB01050"

    async def asyncSetUp(self) -> None:
        self.neo4j = Neo4jClient.from_settings()
        self.service = PatientFactGraphService(self.neo4j)
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.neo4j.close()

    async def _cleanup(self) -> None:
        # chỉ xoá nút do chính test này tạo (id bắt đầu bằng test-ptfact-)
        for pid in (self.PATIENT, self.OTHER):
            await self.neo4j.run(
                "MATCH (p:Patient {id: $pid}) OPTIONAL MATCH (p)-[:PT_HAS_LESION]->(l:PtLesion) DETACH DELETE l, p", pid=pid
            )
        await self.neo4j.run("MATCH (o:PtLiteral) WHERE o.key STARTS WITH 'test-ptfact-' DETACH DELETE o")

    async def _facts(self, **kwargs: Any) -> PatientFactsOutput:
        return await self.service.get_current_facts(self.PATIENT, **kwargs)

    async def test_lesion_and_symptom_with_kg_node(self) -> None:
        moment = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
        result = await self.service.apply_facts(self.PATIENT, [
            fact(3, "mặt trong khuỷu tay hai bên", name="location", lesion_key="l1", observed_at=moment),
            fact(1, "ngứa", lesion_key="l1", object_type="effect/phenotype", kg_node_id=self.PRURITUS, link_method="llm",
                 onset_text="2 tuần", source_message_id="m1", observed_at=moment),
            fact(4, "ra nắng", lesion_key="l1", effect="aggravate", observed_at=moment),
        ])
        self.assertEqual((result.applied, result.skipped), (3, []))
        state = await self._facts()
        self.assertEqual([(l.site_text, l.scope) for l in state.lesions], [("mặt trong khuỷu tay hai bên", "skin")])
        by_label = {f.label: f for f in state.facts}
        itch = by_label["ngứa"]
        self.assertEqual((itch.kg_node_id, itch.object_type, itch.present, itch.onset_text), (self.PRURITUS, "effect/phenotype", True, "2 tuần"))
        self.assertEqual((itch.label, itch.kg_name), ("ngứa", "Pruritus"))
        self.assertEqual(str(itch.onset_at), "2026-10-29")
        self.assertEqual(itch.lesion_id, state.lesions[0].id)
        sun = by_label["ra nắng"]
        self.assertEqual((sun.kg_node_id, sun.effect, sun.object_type), (None, "aggravate", ""))
        # truy vấn tri thức trên cạnh DOC lọc `r.source = 'DOC'`; cạnh bệnh nhân không được mang `source` để không lọt vào đó
        leaked = await self.neo4j.run("MATCH ()-[r]->() WHERE type(r) STARTS WITH 'PT_' AND r.source IS NOT NULL RETURN count(r) AS n")
        self.assertEqual(leaked[0]["n"], 0)

    async def test_repeated_fact_updates_confirmation_without_duplicate(self) -> None:
        first = datetime(2026, 11, 1, tzinfo=UTC)
        later = datetime(2026, 11, 12, tzinfo=UTC)
        item = fact(1, "sốt", scope="body", object_type="effect/phenotype", kg_node_id=self.FEVER)
        await self.service.apply_facts(self.PATIENT, [item.model_copy(update={"observed_at": first})])
        await self.service.apply_facts(self.PATIENT, [item.model_copy(update={"observed_at": later, "present": False})])
        facts = (await self._facts()).facts
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0].present, facts[0].observed_at, facts[0].last_confirmed_at), (False, first.isoformat(), later.isoformat()))

    async def test_resolved_fact_hidden_unless_history(self) -> None:
        item = fact(1, "sốt", scope="body", object_type="effect/phenotype", kg_node_id=self.FEVER)
        await self.service.apply_facts(self.PATIENT, [item])
        await self.service.apply_facts(self.PATIENT, [item.model_copy(update={"resolved": True})])
        self.assertEqual((await self._facts()).facts, [])
        history = (await self._facts(include_history=True)).facts
        self.assertEqual([f.status for f in history], ["resolved"])

    async def test_single_valued_attribute_supersedes(self) -> None:
        size = lambda text, day: fact(3, text, name="kích thước", lesion_key="l1", observed_at=datetime(2026, 11, day, tzinfo=UTC))  # noqa: E731
        await self.service.apply_facts(self.PATIENT, [fact(3, "cẳng tay", name="location", lesion_key="l1"), size("1 cm", 1)])
        await self.service.apply_facts(self.PATIENT, [])
        lesion_id = (await self._facts()).lesions[0].id
        grow = lambda text, day: fact(3, text, name="kích thước", lesion_id=lesion_id, observed_at=datetime(2026, 11, day, tzinfo=UTC))  # noqa: E731
        await self.service.apply_facts(self.PATIENT, [grow("1 cm", 5)])  # cùng giá trị: chỉ nhắc lại
        self.assertEqual([f.label for f in (await self._facts()).facts], ["1 cm"])
        await self.service.apply_facts(self.PATIENT, [grow("3 cm", 10)])
        self.assertEqual([f.label for f in (await self._facts()).facts], ["3 cm"])
        history = (await self._facts(include_history=True)).facts
        self.assertEqual(sorted((f.label, f.status) for f in history), [("1 cm", "superseded"), ("3 cm", "current")])

    async def test_missing_kg_node_falls_back_to_literal(self) -> None:
        await self.service.apply_facts(self.PATIENT, [fact(1, "sốt cao", scope="body", object_type="effect/phenotype", kg_node_id="khong-co")])
        item = (await self._facts()).facts[0]
        self.assertEqual((item.label, item.kg_node_id, item.link_method), ("sốt cao", None, "none"))

    async def test_invalid_fact_is_skipped_others_applied(self) -> None:
        result = await self.service.apply_facts(self.PATIENT, [
            fact(1, "ngứa"),  # thiếu tổn thương
            fact(5, "ibuprofen", object_type="drug", kg_node_id=self.IBUPROFEN, kind="taking"),
        ])
        self.assertEqual((result.applied, [s.index for s in result.skipped]), (1, [0]))
        self.assertEqual([(f.label, f.kg_name, f.kind, f.object_type) for f in (await self._facts()).facts], [("ibuprofen", "Ibuprofen", "taking", "drug")])

    async def test_facts_have_stable_id_and_legacy_fact_type(self) -> None:
        await self.service.apply_facts(self.PATIENT, [
            fact(1, "ngứa", lesion_id="test-ptfact-lesion-t", object_type="effect/phenotype"),
            fact(5, "ibuprofen", object_type="drug", kind="taking"),
            fact(5, "penicillin", object_type="drug", kind="allergy"),
            fact(5, "chàm", object_type="disease", of="family"),
            fact(4, "thợ làm tóc"),
        ])
        first = {f.label: (f.id, f.fact_type) for f in (await self._facts()).facts}
        await self.service.apply_facts(self.PATIENT, [fact(5, "ibuprofen", object_type="drug", kind="taking")])  # nhắc lại: id không đổi
        again = {f.label: f.id for f in (await self._facts()).facts}
        self.assertEqual({k: v[1] for k, v in first.items()}, {"ngứa": "symptom", "ibuprofen": "medication", "penicillin": "allergy", "chàm": "history", "thợ làm tóc": "history"})
        self.assertTrue(all(v[0] for v in first.values()) and len(set(v[0] for v in first.values())) == 5)
        self.assertEqual(first["ibuprofen"][0], again["ibuprofen"])

    async def test_long_term_facts_exclude_lesion_facts_and_cover_each_profile(self) -> None:
        await self.service.apply_facts(self.PATIENT, [fact(1, "ngứa", lesion_id="test-ptfact-lesion-t"), fact(5, "ibuprofen", object_type="drug", kind="taking")])
        got = await self.service.get_long_term_facts([self.PATIENT, self.OTHER])
        self.assertEqual({k: [f.label for f in v] for k, v in got.items()}, {self.PATIENT: ["ibuprofen"], self.OTHER: []})

    async def test_profile_form_replaces_full_list_and_resolves_removed_including_chat_facts(self) -> None:
        item = lambda kind, label, detail="": ProfileFactItem(fact_type=kind, label=label, detail=detail)  # type: ignore[arg-type]  # noqa: E731
        await self.service.apply_facts(self.PATIENT, [fact(5, "hen suyễn", object_type="disease"), fact(1, "ngứa", lesion_id="test-ptfact-lesion-t")])  # từ chat
        first = await self.service.replace_profile_facts(self.PATIENT, [item("allergy", "Penicillin", "nổi mề đay"), item("medication", "Cetirizine")])
        self.assertEqual(sorted((f.fact_type, f.label, f.detail) for f in first), [("allergy", "Penicillin", "nổi mề đay"), ("medication", "Cetirizine", "")])
        self.assertEqual([f.label for f in (await self._facts()).facts if f.fact_type == "symptom"], ["ngứa"])  # fact theo tổn thương không bị form đụng tới
        second = await self.service.replace_profile_facts(self.PATIENT, [item("allergy", "penicillin", "phát ban"), item("history", "chàm")])  # nhãn không phân biệt hoa thường
        self.assertEqual(sorted((f.fact_type, f.label.lower(), f.detail) for f in second), [("allergy", "penicillin", "phát ban"), ("history", "chàm", "")])
        self.assertEqual(first[0].id, [f.id for f in second if f.fact_type == "allergy"][0])  # cùng fact, giữ id
        self.assertEqual((await self.service.replace_profile_facts(self.PATIENT, [])), [])
        history = (await self._facts(include_history=True)).facts
        self.assertEqual({f.status for f in history if f.fact_type in ("allergy", "history", "medication")}, {"resolved"})  # chỉ ẩn, không xoá

    async def test_client_generated_lesion_id_is_created_and_reused(self) -> None:
        lesion = "test-ptfact-lesion-1"
        result = await self.service.apply_facts(self.PATIENT, [fact(1, "ngứa", lesion_id=lesion, site_text="tay", detail="về đêm")])
        self.assertEqual(result.applied, 1)
        await self.service.apply_facts(self.PATIENT, [fact(2, "dát đỏ", lesion_id=lesion)])
        state = await self._facts()
        self.assertEqual([(l.id, l.site_text) for l in state.lesions], [(lesion, "tay")])
        self.assertEqual(sorted((f.label, f.detail, f.lesion_id) for f in state.facts), [("dát đỏ", "", lesion), ("ngứa", "về đêm", lesion)])

    async def test_other_patient_lesion_is_rejected_and_data_not_shared(self) -> None:
        await self.service.apply_facts(self.PATIENT, [fact(3, "mặt", name="location", lesion_key="l1")])
        lesion_id = (await self._facts()).lesions[0].id
        result = await self.service.apply_facts(self.OTHER, [fact(1, "ngứa", lesion_id=lesion_id)])
        self.assertEqual(result.applied, 0)
        self.assertEqual((await self.service.get_current_facts(self.OTHER)).facts, [])
        await self.service.apply_facts(self.OTHER, [fact(4, "thợ làm tóc")])
        await self.service.apply_facts(self.PATIENT, [fact(4, "thợ làm tóc")])
        keys = await self.neo4j.run("MATCH (o:PtLiteral) WHERE o.key ENDS WITH '|thợ làm tóc' AND o.key STARTS WITH 'test-ptfact-' RETURN o.key AS key")
        self.assertEqual(len(keys), 2)


@unittest.skipUnless(_neo4j_available(), "cần Neo4j dev đang chạy (make infra)")
class PatientFactLinkerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.neo4j = Neo4jClient.from_settings()
        self.translated: list[list[tuple[str, str]]] = []

        async def translate(items: list[tuple[str, str]]) -> dict[str, str]:
            self.translated.append(items)
            return {"ngứa": "pruritus", "sốt": "Fever", "ibuprofen": "ibuprofen", "xyz lạ": ""}

        self.linker = PatientFactLinker(self.neo4j, translate)

    async def asyncTearDown(self) -> None:
        await self.neo4j.close()

    async def test_exact_then_translated_then_unmatched(self) -> None:
        facts = [
            fact(1, "Erythema", object_type="effect/phenotype"),  # khớp thẳng không cần dịch
            fact(1, "ngứa", object_type="effect/phenotype"),
            fact(5, "ibuprofen", object_type="drug"),
            fact(1, "xyz lạ", object_type="effect/phenotype"),
            fact(4, "nắng"),  # không có loại nút: không khớp
            fact(1, "đã khớp", object_type="effect/phenotype", kg_node_id="1"),  # có sẵn id: giữ nguyên
        ]
        linked = await self.linker.link_facts(facts)
        self.assertEqual(linked, 3)  # Erythema + ibuprofen khớp thẳng, ngứa nhờ dịch
        got = [(f.kg_node_id, f.link_method) for f in facts]
        self.assertEqual(got, [("10783", "exact"), ("989", "llm"), ("DB01050", "exact"), (None, "none"), (None, "none"), ("1", "none")])
        self.assertEqual(self.translated, [[("ngứa", "effect/phenotype"), ("xyz lạ", "effect/phenotype")]])

    async def test_loose_candidates_are_chosen_by_llm_or_left_empty(self) -> None:
        async def translate(items: list[tuple[str, str]]) -> dict[str, str]:
            return {"mụn nước": "vesicle", "trợt": "erosion", "lạ": "zzzzqqqq"}

        asked: list[list[tuple[str, str, list[str]]]] = []

        async def choose(items: list[tuple[str, str, list[str]]]) -> dict[int, int]:
            asked.append(items)
            at = {label: (position, cands) for position, (label, _, cands) in enumerate(items)}
            position, cands = at["mụn nước"]
            return {position: cands.index("Skin vesicle")}  # trợt: không ứng viên đúng nghĩa

        facts = [fact(2, "mụn nước", object_type="effect/phenotype"), fact(2, "trợt", kind="secondary", object_type="effect/phenotype"), fact(2, "lạ", kind="secondary", object_type="effect/phenotype")]
        linked = await PatientFactLinker(self.neo4j, translate, choose).link_facts(facts)
        self.assertEqual(linked, 1)
        self.assertEqual([(f.link_method) for f in facts], ["llm", "none", "none"])
        self.assertEqual(sorted(label for label, _, _ in asked[0]), ["mụn nước", "trợt"])  # nhãn không có ứng viên nào thì không hỏi LLM
        row = await self.neo4j.run("MATCH (n:Entity:EffectPhenotype {id: $id}) RETURN n.name AS name", id=facts[0].kg_node_id)
        self.assertEqual(row[0]["name"], "Skin vesicle")

    async def test_chooser_failure_keeps_facts_as_text_and_logs(self) -> None:
        async def translate(items: list[tuple[str, str]]) -> dict[str, str]:
            return {"mụn nước": "vesicle"}

        async def broken(_: list[tuple[str, str, list[str]]]) -> dict[int, int]:
            raise RuntimeError("llm chết")

        facts = [fact(2, "mụn nước", object_type="effect/phenotype")]
        with self.assertLogs("app.services.patient_fact_linker", level="ERROR"):
            self.assertEqual(await PatientFactLinker(self.neo4j, translate, broken).link_facts(facts), 0)

    async def test_translator_failure_keeps_facts_as_text_and_logs(self) -> None:
        async def broken(_: list[tuple[str, str]]) -> dict[str, str]:
            raise RuntimeError("llm chết")

        facts = [fact(1, "ngứa", object_type="effect/phenotype")]
        with self.assertLogs("app.services.patient_fact_linker", level="ERROR"):
            self.assertEqual(await PatientFactLinker(self.neo4j, broken).link_facts(facts), 0)
        self.assertIsNone(facts[0].kg_node_id)

    async def test_no_translator_only_exact(self) -> None:
        facts = [fact(1, "ngứa", object_type="effect/phenotype"), fact(1, "fever", scope="body", object_type="effect/phenotype")]
        self.assertEqual(await PatientFactLinker(self.neo4j).link_facts(facts), 1)
        self.assertEqual([f.kg_node_id for f in facts], [None, "1945"])

    def test_exact_query_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            build_exact_query("effect/phenotype) DETACH DELETE (n")


@unittest.skipUnless(_neo4j_available(), "cần Neo4j dev đang chạy (make infra)")
class ApplyWithLinkerTest(unittest.IsolatedAsyncioTestCase):
    PATIENT = "test-ptfact-linked"

    async def asyncSetUp(self) -> None:
        self.neo4j = Neo4jClient.from_settings()

        async def translate(items: list[tuple[str, str]]) -> dict[str, str]:
            return {"ngứa": "pruritus"}

        self.service = PatientFactGraphService(self.neo4j, PatientFactLinker(self.neo4j, translate))
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.neo4j.close()

    async def _cleanup(self) -> None:
        await self.neo4j.run("MATCH (p:Patient {id: $pid}) OPTIONAL MATCH (p)-[:PT_HAS_LESION]->(l:PtLesion) DETACH DELETE l, p", pid=self.PATIENT)
        await self.neo4j.run("MATCH (o:PtLiteral) WHERE o.key STARTS WITH $pid DETACH DELETE o", pid=self.PATIENT)

    async def test_apply_links_node_and_keeps_patient_wording(self) -> None:
        await self.service.apply_facts(self.PATIENT, [fact(1, "ngứa", lesion_id="test-ptfact-linked-l1", object_type="effect/phenotype")])
        item = (await self.service.get_current_facts(self.PATIENT)).facts[0]
        self.assertEqual((item.label, item.kg_name, item.kg_node_id, item.link_method), ("ngứa", "Pruritus", "989", "llm"))


if __name__ == "__main__":
    unittest.main()
