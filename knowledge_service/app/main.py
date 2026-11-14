import asyncio
import sys
from contextlib import asynccontextmanager

import uvicorn
import uvicorn.loops.asyncio as _uvloop

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    _uvloop.asyncio_loop_factory = lambda use_subprocess=False: asyncio.SelectorEventLoop
from derma_shared.log import RequestLogMiddleware, setup_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.api.deps import close_clients, get_rabbitmq_client
from app.api.citation_api import router as citation_router
from app.api.document_api import router as document_router
from app.api.exception_handler import register_exception_handlers
from app.api.graph_schema_api import router as graph_schema_router
from app.api.internal_api import router as internal_router
from app.api.internal_case_api import router as internal_case_router
from app.config.settings import log_startup_infra, settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    log_startup_infra()
    await get_rabbitmq_client().connect()
    yield
    await close_clients()


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)

setup_logging("knowledge")
app.add_middleware(RequestLogMiddleware)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)
app.include_router(document_router, prefix=settings.API_V1_PREFIX)
app.include_router(citation_router, prefix=settings.API_V1_PREFIX)
app.include_router(graph_schema_router, prefix=settings.API_V1_PREFIX)
app.include_router(internal_router)
app.include_router(internal_case_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=False, loop="asyncio")
