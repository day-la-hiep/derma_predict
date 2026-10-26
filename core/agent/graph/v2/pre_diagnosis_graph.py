import logging
from typing import Any

from langchain.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from agent.context.agent_context import AgentContext
from agent.graph.v2.nodes import answer, choose_tools_node, extract_facts_node, label_evidence_node, load_memory_node, plan, reflect
from agent.graph.v2.state import PreDiagState
from agent.tools.hybrid_retrieval import (
    hybrid_retrieval,
    keyword_search,
    knowledge_graph_query,
    semantic_search,
)
from agent.tools.search_finalize_report import search_finalize_report
from agent.tools.search_finalize_report_by_image import search_finalize_report_by_image
from agent.tools.skin_image_classifier import classify_skin_image
from agent.tools.skin_image_multimodal import analyze_skin_image_multimodal
from agent.tools.web_search import fetch_trusted_page, search_trusted_web
from app.config.settings import settings

logger = logging.getLogger(__name__)


def build_tools() -> list[Any]:
    return [
        hybrid_retrieval,
        semantic_search,
        keyword_search,
        knowledge_graph_query,
        search_finalize_report,
        search_finalize_report_by_image,
        classify_skin_image,
        search_trusted_web,
        fetch_trusted_page,
        *([analyze_skin_image_multimodal] if settings.AGENT_VISION_MODEL else []),
    ]


def _on_tool_error(exc: Exception) -> str:
    logger.warning("tool lỗi: %s", exc)
    return f"Lỗi khi gọi công cụ: {exc}"


def _after_plan(state: PreDiagState) -> str:
    return "choose_tools" if state.get("queries") else "answer"


def _after_choose(state: PreDiagState) -> str:
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "reflect"


def _after_reflect(state: PreDiagState) -> str:
    return "choose_tools" if state.get("next") == "retrieve" else "answer"


def build_pre_diagnosis_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """`checkpointer` / `store` để None khi nối vào chat graph"""
    tools = build_tools()
    graph = StateGraph(PreDiagState, context_schema=AgentContext)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("extract_facts", extract_facts_node)
    graph.add_node("plan", plan)
    graph.add_node("choose_tools", choose_tools_node(tools))
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=_on_tool_error))
    graph.add_node("label_evidence", label_evidence_node)
    graph.add_node("reflect", reflect)
    graph.add_node("answer", answer)
    graph.add_edge(START, "load_memory")
    graph.add_edge("load_memory", "extract_facts")
    graph.add_edge("extract_facts", "plan")
    graph.add_conditional_edges("plan", _after_plan, ["choose_tools", "answer"])
    graph.add_conditional_edges("choose_tools", _after_choose, ["tools", "reflect"])
    graph.add_edge("tools", "label_evidence")
    graph.add_edge("label_evidence", "reflect")
    graph.add_conditional_edges("reflect", _after_reflect, ["choose_tools", "answer"])
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer, store=store, name="pre_diagnosis")
