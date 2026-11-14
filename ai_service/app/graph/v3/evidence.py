from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


# shortcut: khối 3 chưa làm, node đi qua; giai đoạn 3 cài đặt.
async def build_evidence(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    return {}
