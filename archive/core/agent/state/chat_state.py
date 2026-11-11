"""State của chat graph"""
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    route: NotRequired[Literal["answer", "diagnose"]]
    # Snapshot state tiền chẩn đoán của graph v2 (facts, bằng chứng, lệnh đã gọi) để lượt sau dùng tiếp; nằm trong checkpoint theo conversation_id.
    diag: NotRequired[dict[str, Any]]
