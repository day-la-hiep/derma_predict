from typing import Any

from agent.context.agent_context import AgentContext
from agent.dto.schemas import TurnRequest
from app.api.deps import get_postgres_client
from app.config.settings import settings
from app.repositories.clinical_record_repository import ClinicalRecordRepository
from app.repositories.conversation_repository import ConversationRepository


async def _known_facts(profile_id: str) -> list[dict[str, Any]]:
    if not profile_id:
        return []
    async with get_postgres_client().session_factory() as db:
        rows = await ClinicalRecordRepository(db).current_facts(profile_id)
    return [
        {"template_label": f.label, "fact_type": f.fact_type, "detail": f.detail, "body_site": site or "", "source_messages": []}
        for f, site in rows
    ]


async def _conversation_for(conversation_id: str) -> tuple[str, str, str]:
    async with get_postgres_client().session_factory() as db:
        repo = ConversationRepository(db)
        conversation = await repo.get(conversation_id)
        if conversation is None:
            return "", "", ""
        user_id = await repo.owner_user_id(conversation) or ""
        profile_id = conversation.patient_profile_id
    model = settings.AGENT_MODEL_CHOICES.get(conversation.model, "")
    return user_id, model, profile_id


async def build_context(req: TurnRequest) -> AgentContext:
    user_id, model, profile_id = await _conversation_for(req.conversation_id)
    return AgentContext(
        user_id=user_id,
        patient_profile_id=profile_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[
            a.storage_key
            for a in (req.attached_files or [])
            if a.content_type.startswith("image/")
        ],
        model=model,
        known_facts=await _known_facts(profile_id),
    )
