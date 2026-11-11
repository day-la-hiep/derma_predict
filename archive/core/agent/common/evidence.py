import json
from typing import Any, Literal

from langchain.messages import AnyMessage, HumanMessage, ToolMessage


# `knowledge_graph_query` tính là đã tra cứu nhưng không bao giờ cho bằng chứng (kết quả `source="kg"` chỉ là gợi ý).
RETRIEVAL_TOOLS = {"hybrid_retrieval", "semantic_search", "keyword_search", "knowledge_graph_query", "search_finalize_report"}
JSON_RESULT_TOOLS = {"hybrid_retrieval", "semantic_search", "keyword_search", "knowledge_graph_query"}

Status = Literal["untried", "none", "found"]


def message_text(message: AnyMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def has_evidence(tool: str, content: str) -> bool:
    if tool in JSON_RESULT_TOOLS:
        try:
            results = json.loads(content).get("results") or []
        except (ValueError, AttributeError):
            return False
        return any(isinstance(r, dict) and r.get("source") == "book" for r in results)
    if tool == "search_finalize_report":
        try:
            data = json.loads(content)
            return bool(data.get("evidence_found") and data.get("cases"))
        except (ValueError, AttributeError):
            return False
    return False


def evidence_status(turn: list[AnyMessage]) -> Status:
    """`untried`: chưa gọi tool tra cứu nào trong lượt; `none`: đã gọi nhưng không cái nào cho bằng chứng; `found`: có bằng chứng."""
    tried = False
    for m in turn:
        if isinstance(m, ToolMessage) and m.name in RETRIEVAL_TOOLS:
            tried = True
            if has_evidence(m.name or "", message_text(m)):
                return "found"
    return "none" if tried else "untried"
