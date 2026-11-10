"""Xử lý 1 turn của agent"""

import asyncio
import logging
from typing import Any, cast

from langchain_core.messages import AIMessage, HumanMessage
from derma_shared.constants import CONVERSATION_EVENTS_STREAM, STREAM_DONE_SENTINEL

from agent.dto.turn_request import TurnRequest
from agent.common.tracing import build_run_config
from agent.graph.chat_graph import chat_graph
from agent.middleware.tool_step_events import emit
from agent.context.agent_context import AgentContext
from agent.context.turn_context_builder import build_context
from agent.tools.patient_memory import after_turn
from app.deps import get_clinical_client, get_consultation_client, get_redis_client

logger = logging.getLogger(__name__)

# Node của chat graph có thể tạo câu trả lời cuối của turn: bước lọc intent trả lời luôn (`triage`) hoặc graph tiền chẩn đoán
# (`pre_diagnosis`; update của nó gồm mọi tin mới trong vòng lặp nên câu trả lời là AIMessage cuối cùng).
_ANSWER_NODES = ("triage", "pre_diagnosis")

# Giữ tham chiếu tới tác vụ nền: asyncio chỉ giữ tham chiếu yếu nên tác vụ không ai giữ có thể bị thu dọn giữa chừng.
_background: set["asyncio.Task[None]"] = set()

_ERROR_TEXT = (
    "Xin lỗi, hệ thống gặp sự cố khi xử lý câu hỏi này (có thể do quá tải "
    "tạm thời). Vui lòng thử lại sau ít phút."
)


def _human_message_content(req: TurnRequest) -> str:
    """Nối thêm object key MinIO của ảnh đính kèm"""
    content = req.content or ""
    images = [
        a
        for a in (req.attached_files or [])
        if a.content_type.startswith("image/")
    ]
    if not images:
        return content

    # nhãn `object_key` giữ nguyên: là tên tham số của tool `classify_skin_image` mà prompt hướng dẫn LLM chép lại
    lines = [
        f'- name="{a.file_name}" object_key="{a.storage_key}"' for a in images
    ]
    return content + "\n\n[Ảnh đính kèm]\n" + "\n".join(lines)


async def _stream_graph(
    input_: object,
    base: dict[str, Any],
    context: AgentContext,
    req: TurnRequest,
    streamed_text: list[str],
) -> AIMessage | None:
    """Chạy chat graph, forward token; trả AIMessage cuối của lượt."""
    final_message: AIMessage | None = None
    streamed = False

    async for mode, chunk in chat_graph.astream(  # pyright: ignore[reportUnknownMemberType]
        input_,
        config=build_run_config(req.conversation_id),
        context=context,
        stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            # token model chính do node `pre_diagnosis` của chat graph chuyển tiếp (`agent/graph/chat_graph.py::_pre_diagnosis_node`)
            payload = cast("dict[str, Any]", chunk)
            if payload.get("type") == "token" and payload.get("text"):
                streamed = True
                streamed_text.append(payload["text"])
                await emit(
                    req.conversation_id,
                    {"type": "message.delta", "delta": payload["text"], **base},
                )
            continue

        # mode == "updates": state diff sau mỗi node của chat graph — dùng để tóm `AIMessage` cuối cùng (LangGraph đã gộp sẵn, không cần tự cộng dồn từng chunk). Token không đi qua đây mà qua mode "custom" ở trên.
        update = cast(dict[str, Any], chunk)
        for node in _ANSWER_NODES:
            node_update = update.get(node)
            if node_update and node_update.get("messages"):
                last = node_update["messages"][-1]
                if isinstance(last, AIMessage):
                    final_message = last

    # Câu trả lời của triage không đi qua token streaming (nằm trong tham số tool của lần phân loại) — phát một lần để FE hiển thị
    # như các câu trả lời khác.
    if final_message is not None and not streamed and final_message.text:
        await emit(
            req.conversation_id,
            {"type": "message.delta", "delta": final_message.text, **base},
        )

    return final_message


async def _drive(req: TurnRequest, input_: object) -> None:
    context = await build_context(req)
    base: dict[str, Any] = {
        "conversation_id": req.conversation_id,
        "message_id": req.message_id,
    }

    await emit(
        req.conversation_id, {"type": "message.started", "corr_id": req.corr_id, **base}
    )

    streamed_text: list[str] = []
    try:
        final_message = await _stream_graph(
            input_, base, context, req, streamed_text
        )
    except asyncio.CancelledError:
        # người dùng bấm Dừng: giữ phần đã stream; nuốt CancelledError vì turn phải đóng bình thường (xoá active key, ack)
        logger.info("turn %s bị người dùng dừng", req.message_id)
        partial = "".join(streamed_text)
        await finish_turn(
            req,
            {"type": "message.done", "content": partial, **base},
            content=partial,
            reasoning=context.reasoning_steps,
            context=context,
        )
        return
    except Exception as exc:  # noqa: BLE001
        # Không để lỗi lọt ra ngoài (turn sẽ treo, message kẹt "queued"); coi như "done" với nội dung báo lỗi
        # vì thêm status "error" phải sửa cả DTO/FE/DB enum.
        logger.exception("lỗi khi chạy turn %s: %s", req.message_id, exc)
        await finish_turn(
            req,
            {"type": "message.done", "content": _ERROR_TEXT, **base},
            content=_ERROR_TEXT,
            reasoning=context.reasoning_steps,
            context=context,
        )
        return

    answer = final_message.text if final_message is not None else ""
    await finish_turn(
        req,
        {"type": "message.done", "content": answer, **base},
        content=answer,
        reasoning=context.reasoning_steps,
        context=context,
    )
    _schedule_memory_update(req, context)


def _schedule_memory_update(req: TurnRequest, context: AgentContext) -> None:
    """Cập nhật memory chạy nền, tách khỏi luồng trả lời: câu trả lời đã gửi xong, lượt không phải chờ bước này."""
    text = req.content
    store = chat_graph.store
    if not text or store is None or not context.patient_profile_id:
        return
    task = asyncio.create_task(after_turn(store, context.patient_profile_id, req.conversation_id, text, context.model or None))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def handle_turn(req: TurnRequest) -> None:
    """Turn mới."""
    # id DB của tin người dùng: nguồn của fact trích từ tin này trỏ đúng bảng `messages`
    await _drive(
        req, {"messages": [HumanMessage(content=_human_message_content(req), id=req.user_message_id)]}
    )


async def finish_turn(
    req: TurnRequest,
    event: dict[str, Any],
    *,
    content: str,
    reasoning: list[dict[str, Any]] | None = None,
    context: AgentContext | None = None,
) -> None:
    """Kết thúc/tạm dừng turn: báo FE qua Redis Stream, ghi kết quả lâm sàng vào clinical rồi trả câu trả lời cho consultation."""
    await emit(req.conversation_id, event)
    await get_redis_client().add_stream_event(
        CONVERSATION_EVENTS_STREAM.format(conversation_id=req.conversation_id), STREAM_DONE_SENTINEL
    )
    if context is not None and (context.turn_facts or context.turn_hypotheses or context.turn_images):
        await _save_clinical_result(req, context)
    result = {
        "conversation_id": req.conversation_id,
        "content": content,
        "status": "done",
        "choice": None,
        "reasoning": reasoning or None,
    }
    try:
        await get_consultation_client().post_turn_result(req.message_id, result)
    except Exception:  # noqa: BLE001
        # tin assistant ở consultation vẫn `queued` tới khi quá hạn; FE đã nhận câu trả lời qua stream
        logger.error("Không gửi được kết quả turn %s về consultation", req.message_id, exc_info=True)


async def _save_clinical_result(req: TurnRequest, context: AgentContext) -> None:
    """Lỗi ghi hồ sơ lâm sàng không được làm mất câu trả lời đã có."""
    try:
        await get_clinical_client().apply_turn(
            {
                "conversation_id": req.conversation_id,
                "message_id": req.message_id,
                "patient_profile_id": context.patient_profile_id,
                "facts": context.turn_facts,
                "hypotheses": context.turn_hypotheses,
                "image_predictions": context.turn_images,
            }
        )
    except Exception:  # noqa: BLE001
        logger.error("Không ghi được kết quả lâm sàng của turn %s vào clinical", req.message_id, exc_info=True)
