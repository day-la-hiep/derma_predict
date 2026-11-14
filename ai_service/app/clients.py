from typing import Any

import httpx


class ClinicalClient:
    """Gọi clinical: ghi giả thuyết và ảnh của lượt (fact ghi vào graph qua knowledge)."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

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

    async def get_link_candidates(self, mentions: list[dict[str, str]], limit: int = 6) -> list[dict[str, Any]]:
        """Mỗi mention `{text, text_en, object_type}` → `{exact: {id, name} | None, candidates: [{id, name}]}`, cùng thứ tự."""
        return await self._post("/internal/kg/link-candidates", {"mentions": mentions, "limit": limit})

    async def rank_diseases(self, present: list[dict[str, str]], absent: list[dict[str, str]], top_k: int = 12) -> list[dict[str, Any]]:
        """Nút `{type, id}` → `[{id, name, score, why, absent}]` (id bệnh PrimeKG, chưa có tiền tố)."""
        return await self._post("/internal/kg/rank-diseases", {"present": present, "absent": absent, "top_k": top_k})

    async def get_disease_ids(self, names: list[str]) -> dict[str, list[str]]:
        return await self._post("/internal/kg/disease-ids", {"names": names})

    async def get_disease_profiles(self, disease_ids: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """id bệnh (không tiền tố) → `{positive: [{id, name, weight}], negative: [...]}`."""
        return await self._post("/internal/kg/disease-profile", {"disease_ids": disease_ids})

    async def get_drug_notes(self, drugs: list[dict[str, str]], symptoms: list[dict[str, str]], disease_names: list[str]) -> list[str]:
        return await self._post("/internal/kg/drug-notes", {"drugs": drugs, "symptoms": symptoms, "disease_names": disease_names})

    async def get_discriminating_questions_by_ids(self, disease_ids: list[str], known_phenotype_ids: list[str], top_k: int = 3) -> dict[str, Any]:
        return await self._post("/internal/kg/discriminating-questions", {"disease_ids": disease_ids, "known_phenotype_ids": known_phenotype_ids, "top_k": top_k})

    async def apply_patient_facts(self, patient_id: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
        """Ghi fact vào graph theo dõi; trả `{applied, skipped: [{index, reason}], lesions}`."""
        return await self._post("/internal/patient-facts/apply", {"patient_id": patient_id, "facts": facts})

    async def get_patient_facts(self, patient_id: str) -> dict[str, Any]:
        """Fact hiện hành: `{lesions: [{id, site_text, scope}], facts: [...]}`."""
        response = await self._http.get(f"/internal/patient-facts/{patient_id}")
        response.raise_for_status()
        return response.json()["data"]

    async def get_patient_graph_context(self, patient_id: str, top_k: int = 5) -> dict[str, Any]:
        """Bệnh ứng viên, triệu chứng nên hỏi tiếp, ghi chú thuốc và trích dẫn sách mở rộng từ fact đã khớp nút của bệnh nhân."""
        response = await self._http.get(f"/internal/patient-facts/{patient_id}/context", params={"top_k": top_k})
        response.raise_for_status()
        return response.json()["data"]

    async def get_discriminating_questions(self, diseases: list[str], known_phenotype_ids: list[str] | None = None, top_k: int = 3) -> dict[str, Any]:
        return await self._post("/internal/kg/discriminating-questions", {"diseases": diseases, "known_phenotype_ids": known_phenotype_ids, "top_k": top_k})
