"""Message contract Core (FastAPI) ⇄ Agent Worker qua RabbitMQ (2 queue,
`app/config/constants.py`).

`TurnRequest`: Core -> Worker (`agent_request_queue`) — mở turn mới (`type="turn"`)
hoặc resume câu hỏi `ask_user` đang chờ (`type="resume"`, xem `agent/tools/ask_user.py`).

`AgentResponseMessage`: Worker -> Core (`agent_response_queue`) — Core là writer duy
nhất của bảng `messages`, tự upsert khi nhận được (`app/workers/agent_response_consumer.py`).
"""
from typing import Any, Literal

from pydantic import BaseModel


class TurnAttachment(BaseModel):
    """1 ảnh đính kèm turn — field khớp `app/dto/base/file.py::File`; `storage_key` là key MinIO
    (`app/services/file_store_service.py`), Worker tự fetch bytes qua `get_object_bytes()` khi
    tool `classify_skin_image` (`agent/tools/skin_image_classifier.py`) cần."""

    file_name: str
    content_type: str
    storage_key: str


class TurnRequest(BaseModel):
    type: Literal["turn", "resume", "consultation_report"]
    conversation_id: str
    message_id: str  # id assistant message của turn hoặc marker message
    # id tin người dùng trong DB (type="turn"): gán cho HumanMessage để nguồn của fact trỏ đúng bảng `messages`
    user_message_id: str | None = None
    corr_id: str | None = None
    content: str | None = None  # bắt buộc khi type="turn"
    answer: str | None = None  # bắt buộc khi type="resume" — câu trả lời cho `ask_user`
    attached_files: list[TurnAttachment] | None = None
    # Trường dành cho consultation_report:
    session_id: str | None = None
    patient_profile_id: str | None = None
    reason: str | None = None


class AgentResponseMessage(BaseModel):
    conversation_id: str
    message_id: str
    content: str = ""
    status: Literal["done", "question", "report_ready", "report_failed"]
    # `MessageChoice.model_dump(mode="json")` — chỉ set khi
    # status="question" (`app/dto/response/message.py`).
    choice: dict[str, Any] | None = None
    # `AgentContext.reasoning_steps` tích luỹ được tới thời điểm turn kết thúc/tạm dừng
    # (`agent/context/agent_context.py`, `agent/worker.py::_drive`) — mỗi dict khớp field của
    # `Step` (`app/dto/common/chat.py`). Core persist NGUYÊN list này vào
    # `Message.extra.reasoning` (`app/workers/agent_response_consumer.py`) để `GET
    # .../messages` trả lại được các bước suy luận sau khi reload, không chỉ thấy lúc
    # đang stream qua SSE (Redis Pub/Sub không replay).
    reasoning: list[dict[str, Any]] | None = None
    # Kết quả lâm sàng của lượt (status="done"), Core ghi vào đợt bệnh (`ClinicalRecordService.apply_turn`):
    # facts: {template_label, fact_type, detail, body_site, source_messages: [message_id]} — mới / đổi trong lượt + fact chưa rõ vùng
    facts: list[dict[str, Any]] | None = None
    # hypotheses: {disease, code, body_site, confidence, evidence: [{source, text}], missing}
    hypotheses: list[dict[str, Any]] | None = None
    # image_predictions: {storage_key, top_k: [{label, score}]}
    image_predictions: list[dict[str, Any]] | None = None
    # Trường dành cho consultation_report (status in ("report_ready", "report_failed")):
    session_id: str | None = None
    report_summary: str | None = None
    provenance_pairs: list[list[str]] | None = None

