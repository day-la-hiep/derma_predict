import logging
from typing import Any

from langchain.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from agent.context.agent_context import AgentContext
from agent.graph.v2.image import image_cnn, image_done, image_vision
from agent.graph.v2.nodes import answer, choose_tools_node, extract_facts_node, label_evidence_node, load_memory_node, plan, reflect
from agent.graph.v2.state import ImageState, PreDiagState
from agent.tools.hybrid_retrieval import (
    hybrid_retrieval,
    keyword_search,
    knowledge_graph_query,
    semantic_search,
)
from agent.tools.search_finalize_report import search_finalize_report
from agent.tools.web_search import fetch_trusted_page, search_trusted_web

logger = logging.getLogger(__name__)


def build_tools() -> list[Any]:
    return [
        hybrid_retrieval,
        semantic_search,
        keyword_search,
        knowledge_graph_query,
        search_finalize_report,
        search_trusted_web,
        fetch_trusted_page,
    ]


def _on_tool_error(exc: Exception) -> str:
    logger.warning("tool lỗi: %s", exc)
    return f"Lỗi khi gọi công cụ: {exc}"


def _after_memory(state: PreDiagState, runtime: Runtime[AgentContext]) -> list[str]:
    return ["text_flow", "image_flow"] if runtime.context.image_keys else ["text_flow"]


def _after_plan(state: PreDiagState) -> str:
    return "choose_tools" if state.get("queries") else "answer"


def _after_choose(state: PreDiagState) -> str:
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "label_evidence"


def _after_reflect(state: PreDiagState) -> str:
    return "choose_tools" if state.get("next") == "retrieve" else "answer"


def _text_flow(tools: list[Any]) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """Làn suy luận từ mô tả của người dùng: trích dữ kiện, lập kế hoạch, tra cứu, phản biện, trả lời."""
    graph = StateGraph(PreDiagState, context_schema=AgentContext)
    graph.add_node("extract_facts", extract_facts_node)
    graph.add_node("plan", plan)
    graph.add_node("choose_tools", choose_tools_node(tools))
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=_on_tool_error))
    graph.add_node("label_evidence", label_evidence_node)
    graph.add_node("reflect", reflect)
    graph.add_node("answer", answer)
    graph.add_edge(START, "extract_facts")
    graph.add_edge("extract_facts", "plan")
    graph.add_conditional_edges("plan", _after_plan, ["choose_tools", "answer"])
    graph.add_conditional_edges("choose_tools", _after_choose, ["tools", "label_evidence"])
    graph.add_edge("tools", "label_evidence")
    graph.add_edge("label_evidence", "reflect")
    graph.add_conditional_edges("reflect", _after_reflect, ["choose_tools", "answer"])
    graph.add_edge("answer", END)
    return graph.compile(name="text_flow")


def _image_flow() -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """Làn suy luận từ ảnh: CNN và model mô tả ảnh song song, rồi gom kết quả cho `label_evidence`."""
    graph = StateGraph(ImageState, context_schema=AgentContext)
    graph.add_node("image_cnn", image_cnn)
    graph.add_node("image_vision", image_vision)
    graph.add_node("image_done", image_done)
    graph.add_edge(START, "image_cnn")
    graph.add_edge(START, "image_vision")
    graph.add_edge(["image_cnn", "image_vision"], "image_done")
    graph.add_edge("image_done", END)
    return graph.compile(name="image_flow")


def build_pre_diagnosis_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """`checkpointer` / `store` để None khi nối vào chat graph"""
    graph = StateGraph(PreDiagState, context_schema=AgentContext)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("text_flow", _text_flow(build_tools()))
    graph.add_node("image_flow", _image_flow())
    graph.add_edge(START, "load_memory")
    graph.add_conditional_edges("load_memory", _after_memory, ["text_flow", "image_flow"])
    graph.add_edge("text_flow", END)
    graph.add_edge("image_flow", END)
    return graph.compile(checkpointer=checkpointer, store=store, name="pre_diagnosis")
