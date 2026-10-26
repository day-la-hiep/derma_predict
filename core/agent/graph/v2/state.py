from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class PreDiagState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Dữ kiện lâm sàng tích luỹ theo hội thoại: {template_label, fact_type, detail, source_messages}; `facts_upto` = số tin nhắn đã trích.
    facts: NotRequired[list[dict[str, Any]]]
    facts_upto: NotRequired[int]
    # Mỗi giả thuyết: {"disease", "confidence", "cites", "missing"}; chỉ giữ giả thuyết có trích dẫn hợp lệ sau `reflect`.
    plan: NotRequired[list[dict[str, Any]]]
    # Giả thuyết model nêu nhưng không có mã bằng chứng hợp lệ — vẫn cho model thấy để tra cứu tiếp.
    unsupported: NotRequired[list[str]]
    queries: NotRequired[list[str]]
    done_calls: NotRequired[list[str]]
    # Mỗi lệnh đã gọi kèm số mục trả về / số mục mới (không trùng), để `choose_tools` và `reflect` thấy vòng trước đã thu được gì.
    call_results: NotRequired[list[str]]
    # Số lần `choose_tools` đã chạy trong lượt; `reflect` ép sang `answer` khi chạm `MAX_TOOL_ROUNDS`.
    rounds: NotRequired[int]
    # Mỗi mục: {"id", "kind": "evidence" | "hint", "source", "text"}
    evidence: NotRequired[list[dict[str, Any]]]
    evidence_status: NotRequired[Literal["none", "found"]]
    next: NotRequired[Literal["retrieve", "answer"]]
