import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
import uvicorn.loops.asyncio as _uvloop

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # psycopg/asyncpg cần SelectorEventLoop; uvicorn mặc định dùng ProactorEventLoop trên Windows.
    _uvloop.asyncio_loop_factory = lambda use_subprocess=False: asyncio.SelectorEventLoop
from derma_shared.errors import AppError
from derma_shared.log import RequestLogMiddleware, setup_logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.graph.chat_graph import chat_graph
from app.langgraph_postgres_persistence import postgres_persistence
from app.api import router as internal_router
from app.config.settings import log_startup_infra, settings
from app.deps import close_clients

logger = logging.getLogger("ai")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log_startup_infra()
    logger.info("model: %s", settings.AGENT_MODEL)
    # Memory dài hạn và checkpoint hội thoại nằm ở Postgres (schema `langgraph`); graph biên dịch sẵn lúc import với bản RAM nên thay ở đây, trước khi nhận turn nào.
    async with postgres_persistence() as (store, checkpointer):
        chat_graph.store = store
        chat_graph.checkpointer = checkpointer
        logger.info("memory dài hạn và checkpoint hội thoại: Postgres, schema langgraph")
        yield
    await close_clients()


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)
setup_logging("ai")
app.add_middleware(RequestLogMiddleware)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


app.include_router(internal_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=False, loop="asyncio")
