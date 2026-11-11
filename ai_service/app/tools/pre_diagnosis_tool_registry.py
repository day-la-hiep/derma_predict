import logging
from typing import Any

from app.tools.hybrid_retrieval import hybrid_retrieval, keyword_search, knowledge_graph_query, semantic_search
from app.tools.query_document_graph import query_document_graph
from app.tools.search_finalize_report import search_finalize_report
from app.config.settings import settings

logger = logging.getLogger(__name__)


def build_tools() -> list[Any]:
    tools: list[Any] = [hybrid_retrieval, semantic_search, keyword_search, knowledge_graph_query, query_document_graph]
    if settings.AGENT_FINALIZE_REPORT_SEARCH_ENABLED:
        tools.append(search_finalize_report)
    return tools


def on_tool_error(exc: Exception) -> str:
    logger.warning("tool lỗi: %s", exc)
    return f"Lỗi khi gọi công cụ: {exc}"
