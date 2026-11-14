import logging
from datetime import UTC, datetime

from app.context.agent_context import AgentContext
from app.deps import get_knowledge_client
from app.reasoning.patient_fact_extractor import build_graph_fact

logger = logging.getLogger(__name__)


async def save_turn_facts(ctx: AgentContext) -> None:
    """Ghi fact mới của lượt vào graph theo dõi, tối đa một lần mỗi lượt. Lỗi chỉ log (không làm mất câu trả lời); fact bị knowledge từ chối log kèm lý do."""
    if ctx.turn_facts_saved or not ctx.turn_facts or not ctx.patient_profile_id:
        return
    observed_at = datetime.now(UTC).isoformat()
    facts = [{**build_graph_fact(f), "observed_at": observed_at} for f in ctx.turn_facts]
    try:
        result = await get_knowledge_client().apply_patient_facts(ctx.patient_profile_id, facts)
    except Exception:  # noqa: BLE001
        logger.error("Không ghi được fact của turn %s vào graph theo dõi", ctx.message_id, exc_info=True)
        return
    ctx.turn_facts_saved = True
    for skipped in result.get("skipped", []):
        logger.warning("Knowledge bỏ fact #%s của turn %s: %s", skipped.get("index"), ctx.message_id, skipped.get("reason"))
