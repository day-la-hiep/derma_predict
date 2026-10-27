import logging
from typing import Any, cast

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessageChunk, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_config, get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from agent.graph.v1.pre_diagnosis_graph import (
    ALL_TOOLS,
    build_pre_diagnosis_graph,
    default_middleware,
)
from agent.graph.triage import triage
from agent.state.chat_state import ChatState
from agent.context.agent_context import AgentContext
from agent.tools.memory import build_memory_store
from agent.common.tracing import trace_callback
from app.config.settings import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ALL_TOOLS",
    "chat_graph",
    "build_agent_graph",
    "build_chat_graph",
    "config_for",
    "default_middleware",
]


# Chỉ node `answer` của graph v2 được stream token. Graph v1 không stream: các lượt `model` trung gian có thể kèm chữ cùng tool_calls,
# nên chỉ câu trả lời cuối được gửi một lần ở cuối lượt (`turn.py` phát `message.delta` từ AIMessage cuối khi chưa có token nào).
_STREAM_NODES = ("answer",)

# Phần state của graph v2 giữ lại giữa các lượt; graph v1 không có các khoá này nên `diag` rỗng.
_DIAG_KEYS = ("facts", "facts_upto", "plan", "unsupported", "evidence", "evidence_status", "done_calls", "call_results")


def _default_pre_diagnosis() -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    if settings.AGENT_GRAPH_VERSION == "v2":
        from agent.graph.v2.pre_diagnosis_graph import (
            build_pre_diagnosis_graph as build_v2,
        )

        return build_v2()
    return build_pre_diagnosis_graph()


def _pre_diagnosis_node(graph: CompiledStateGraph[Any, AgentContext, Any, Any]):
    async def run(
        state: ChatState, runtime: Runtime[AgentContext]
    ) -> dict[str, Any]:
        before = state["messages"]
        write = get_stream_writer()
        final: dict[str, Any] = {}
        # Đọc stream của graph con thay vì `ainvoke`: gọi `ainvoke` bên trong node thì token LLM không đi tiếp ra stream của chat graph
        # (chỉ còn tin hoàn chỉnh, gắn tên node của cha). Token của model chính (node "model", không phải các lần gọi LLM phụ như
        # tóm tắt) được chuyển tiếp qua kênh `custom` cho `turn.py` phát `message.delta`.
        # `get_config()`: truyền tiếp config của lượt chạy (checkpoint namespace, thread_id) để `interrupt()` của `ask_user` hoạt động.
        async for mode, chunk in graph.astream(
            {"messages": before, **state.get("diag", {})},
            config=get_config(),
            context=runtime.context,
            stream_mode=["messages", "values"],
        ):
            if mode == "messages":
                message, meta = cast("tuple[Any, dict[str, Any]]", chunk)
                if (
                    meta.get("langgraph_node") in _STREAM_NODES
                    and isinstance(message, AIMessageChunk)
                    and message.text
                ):
                    write({"type": "token", "text": message.text})
            else:
                final = cast("dict[str, Any]", chunk)
        known = {m.id for m in before}
        kept = {m.id for m in final["messages"]}
        return {
            "messages": [
                *(RemoveMessage(id=i) for i in known - kept if i),
                *(m for m in final["messages"] if m.id not in known),
            ],
            "diag": {k: final[k] for k in _DIAG_KEYS if k in final},
        }

    return run


def _after_triage(state: ChatState) -> str:
    return END if state.get("route") == "answer" else "pre_diagnosis"


def build_chat_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    *,
    pre_diagnosis: CompiledStateGraph[Any, AgentContext, Any, Any]
    | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    graph = StateGraph(ChatState, context_schema=AgentContext)
    graph.add_node(
        "pre_diagnosis",
        _pre_diagnosis_node(pre_diagnosis or _default_pre_diagnosis()),
    )
    if settings.AGENT_TRIAGE_ENABLED:
        graph.add_node("triage", triage)
        graph.add_edge(START, "triage")
        graph.add_conditional_edges(
            "triage", _after_triage, ["pre_diagnosis", END]
        )
    else:
        graph.add_edge(START, "pre_diagnosis")
    graph.add_edge("pre_diagnosis", END)
    return graph.compile(
        # Bản RAM dùng cho test/debug và lúc import; worker thay bằng Postgres khi khởi động (`agent/persistence.py`).
        checkpointer=checkpointer or InMemorySaver(),
        store=store or build_memory_store(),
    )


def build_agent_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    *,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware[AgentState[Any], AgentContext, Any]]
    | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """Chat graph đầy đủ; `tools`/`system_prompt`/`middleware` chỉ áp dụng cho graph v1"""
    if settings.AGENT_GRAPH_VERSION == "v2":
        if tools or system_prompt or middleware:
            logger.warning("graph v2 bỏ qua tools/system_prompt/middleware truyền vào")
        return build_chat_graph(checkpointer, store)
    return build_chat_graph(
        checkpointer,
        store,
        pre_diagnosis=build_pre_diagnosis_graph(
            tools=tools, system_prompt=system_prompt, middleware=middleware
        ),
    )


chat_graph = build_chat_graph()


def config_for(conversation_id: str) -> RunnableConfig:
    """`thread_id` = `conversation_id`"""
    return {
        "configurable": {"thread_id": conversation_id},
        "callbacks": [trace_callback],
    }
