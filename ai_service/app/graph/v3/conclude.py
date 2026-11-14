from typing import Any

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from app.common.messages import get_dialogue_history
from app.context.agent_context import AgentContext
from app.prompt.v3.pre_diagnosis_prompts import CONCLUDE
from app.reasoning.structured_llm_calls import get_model_for_turn
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


async def reply(state: PreDiagnosisState, ctx: AgentContext, system: str) -> dict[str, Any]:
    ai = await get_model_for_turn(ctx).ainvoke([SystemMessage(content=system), *get_dialogue_history(state["messages"])])
    return {"messages": [ai]}


async def conclude(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    return await reply(state, runtime.context, CONCLUDE)
