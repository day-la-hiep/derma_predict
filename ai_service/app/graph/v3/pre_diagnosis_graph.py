from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]

from app.context.agent_context import AgentContext
from app.graph.v3.ask import ask
from app.graph.v3.check import check, route_after_check
from app.graph.v3.conclude import conclude, reason
from app.graph.v3.evidence import build_evidence
from app.graph.v3.hypothesis import hypothesize
from app.graph.v3.intake import intake
from app.graph.v3.retrieval import retrieve
from app.state.v3.pre_diagnosis_state import PreDiagnosisState


def build_pre_diagnosis_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    graph = StateGraph(PreDiagnosisState, context_schema=AgentContext)
    graph.add_node("intake", intake)
    graph.add_node("hypothesize", hypothesize)
    graph.add_node("retrieve", retrieve)
    graph.add_node("build_evidence", build_evidence)
    graph.add_node("check", check)
    graph.add_node("ask", ask)
    graph.add_node("reason", reason)
    # Tên `answer` để chat graph stream token như v2 (`_STREAM_NODES`).
    graph.add_node("answer", conclude)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "hypothesize")
    graph.add_edge("hypothesize", "retrieve")
    graph.add_edge("retrieve", "build_evidence")
    graph.add_edge("build_evidence", "check")
    graph.add_conditional_edges("check", route_after_check, ["ask", "reason"])
    graph.add_edge("reason", "answer")
    graph.add_edge("ask", END)
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer, name="pre_diagnosis")
