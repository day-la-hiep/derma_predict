from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.graph.v3.conclude import reply
from app.prompt.v3.pre_diagnosis_prompts import ASK
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


async def ask(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    question = (state.get("question") or {}).get("text", "triệu chứng xuất hiện từ khi nào và có ngứa không")
    out = await reply(state, runtime.context, ASK.format(question=question))
    return {**out, "rounds": state.get("rounds", 0) + 1}
