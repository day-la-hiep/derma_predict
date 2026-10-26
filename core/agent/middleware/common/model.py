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
from agent.tools.memory import search_memories

logger = logging.getLogger(__name__)


async def with_memory(
    base: str,
    messages: list[AnyMessage],
    store: BaseStore | None,
    ctx: AgentContext,
) -> str:
    """Nối memory dài hạn của người dùng vào prompt; không có memory (hoặc lỗi) thì trả nguyên `base`."""
    query = next(
        (
            str(m.content)
            for m in reversed(messages)
            if isinstance(m, HumanMessage)
        ),
        "",
    )
    memories: list[str] = []
    try:
        memories = await search_memories(store, ctx.user_id, query)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        # Bộ nhớ dài hạn không bắt buộc cho một lượt trả lời; nếu embedding/DB lỗi
        # thì bỏ qua thay vì làm hỏng cả lượt hội thoại.
        logger.warning("không đọc được memory dài hạn: %s", exc)
    if not memories:
        return base
    memory_text = "\n".join(f"- {m}" for m in memories)
    return f"{base}\n\nThông tin đã biết về người dùng:\n{memory_text}"


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
