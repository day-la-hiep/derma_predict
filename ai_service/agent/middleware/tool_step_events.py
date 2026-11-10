import json
from typing import Any

from derma_shared.constants import CONVERSATION_EVENTS_STREAM

from agent.context.agent_context import AgentContext
from app.deps import get_redis_client

# Tên tool hiển thị cho người dùng khi FE render bước "đang tra cứu ..." (SSE
# `message.tool_result`/`message.thinking`, xem `emit_tool_result`/`emit_reasoning_step`
# bên dưới) — tên hàm tiếng Anh (`hybrid_retrieval`...) khó hiểu với
# người dùng cuối, map sang nhãn tiếng Việt dễ hiểu. Tool nào quên thêm vào đây thì
# fallback về tên gốc.
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "record_reasoning": "Lập luận",
    "extract_facts": "Trích dữ kiện lâm sàng",
    "hybrid_retrieval": "Tra cứu sách giáo khoa",
    "semantic_search": "Tra cứu sách giáo khoa (theo ngữ nghĩa)",
    "keyword_search": "Tra cứu sách giáo khoa (theo từ khoá)",
    "knowledge_graph_query": "Tra cứu đồ thị tri thức",
    "search_finalize_report": "Tra cứu ca bệnh tương tự (báo cáo kết luận)",
    "search_finalize_report_by_image": "Tra cứu ca bệnh tương tự theo ảnh",
    "query_document_graph": "Tra cuu do thi tri thuc tu sach",
    "classify_skin_image": "Phân tích ảnh tổn thương da",
    "analyze_skin_image_multimodal": "Mô tả tổn thương bằng AI đa phương thức",
    "cross_check": "Kiểm tra chéo ảnh và mô tả của người bệnh",
}


async def emit(conversation_id: str, payload: dict[str, Any]) -> None:
    """Ghi event vào Redis Stream của hội thoại; consultation đọc ra SSE cho FE."""
    await get_redis_client().add_stream_event(
        CONVERSATION_EVENTS_STREAM.format(conversation_id=conversation_id), json.dumps(payload, ensure_ascii=False, default=str)
    )

REASONING_TOOL = "record_reasoning"
STAGE_LABELS = {
    "initial": "Lập luận ban đầu",
    "after_evidence": "Cập nhật lập luận sau bằng chứng",
}


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
    """Ghi bước tool vào `ctx.reasoning_steps` và phát `message.tool_result`; """
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
