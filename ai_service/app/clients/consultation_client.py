from typing import Any

import httpx


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
