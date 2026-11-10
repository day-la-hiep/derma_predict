import asyncio
import logging
from collections import defaultdict

from derma_shared.log import request_id_var

from agent.dto.schemas import TurnRequest
from agent.handler.consultation_report import handle_consultation_report
from agent.turn import handle_resume, handle_turn

logger = logging.getLogger("turn_runner")

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên CÙNG `thread_id` (đụng checkpoint).
# Consultation đã chặn tin mới khi turn đang chạy, lock này là lớp bảo vệ cuối.
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
# message_id -> task đang chạy, để Dừng chỉ huỷ đúng task đó (resume dùng lại cùng message_id của turn)
_running: dict[str, "asyncio.Task[None]"] = {}
# asyncio chỉ giữ tham chiếu yếu tới task nên phải tự giữ
_background: set["asyncio.Task[None]"] = set()


def start_turn(req: TurnRequest) -> None:
    """Chạy turn nền: `POST /internal/turns` trả 202 ngay, kết quả đi qua Redis Stream và lời gọi sang consultation."""
    task = asyncio.create_task(run_turn(req))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def run_turn(req: TurnRequest) -> None:
    request_id_var.set(req.message_id[:8])  # mọi dòng log của turn (kể cả trace LLM/tool) mang cùng mã này
    async with _conversation_locks[req.conversation_id]:
        # task riêng để Dừng chỉ huỷ task này
        task = asyncio.create_task(_dispatch(req))
        if req.type != "consultation_report":
            _running[req.message_id] = task
        try:
            await task
        except Exception:  # noqa: BLE001
            logger.exception("turn %s lỗi", req.conversation_id)
        finally:
            _running.pop(req.message_id, None)


async def _dispatch(req: TurnRequest) -> None:
    logger.info("turn bắt đầu: type=%s conversation=%s", req.type, req.conversation_id)
    if req.type == "consultation_report":
        await handle_consultation_report(req)
    elif req.type == "resume":
        await handle_resume(req)
    else:
        await handle_turn(req)
    logger.info("turn kết thúc")


def cancel_turn(message_id: str) -> bool:
    task = _running.get(message_id)
    if task is None:
        return False
    task.cancel()
    return True
