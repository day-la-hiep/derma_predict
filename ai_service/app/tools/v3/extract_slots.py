from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.context.agent_context import AgentContext
from app.prompt.v3.pre_diagnosis_prompts import EXTRACT_SLOTS
from app.reasoning.structured_llm_calls import invoke_structured_with_retry

# Ngoài 7 slot của doc, thêm drug / disease vì khối 4 (red flag) cần thuốc mới và khối 1 cần bệnh tiền sử từ lời kể.
SlotName = Literal["symptom", "morphology", "color", "scale", "location", "distribution", "duration", "drug", "disease"]


class Slot(BaseModel):
    slot: SlotName
    text: str = Field(max_length=120)
    text_en: str = Field(default="", max_length=120)
    assertion: Literal["present", "absent", "family", "history"] = "present"
    source: Literal["text", "image"] = "text"
    ref: int = Field(default=1, description="Số [#i] của tin làm căn cứ")


class Slots(BaseModel):
    """Bản ghi nội bộ: dữ kiện lâm sàng mới trích từ lượt này."""

    items: list[Slot] = Field(default_factory=lambda: list[Slot]())


async def extract_slots(ctx: AgentContext, messages: list[str], known: list[str]) -> list[Slot]:
    if not messages:
        return []
    body = "\n".join(["Dữ kiện đã biết:\n" + ("\n".join(f"- {k}" for k in known) or "(chưa có)"), "", *(f"[#{i}] {m}" for i, m in enumerate(messages, 1))])
    result = await invoke_structured_with_retry(ctx, Slots, [SystemMessage(content=EXTRACT_SLOTS), HumanMessage(content=body)])
    # ref ngoài phạm vi = model bịa số; giữ dữ kiện nhưng không gắn nguồn sai
    return [
        s.model_copy(update={"source": "text", "ref": s.ref if 1 <= s.ref <= len(messages) else 0})
        for s in result.items if s.text.strip()
    ]
