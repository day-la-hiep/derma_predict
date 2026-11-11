import asyncio
import json
import unittest
from typing import Any

import httpx

from app.clients import ClinicalClient
from app.clients import ConsultationClient
from app.clients import KnowledgeClient


def make_http(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://svc", transport=httpx.MockTransport(handler), headers={"X-Internal-Key": "k"})


class KnowledgeClientTest(unittest.TestCase):
    def test_search_sends_corpus_query_and_unwraps_data(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"data": [{"chunk_id": "c1"}]})

        client = KnowledgeClient(make_http(handler))
        result = asyncio.run(client.search_semantic("vảy nến", 5, corpus="finalize_report"))
        self.assertEqual(result, [{"chunk_id": "c1"}])
        self.assertEqual(seen[0].url.path, "/internal/search/semantic")
        self.assertEqual(seen[0].headers["X-Internal-Key"], "k")
        self.assertEqual(json.loads(seen[0].content), {"corpus": "finalize_report", "query": "vảy nến", "limit": 5, "eq": {}})

    def test_kg_intent_returns_facts_notes_resolved(self) -> None:
        body = {"data": {"facts": [{"text": "x"}], "notes": ["n"], "resolved": {"matched_nodes": ["a"]}}}
        client = KnowledgeClient(make_http(lambda r: httpx.Response(200, json=body)))
        facts, notes, resolved = asyncio.run(client.run_kg_intent("treatments", ["psoriasis"], 5))
        self.assertEqual((facts, notes, resolved), ([{"text": "x"}], ["n"], {"matched_nodes": ["a"]}))

    def test_http_error_is_raised_for_the_tool_to_report(self) -> None:
        client = KnowledgeClient(make_http(lambda r: httpx.Response(403, json={"detail": "sai khoá"})))
        with self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(client.search_bm25("x", 3))


class ClinicalAndConsultationClientTest(unittest.TestCase):
    def test_patient_context_hits_internal_endpoint(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"data": {"facts": []}})

        asyncio.run(ClinicalClient(make_http(handler)).get_patient_context("pp-1"))
        self.assertEqual(seen[0].url.path, "/internal/patients/pp-1/context")

    def test_get_conversation_returns_none_when_missing(self) -> None:
        client = ConsultationClient(make_http(lambda r: httpx.Response(404, json={"detail": "x"})))
        self.assertIsNone(asyncio.run(client.get_conversation("c1")))

    def test_post_turn_result_targets_message(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"data": None})

        asyncio.run(ConsultationClient(make_http(handler)).post_turn_result("m1", {"status": "done"}))
        self.assertEqual(seen[0].url.path, "/internal/turns/m1/result")


if __name__ == "__main__":
    unittest.main()
