from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# Giá trị là dict (model_dump của `facts.Fact`, `diagnosis.*`) để checkpoint Postgres serialize được; node chuyển sang model khi đọc.
class PreDiagnosisState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    facts: NotRequired[list[dict[str, Any]]]
    facts_upto: NotRequired[int]
    # Khối 0: nhãn CNN của ảnh [{label, prob, disease_id}], bệnh / thuốc từ tiền sử, mention link chưa chắc (khối 5 hỏi lại)
    cnn_scores: NotRequired[list[dict[str, Any]]]
    history_diseases: NotRequired[list[dict[str, Any]]]
    recent_drugs: NotRequired[list[dict[str, Any]]]
    ambiguous: NotRequired[list[dict[str, Any]]]
    # Ảnh của lượt này không dùng được (mờ, quá nhỏ): khối hỏi thêm nhắc gửi lại; không giữ sang lượt sau
    image_issues: NotRequired[list[str]]
    hypotheses: NotRequired[list[dict[str, Any]]]
    evidence: NotRequired[list[dict[str, Any]]]
    # node_id đã hỏi bệnh nhân, không hỏi lại
    asked: NotRequired[list[str]]
    rounds: NotRequired[int]
    red_flags: NotRequired[list[str]]
    decision: NotRequired[Literal["ask", "conclude"]]
    question: NotRequired[dict[str, Any]]
    ranking: NotRequired[list[dict[str, Any]]]
    urgency: NotRequired[Literal["routine", "soon", "urgent"]]
    claims: NotRequired[list[dict[str, Any]]]


# Phần state giữ lại giữa các lượt (`ChatState.diag`).
DIAG_KEYS = ("facts", "facts_upto", "cnn_scores", "history_diseases", "recent_drugs", "ambiguous", "hypotheses", "evidence", "asked", "rounds", "ranking", "urgency", "claims")
