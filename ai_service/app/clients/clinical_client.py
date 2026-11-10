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

