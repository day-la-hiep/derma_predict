import logging
from typing import Any, cast

from langchain_core.messages import AIMessageChunk, RemoveMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_config, get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.runtime import Runtime

from app.graph.registry import get_pre_diagnosis
from app.graph.intent_triage_node import triage
from app.state.chat_state import ChatState
from app.context.agent_context import AgentContext
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Chỉ node trả lời người dùng được stream token (`answer`; v3 thêm `ask`); câu trả lời của triage (không qua token) do `turn.py` phát một lần.
_STREAM_NODES = ("answer", "ask")


def _load_diag(diag: dict[str, Any], version: str) -> dict[str, Any]:
    # Checkpoint trước khi có `version` là của v2; schema mỗi version khác nhau nên không dùng chéo.
    saved = diag.get("version", "v2")
    if diag and saved != version:
        logger.warning("bỏ diag của version %s vì đang chạy %s", saved, version)
        return {}
    return {k: v for k, v in diag.items() if k != "version"}


def _pre_diagnosis_node(graph: CompiledStateGraph[Any, AgentContext, Any, Any], diag_keys: tuple[str, ...], version: str):
    async def run(
        state: ChatState, runtime: Runtime[AgentContext]
    ) -> dict[str, Any]:
        before = state["messages"]
        write = get_stream_writer()
        final: dict[str, Any] = {}
        final_depth = -1
        # Đọc stream của graph con thay vì `ainvoke`: gọi `ainvoke` bên trong node thì token LLM không đi tiếp ra stream của chat graph
        # (chỉ còn tin hoàn chỉnh, gắn tên node của cha). Token của model chính (node "model", không phải các lần gọi LLM phụ như
        # tóm tắt) được chuyển tiếp qua kênh `custom` cho `turn.py` phát `message.delta`.
        # `get_config()`: truyền tiếp config của lượt chạy (checkpoint namespace, thread_id).
        # `subgraphs=True`: graph đặt `answer` trong subgraph `text_flow`, không bật thì token của nó không ra stream; `values` lấy bản cuối của tầng nông nhất (graph con chạy dưới namespace của chat graph nên không phải ns rỗng).
        async for ns, mode, chunk in graph.astream(
            {"messages": before, **_load_diag(state.get("diag", {}), version)},
            config=get_config(),
            context=runtime.context,
            stream_mode=["messages", "values", "updates"],
            subgraphs=True,
        ):
            if mode == "messages":
                message, meta = cast("tuple[Any, dict[str, Any]]", chunk)
                if (
                    meta.get("langgraph_node") in _STREAM_NODES
                    and isinstance(message, AIMessageChunk)
                    and message.text
                ):
                    write({"type": "token", "text": message.text})
            elif mode == "updates":
                # Node của subgraph tầng sâu (vd `text_flow/plan`) chỉ về tới stream này, không tự lên stream của chat graph: chuyển tiếp qua `custom`
                # cho UI debug dựng cây node; `turn.py` bỏ qua loại này. `ns[0]` là chính node này; node ngay dưới graph con đã tự lên stream cha nên không gửi lại.
                if len(ns) > 1:
                    for node, update in cast("dict[str, Any]", chunk).items():
                        write({"type": "node", "ns": "/".join(p.split(":")[0] for p in ns[1:]), "node": node, "update": update})
            elif final_depth < 0 or len(ns) <= final_depth:
                final, final_depth = cast("dict[str, Any]", chunk), len(ns)
        known = {m.id for m in before}
        kept = {m.id for m in final["messages"]}
        return {
            "messages": [
                *(RemoveMessage(id=i) for i in known - kept if i),
                *(m for m in final["messages"] if m.id not in known),
            ],
            "diag": {"version": version, **{k: final[k] for k in diag_keys if k in final}},
        }

    return run


def _after_triage(state: ChatState) -> str:
    return END if state.get("route") == "answer" else "pre_diagnosis"


def build_chat_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    *,
    pre_diagnosis: CompiledStateGraph[Any, AgentContext, Any, Any]
    | None = None,
    version: str | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    version = version or settings.AGENT_PRE_DIAGNOSIS_VERSION
    build, diag_keys = get_pre_diagnosis(version)
    graph = StateGraph(ChatState, context_schema=AgentContext)
    graph.add_node(
        "pre_diagnosis",
        _pre_diagnosis_node(pre_diagnosis or build(), diag_keys, version),
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
    )


chat_graph = build_chat_graph()
