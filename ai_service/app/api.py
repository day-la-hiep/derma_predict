import asyncio
import logging
from collections import defaultdict
from typing import Annotated

from derma_shared.errors import ForbiddenError
from derma_shared.log import request_id_var
from fastapi import APIRouter, Depends, Header, status

from app.dto.turn_request import TurnRequest
from app.turn import handle_turn
from app.config.settings import settings

logger = logging.getLogger("turn_runner")

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên CÙNG `thread_id` (đụng checkpoint).
# Consultation đã chặn tin mới khi turn đang chạy, lock này là lớp bảo vệ cuối.
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
# message_id -> task đang chạy, để Dừng chỉ huỷ đúng task đó
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
        _running[req.message_id] = task
        try:
            await task
        except Exception:  # noqa: BLE001
            logger.exception("turn %s lỗi", req.conversation_id)
        finally:
            _running.pop(req.message_id, None)


async def _dispatch(req: TurnRequest) -> None:
    logger.info("turn bắt đầu: type=%s conversation=%s", req.type, req.conversation_id)
    await handle_turn(req)
    logger.info("turn kết thúc")


def cancel_turn(message_id: str) -> bool:
    task = _running.get(message_id)
    if task is None:
        return False
    task.cancel()
    return True


def require_internal_key(x_internal_key: Annotated[str | None, Header()] = None) -> None:
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise ForbiddenError("Thiếu hoặc sai X-Internal-Key.")


router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)])


@router.post("/turns", status_code=status.HTTP_202_ACCEPTED)
async def create_turn(body: TurnRequest) -> dict[str, bool]:
    start_turn(body)
    return {"accepted": True}


@router.post("/turns/{message_id}/cancel")
async def cancel_turn_by_message(message_id: str) -> dict[str, bool]:
    return {"cancelled": cancel_turn(message_id)}
