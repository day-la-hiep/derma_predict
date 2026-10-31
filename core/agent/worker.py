
import asyncio
import json
import logging
from collections import defaultdict

from aio_pika.abc import AbstractIncomingMessage

from agent.dto.schemas import TurnRequest
from agent.handler.consultation_report import handle_consultation_report
from agent.graph.chat_graph import chat_graph
from agent.persistence import postgres_persistence
from agent.turn import handle_resume, handle_turn
from app.config.log import request_id_var, setup_logging
from app.config.settings import log_startup_infra, settings
from app.config.constants import AGENT_CANCEL_CHANNEL, AGENT_REQUEST_QUEUE
from app.api.deps import close_clients, get_rabbitmq_client, get_redis_client

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên
# CÙNG `thread_id` (đụng checkpoint). Core đã chặn tin mới khi turn đang chạy, lock này là
# lớp bảo vệ cuối nếu vẫn có 2 request cùng hội thoại lọt vào queue.
logger = logging.getLogger("worker")
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_running: dict[str, "asyncio.Task[None]"] = {}


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            req = TurnRequest.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("message không hợp lệ: %s", exc)
            return

        request_id_var.set(req.message_id[:8])  # mọi dòng log của turn (kể cả trace LLM/tool) mang cùng mã này
        async with _conversation_locks[req.conversation_id]:
            # chạy trong task riêng để Dừng chỉ huỷ task này, không huỷ cả consumer của aio_pika
            task = asyncio.create_task(_run(req))
            if req.type != "consultation_report":
                _running[req.conversation_id] = task
            try:
                await task
            except Exception as exc:  # noqa: BLE001
                logger.exception("turn %s lỗi", req.conversation_id)
            finally:
                _running.pop(req.conversation_id, None)


async def _run(req: TurnRequest) -> None:
    logger.info("turn bắt đầu: type=%s conversation=%s", req.type, req.conversation_id)
    if req.type == "consultation_report":
        await handle_consultation_report(req)
    elif req.type == "resume":
        await handle_resume(req)
    else:
        await handle_turn(req)
    logger.info("turn kết thúc")


async def _listen_cancel() -> None:
    async for msg in get_redis_client().subscribe(AGENT_CANCEL_CHANNEL):
        try:
            task = _running.get(json.loads(str(msg["data"]))["conversation_id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("yêu cầu dừng không hợp lệ: %s", exc)
            continue
        if task is not None:
            task.cancel()


async def main() -> None:
    setup_logging("worker")
    log_startup_infra()
    logger.info("model: %s", settings.AGENT_MODEL)
    await get_rabbitmq_client().connect()
    # Memory dài hạn và checkpoint hội thoại nằm ở Postgres (schema `langgraph`); graph biên dịch sẵn lúc import với bản RAM nên thay ở đây, trước khi nhận turn nào.
    async with postgres_persistence() as (store, checkpointer):
        chat_graph.store = store
        chat_graph.checkpointer = checkpointer
        logger.info("memory dài hạn và checkpoint hội thoại: Postgres, schema langgraph")
        logger.info("đang lắng nghe queue '%s'", AGENT_REQUEST_QUEUE)
        await get_rabbitmq_client().consume(AGENT_REQUEST_QUEUE, _on_message)
        cancel_task = asyncio.create_task(_listen_cancel())
        try:
            await asyncio.Event().wait()  # chạy tới khi bị dừng (Ctrl+C)
        finally:
            cancel_task.cancel()
            await close_clients()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("worker").info("đã dừng")
