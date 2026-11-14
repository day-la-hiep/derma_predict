import asyncio
import unittest
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_api
from app.api.deps import get_patient_fact_linker
from app.api.exception_handler import register_exception_handlers
from app.config.settings import settings
from app.services.patient_fact_linker import PatientFactLinker

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}


class FakeNeo4j:
    def __init__(self, exact: dict[str, dict[str, str]], loose: list[dict[str, str]], xrefs: list[str] | None = None,
                 phenotypes: dict[str, str] | None = None) -> None:
        self.exact, self.loose, self.xrefs, self.phenotypes = exact, loose, xrefs or [], phenotypes or {}
        self.calls: list[dict[str, Any]] = []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append(params)
        if "xrefs" in query:
            return [{"xrefs": self.xrefs}]
        if "ids" in params:
            return [{"id": i, "name": self.phenotypes[i]} for i in params["ids"] if i in self.phenotypes][:1]
        if "names" in params:
            return [self.exact[n] for n in params["names"] if n in self.exact][:1]
        return self.loose[: params["limit"]]


def linker(exact: dict[str, dict[str, str]] | None = None, loose: list[dict[str, str]] | None = None, **kw: Any) -> tuple[PatientFactLinker, FakeNeo4j]:
    neo = FakeNeo4j(exact or {}, loose or [], **kw)
    return PatientFactLinker(neo), neo  # type: ignore[arg-type]


class FindLinkCandidatesTest(unittest.TestCase):
    def test_exact_by_english_name_skips_loose(self):
        lk, neo = linker(exact={"pruritus": {"id": "1", "name": "Pruritus"}})
        out = asyncio.run(lk.find_link_candidates("ngứa", "pruritus", "effect/phenotype"))
        self.assertEqual(out["exact"], {"id": "1", "name": "Pruritus", "score": 1.0})
        self.assertIsNone(out["xref"])
        self.assertEqual(len(neo.calls), 1)

    def test_exact_by_original_text_when_english_misses(self):
        lk, _ = linker(exact={"eczema": {"id": "2", "name": "eczema"}})
        out = asyncio.run(lk.find_link_candidates("eczema", "atopic thing", "disease"))
        self.assertEqual(out["exact"]["id"], "2")

    def test_loose_candidates_when_no_exact(self):
        lk, neo = linker(loose=[{"id": "4", "name": "Vesicular rash of the palms"}, {"id": "3", "name": "Vesicle"}])
        out = asyncio.run(lk.find_link_candidates("mụn nước", "vesicle", "effect/phenotype"))
        self.assertIsNone(out["exact"])
        self.assertEqual([c["id"] for c in out["candidates"]], ["3", "4"])  # giống tên hơn xếp trước
        self.assertTrue(all(c["score"] <= 0.6 for c in out["candidates"]))
        self.assertEqual(neo.calls[-1]["name"], "vesicle")

    def test_dermo_exact_maps_to_primekg_phenotype_via_hpo_xref(self):
        lk, _ = linker(exact={"plaque": {"id": "DERMO:9", "name": "plaque"}}, xrefs=['SNOMEDCT:1 "x"', 'HP:0011138 "Plaque"'], phenotypes={"11138": "Plaque"})
        out = asyncio.run(lk.find_link_candidates("mảng", "plaque", "dermo"))
        self.assertEqual(out["xref"], {"type": "effect/phenotype", "id": "11138", "name": "Plaque"})


class LinkCandidatesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(internal_api.router)
        lk, _ = linker(exact={"fever": {"id": "9", "name": "Fever"}})
        app.dependency_overrides[get_patient_fact_linker] = lambda: lk
        self.client = TestClient(app)

    def test_returns_one_result_per_mention(self):
        body = {"mentions": [{"text": "sốt", "text_en": "fever", "object_type": "effect/phenotype"}, {"text": "lạ", "object_type": "drug"}]}
        res = self.client.post("/internal/kg/link-candidates", json=body, headers=HEADERS)
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data[0]["exact"]["id"], "9")
        self.assertEqual(data[1], {"exact": None, "candidates": [], "xref": None})

    def test_rejects_unknown_type(self):
        res = self.client.post("/internal/kg/link-candidates", json={"mentions": [{"text": "x", "object_type": "gene"}]}, headers=HEADERS)
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
