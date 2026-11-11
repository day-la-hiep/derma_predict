import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.config.settings import settings
from app.reasoning.description_fact_extractor import DescriptionExtractionError, extract_facts_from_description
from app.reasoning.patient_fact_extractor import ExtractedFact, ExtractedFacts


class FakeStructured:
    def __init__(self, result: Any) -> None:
        self.result, self.calls = result, 0

    async def ainvoke(self, _messages: Any) -> Any:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeModel:
    def __init__(self, structured: FakeStructured) -> None:
        self._structured = structured

    def with_structured_output(self, *_a: Any, **_k: Any) -> FakeStructured:
        return self._structured


def fact(label: str, detail: str, kind: str = "lesion") -> ExtractedFact:
    return ExtractedFact(template_label=label, fact_type=kind, detail=detail)  # type: ignore[arg-type]


class DescriptionFactsTest(unittest.TestCase):
    def _run(self, result: Any, known: list[dict[str, Any]] | None = None, text: str = "mảng đỏ bờ rõ 2cm ở khuỷu tay") -> tuple[Any, FakeStructured]:
        structured = FakeStructured(result)
        with patch("app.reasoning.description_fact_extractor.get_model", return_value=FakeModel(structured)):
            return asyncio.run(extract_facts_from_description(text, known or [])), structured

    def test_blank_description_skips_llm(self):
        out, s = self._run(ExtractedFacts(), text="  ")
        self.assertEqual((out, s.calls), ([], 0))

    def test_returns_facts_and_drops_identical_known(self):
        known = [{"fact_type": "symptom", "template_label": "Ngứa", "detail": "về đêm"}]
        result = ExtractedFacts(facts=[fact("Mảng đỏ", "bờ rõ 2cm"), fact("ngứa", "về đêm", "symptom"), fact("Ngứa", "liên tục", "symptom")])
        out, _ = self._run(result, known)
        # "ngứa / về đêm" trùng hệt nên bỏ; "Ngứa / liên tục" đổi giá trị nên giữ để clinical ghi đè
        self.assertEqual([(f["label"], f["detail"]) for f in out], [("Mảng đỏ", "bờ rõ 2cm"), ("Ngứa", "liên tục")])

    def test_failure_raises_after_retry(self):
        structured = FakeStructured(RuntimeError("boom"))
        with patch("app.reasoning.description_fact_extractor.get_model", return_value=FakeModel(structured)):
            with self.assertRaises(DescriptionExtractionError):
                asyncio.run(extract_facts_from_description("mảng đỏ", []))
        self.assertEqual(structured.calls, 2)


class EndpointTest(unittest.TestCase):
    def setUp(self):
        from app.main import handle_app_error
        from derma_shared.errors import AppError

        app = FastAPI()
        app.add_exception_handler(AppError, handle_app_error)
        app.include_router(router)
        self.client = TestClient(app)
        self.headers = {"X-Internal-Key": settings.INTERNAL_API_KEY}

    def test_requires_internal_key(self):
        self.assertEqual(self.client.post("/internal/extract-facts-from-description", json={"description": "x"}).status_code, 403)

    def test_success_wraps_in_data(self):
        structured = FakeStructured(ExtractedFacts(facts=[fact("Mảng đỏ", "bờ rõ")]))
        with patch("app.reasoning.description_fact_extractor.get_model", return_value=FakeModel(structured)):
            r = self.client.post("/internal/extract-facts-from-description", headers=self.headers, json={"description": "mảng đỏ bờ rõ", "body_site": "tay"})
        self.assertEqual(r.json(), {"data": {"facts": [{"fact_type": "lesion", "label": "Mảng đỏ", "detail": "bờ rõ"}]}})

    def test_llm_failure_is_502_with_message(self):
        structured = FakeStructured(RuntimeError("boom"))
        with patch("app.reasoning.description_fact_extractor.get_model", return_value=FakeModel(structured)):
            r = self.client.post("/internal/extract-facts-from-description", headers=self.headers, json={"description": "mảng đỏ"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("Chưa chuyển được mô tả", r.json()["detail"])
