import logging
from typing import Awaitable, Callable

from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    wrap_model_call,
)
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import AnyMessage
from langgraph.store.base import BaseStore

from agent.common.llm import get_model
from agent.context.agent_context import AgentContext
from agent.prompt.orchestrator import DIAGNOSIS_PROMPT
from agent.tools.memory import has_memories, search_memories

logger = logging.getLogger(__name__)


async def load_memory(messages: list[AnyMessage], store: BaseStore | None, user_id: str) -> str:
    """Đọc memory dài hạn của người dùng theo tin nhắn cuối của họ; không có memory (hoặc lỗi) thì trả chuỗi rỗng."""
    query = next(
        (str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )
    try:
        # Store rỗng (luôn đúng với v2, vì chỉ v1 có `save_memory`) thì khỏi embed câu hỏi.
        if not await has_memories(store, user_id):  # type: ignore[arg-type]
            return ""
        memories = await search_memories(store, user_id, query)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        # Bộ nhớ dài hạn không bắt buộc cho một lượt trả lời; nếu embedding/DB lỗi
        # thì bỏ qua thay vì làm hỏng cả lượt hội thoại.
        logger.warning("không đọc được memory dài hạn: %s", exc)
        return ""
    return "\n".join(f"- {m}" for m in memories)


def inject_memory(base: str, memory_text: str) -> str:
    return f"{base}\n\nThông tin đã biết về người dùng:\n{memory_text}" if memory_text else base


async def with_memory(
    base: str,
    messages: list[AnyMessage],
    store: BaseStore | None,
    ctx: AgentContext,
) -> str:
    """Đọc memory rồi nối vào prompt trong cùng một lời gọi (v1: mỗi lần gọi model); v2 đọc một lần ở `load_memory` rồi dùng `inject_memory`."""
    return inject_memory(base, await load_memory(messages, store, ctx.user_id))


@wrap_model_call
async def select_model(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """Chọn model theo `AgentContext.model`"""
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    if ctx.model:
        request = request.override(model=get_model(ctx.model))
    return await handler(request)


@wrap_model_call
async def inject_long_term_memory(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    base = (
        request.system_message.content
        if request.system_message
        else DIAGNOSIS_PROMPT
    )
    text = await with_memory(
        str(base), request.state["messages"], request.runtime.store, ctx
    )
    if text != base:
        request = request.override(system_message=SystemMessage(content=text))
    return await handler(request)
