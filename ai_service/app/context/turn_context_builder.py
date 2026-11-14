import logging
from typing import Any

from app.context.agent_context import AgentContext
from app.dto.turn_request import TurnRequest
from app.config.settings import settings
from app.deps import get_consultation_client, get_knowledge_client
from app.reasoning.patient_fact_extractor import build_fact_from_graph

logger = logging.getLogger(__name__)


async def _get_known_state(profile_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fact và tổn thương hiện hành của hồ sơ lấy từ graph theo dõi; lỗi thì chạy tiếp không có (log để biết lượt thiếu ngữ cảnh)."""
    if not profile_id:
        return [], []
    try:
        state = await get_knowledge_client().get_patient_facts(profile_id)
    except Exception:  # noqa: BLE001
        logger.warning("Không lấy được fact của hồ sơ %s từ knowledge", profile_id, exc_info=True)
        return [], []
    return [build_fact_from_graph(f, state["lesions"]) for f in state["facts"]], state["lesions"]



async def build_context(req: TurnRequest) -> AgentContext:
    conversation = await get_consultation_client().get_conversation(req.conversation_id) or {}
    profile_id = conversation.get("patient_profile_id") or ""
    known_facts, known_lesions = await _get_known_state(profile_id)
    return AgentContext(
        user_id=conversation.get("user_id") or "",
        patient_profile_id=profile_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[a.storage_key for a in (req.attached_files or []) if a.content_type.startswith("image/")],
        model=settings.AGENT_MODEL_CHOICES.get(conversation.get("model") or "", ""),
        known_facts=known_facts,
        known_lesions=known_lesions,
    )
