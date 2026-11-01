import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from agent.graph.common import TOOL_DISPLAY_NAMES, emit
from agent.context.agent_context import AgentContext
from agent.tools.reasoning import STAGE_LABELS, TOOL_NAME as REASONING_TOOL

logger = logging.getLogger(__name__)


def _display_name(tool_name: str, tool_args: Any) -> str:
    display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
    # Mỗi `stage` của record_reasoning cần tên riêng, nếu không dedupe theo tên sẽ ghi đè lập luận đầu.
    if tool_name == REASONING_TOOL and isinstance(tool_args, dict):
        display_name = STAGE_LABELS.get(str(tool_args.get("stage")), display_name)
    return display_name


def _new_step(ctx: AgentContext, display_name: str) -> tuple[str, str]:
    n = ctx.tool_counts.get(display_name, 0) + 1
    ctx.tool_counts[display_name] = n
    # lần 1 giữ id/nhãn cũ để dữ liệu đã lưu và FE hiện tại vẫn khớp
    if n == 1:
        return f"{ctx.message_id}-tool-{display_name}", display_name
    return f"{ctx.message_id}-tool-{display_name}-{n}", f"{display_name} (lần {n})"


async def emit_tool_start(ctx: AgentContext, tool_name: str, tool_args: Any) -> None:
    """Báo FE tool bắt đầu chạy; FE hiện vòng quay đến khi `message.tool_result` cùng `step_id` về"""
    if not ctx.conversation_id:
        return
    display_name = _display_name(tool_name, tool_args)
    step = _new_step(ctx, display_name)
    ctx.open_steps.setdefault(display_name, []).append(step)
    await emit(
        ctx.conversation_id,
        {
            "type": "message.tool_start",
            "step_id": step[0],
            "tool": step[1],
            "input": tool_args,
            "conversation_id": ctx.conversation_id,
            "message_id": ctx.message_id,
        },
    )


async def emit_tool_step(
    ctx: AgentContext, tool_name: str, tool_args: Any, content: Any
) -> None:
    """Ghi bước tool vào `ctx.reasoning_steps` và phát `message.tool_result`; dùng chung cho graph v1 và v2"""
    display_name = _display_name(tool_name, tool_args)
    # có start trước đó thì dùng lại id của nó; không (extract_facts, bước ảnh) thì tạo mới
    queue = ctx.open_steps.get(display_name)
    step_id, label = queue.pop(0) if queue else _new_step(ctx, display_name)
    step = {
        "id": step_id,
        "title": f"Gọi tool: {label}",
        "input": tool_args,
        "content": str(content),
        "status": "done",
        "type": "tool",
    }
    existing_index = next(
        (i for i, s in enumerate(ctx.reasoning_steps) if s["id"] == step_id),
        None,
    )
    if existing_index is not None:
        ctx.reasoning_steps[existing_index] = step
    else:
        ctx.reasoning_steps.append(step)

    # Không có conversation_id (chạy trực tiếp để debug) thì chỉ ghi bước, không publish.
    if not ctx.conversation_id:
        return
    await emit(
        ctx.conversation_id,
        {
            "type": "message.tool_result",
            "step_id": step_id,
            "tool": label,
            "input": tool_args,
            "content": content,
            "conversation_id": ctx.conversation_id,
            "message_id": ctx.message_id,
        },
    )


@wrap_tool_call
async def emit_tool_result(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    """Publish `message.tool_start` TRƯỚC và `message.tool_result` SAU khi tool thực thi"""
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    call = request.tool_call
    # ask_user tạm dừng turn bằng interrupt, không có tool_result để tắt vòng quay; FE hiển thị qua message.question.
    if call.get("name") != "ask_user":
        await emit_tool_start(ctx, call.get("name", ""), call.get("args"))
    try:
        response = await handler(request)
    except GraphBubbleUp:
        raise
    except Exception as exc:  # noqa: BLE001
        # Trả ToolMessage lỗi thay vì ném: AIMessage(tool_calls) đã nằm trong checkpoint,
        # thiếu ToolMessage đi sau thì turn kế tiếp bị provider từ chối (400) và hội thoại kẹt.
        tool_name = (
            request.tool.name
            if request.tool
            else request.tool_call.get("name", "")
        )
        logger.warning("tool '%s' lỗi: %s", tool_name, exc)
        response = ToolMessage(
            content=f"Lỗi khi gọi công cụ '{tool_name}': {exc}",
            name=tool_name,
            tool_call_id=request.tool_call.get("id", ""),
        )

    if isinstance(response, ToolMessage):
        tool_args = (
            request.tool_call.get("args")
            if isinstance(request.tool_call, dict)
            else None
        )
        await emit_tool_step(
            ctx,
            response.name or request.tool_call.get("name", ""),
            tool_args,
            response.content,
        )
    return response
