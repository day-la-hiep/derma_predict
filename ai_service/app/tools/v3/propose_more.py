import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.context.agent_context import AgentContext
from app.deps import get_knowledge_client
from app.prompt.v3.pre_diagnosis_prompts import PROPOSE_MORE
from app.reasoning.structured_llm_calls import invoke_structured_with_retry
from app.state.v3.facts import Fact

logger = logging.getLogger(__name__)

MAX_PROPOSED = 3


class ProposedDiseases(BaseModel):
    """Bản ghi nội bộ: bệnh nên cân nhắc thêm."""

    names: list[str] = Field(default_factory=lambda: list[str](), max_length=MAX_PROPOSED)


async def propose_more(ctx: AgentContext, facts: list[Fact], current: list[str]) -> list[dict[str, Any]]:
    lines = "\n".join(f"- {f.slot}: {f.text_en or f.text} ({f.assertion})" for f in facts if f.source != "history") or "(chưa có)"
    body = f"Dữ kiện:\n{lines}\n\nĐang cân nhắc: {', '.join(current) or '(chưa có)'}"
    result = await invoke_structured_with_retry(ctx, ProposedDiseases, [SystemMessage(content=PROPOSE_MORE), HumanMessage(content=body)])
    names = [n.strip() for n in result.names[:MAX_PROPOSED] if n.strip()]
    if not names:
        return []
    ids = await get_knowledge_client().get_disease_ids(names)
    out: list[dict[str, Any]] = []
    for name in names:
        if ids.get(name):
            out.append({"disease_id": f"disease:{ids[name][0]}", "name": name, "score": 0.0})
        else:
            logger.warning("propose_more: '%s' không khớp node bệnh nào, bỏ", name)
    return out
