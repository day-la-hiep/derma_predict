from typing import Any

import httpx


class ClinicalClient:
    """Gọi clinical: kéo hồ sơ/fact của bệnh nhân và ghi kết quả lâm sàng của lượt."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get_patient_context(self, profile_id: str) -> dict[str, Any]:
        """`{facts: [{label, fact_type, detail, body_site}]}`."""
        response = await self._http.get(f"/internal/patients/{profile_id}/context")
        response.raise_for_status()
        return response.json()["data"]

    async def apply_turn(self, body: dict[str, Any]) -> None:
        response = await self._http.post("/internal/episodes/apply-turn", json=body)
        response.raise_for_status()


class ConsultationClient:
    """Gọi consultation: thông tin hội thoại, lịch sử tin, báo cáo tiền tư vấn và trả câu trả lời cuối của lượt."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """`{user_id, patient_profile_id, model}`; None khi hội thoại không còn."""
        response = await self._http.get(f"/internal/conversations/{conversation_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()["data"]

    async def get_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Mỗi tin `{sender, content, message_type}`, cũ trước."""
        response = await self._http.get(f"/internal/conversations/{conversation_id}/history")
        response.raise_for_status()
        return response.json()["data"]

    async def get_latest_report_summary(self, profile_id: str, exclude_session_id: str) -> str | None:
        """Tóm tắt báo cáo tiền tư vấn gần nhất của hồ sơ, trừ phiên đang sinh báo cáo."""
        response = await self._http.get(f"/internal/patients/{profile_id}/latest-report", params={"exclude_session_id": exclude_session_id})
        response.raise_for_status()
        return response.json()["data"]["summary"]

    async def save_session_report(self, session_id: str, summary: str, status: str) -> None:
        """Ghi báo cáo tiền tư vấn của phiên (`status` = `ready` | `failed`); consultation sở hữu bảng này và báo cho bác sĩ/bệnh nhân."""
        response = await self._http.post(f"/internal/sessions/{session_id}/report", json={"report_summary": summary, "status": status})
        response.raise_for_status()

    async def post_turn_result(self, message_id: str, body: dict[str, Any]) -> None:
        response = await self._http.post(f"/internal/turns/{message_id}/result", json=body)
        response.raise_for_status()


class KnowledgeClient:
    """Gọi knowledge (retrieval sách/ca bệnh, đồ thị tri thức); lỗi HTTP ném lên để tool tự báo cho model."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        response = await self._http.post(path, json=body)
        response.raise_for_status()
        return response.json()["data"]

    async def search_semantic(self, query: str, limit: int, *, corpus: str = "document", eq: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._post("/internal/search/semantic", {"corpus": corpus, "query": query, "limit": limit, "eq": eq or {}})

    async def search_bm25(self, query: str, limit: int, *, corpus: str = "document", eq: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._post("/internal/search/bm25", {"corpus": corpus, "query": query, "limit": limit, "eq": eq or {}})

    async def search_by_graph(self, names: list[str], limit: int) -> list[dict[str, Any]]:
        return await self._post("/internal/search/graph", {"names": names, "limit": limit})

    async def query_document_graph(self, entity: str, relation: str | None, limit: int) -> list[dict[str, Any]]:
        return await self._post("/internal/graph/document-query", {"entity": entity, "relation": relation, "limit": limit})

    async def run_kg_intent(self, intent: str, entities: list[str], limit: int, translate: bool = True) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
        data = await self._post("/internal/kg/intent", {"intent": intent, "entities": entities, "limit": limit, "translate": translate})
        return data["facts"], data["notes"], data["resolved"]

    async def get_discriminating_questions(self, diseases: list[str], known_phenotype_ids: list[str] | None = None, top_k: int = 3) -> dict[str, Any]:
        return await self._post("/internal/kg/discriminating-questions", {"diseases": diseases, "known_phenotype_ids": known_phenotype_ids, "top_k": top_k})
