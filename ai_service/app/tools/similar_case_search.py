from typing import Any

from app.tools.hybrid_retrieval.corpus import FINALIZE_REPORT_CORPUS
from app.deps import get_knowledge_client


async def search_similar_cases(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Ca bệnh bác sĩ đã chốt gần `query` nhất (knowledge tìm theo ngữ nghĩa), dạng dict dùng cho tool tìm ca theo ảnh."""
    payloads = await get_knowledge_client().search_semantic(query, limit, corpus=FINALIZE_REPORT_CORPUS.name)
    return [
        {
            "case_id": p.get("case_id"),
            "diagnosis": p.get("diagnosis", ""),
            "gender": p.get("gender"),
            "age": p.get("age"),
            "allergies": p.get("allergies"),
            "medical_history": p.get("medical_history"),
            "clinical_facts": p.get("clinical_facts", []),
            "doctor_reasoning": p.get("reasoning", ""),
            "urgency": p.get("urgency", ""),
            "treatment_instructions": p.get("instructions", []),
            "doctor_notes": p.get("notes", ""),
            "summary": p.get("text", ""),
            "images": p.get("images", []),
        }
        for p in payloads
    ]
