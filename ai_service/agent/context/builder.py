import logging
from typing import Any

from agent.context.agent_context import AgentContext
from agent.dto.schemas import TurnRequest
from app.config.settings import settings
from app.deps import get_clinical_client, get_consultation_client

logger = logging.getLogger(__name__)


async def _get_known_facts(profile_id: str) -> list[dict[str, Any]]:
    """Fact hiện trạng của hồ sơ lấy từ clinical; lỗi thì chạy tiếp không có fact (log để biết lượt thiếu ngữ cảnh)."""
    if not profile_id:
        return []
    try:
        context = await get_clinical_client().get_patient_context(profile_id)
    except Exception:  # noqa: BLE001
        logger.warning("Không lấy được fact của hồ sơ %s từ clinical", profile_id, exc_info=True)
        return []
    return [
        {"template_label": f["label"], "fact_type": f["fact_type"], "detail": f["detail"], "body_site": f.get("body_site") or "", "source_messages": []}
        for f in context["facts"]
    ]


async def build_context(req: TurnRequest) -> AgentContext:
    conversation = await get_consultation_client().get_conversation(req.conversation_id) or {}
    profile_id = conversation.get("patient_profile_id") or ""
    return AgentContext(
        user_id=conversation.get("user_id") or "",
        patient_profile_id=profile_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[a.storage_key for a in (req.attached_files or []) if a.content_type.startswith("image/")],
        model=settings.AGENT_MODEL_CHOICES.get(conversation.get("model") or "", ""),
        known_facts=await _get_known_facts(profile_id),
    )
