from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


# shortcut: khối 4 chưa có red flag / điều kiện dừng nên luôn kết luận; giai đoạn 3 cài đặt.
async def check(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    return {"decision": "conclude", "urgency": "routine", "red_flags": []}


def route_after_check(state: PreDiagnosisState) -> str:
    return "ask" if state.get("decision") == "ask" else "answer"
