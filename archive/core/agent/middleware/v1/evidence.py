from typing import Awaitable, Callable

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.messages import SystemMessage

from agent.common.evidence import evidence_status
from agent.context.agent_context import AgentContext
from agent.tools.reasoning import turn_messages

_NO_EVIDENCE_RULES = (
    "\n\n[KIỂM SOÁT BẰNG CHỨNG — bắt buộc] Các lần tra cứu trong lượt này KHÔNG trả về bằng chứng (sách / ca bệnh). Từ giờ tới hết lượt: "
    "KHÔNG nêu tên bệnh nào như một khả năng, giả thuyết hay chẩn đoán, KHÔNG xếp hạng, KHÔNG nêu độ tin cậy, KHÔNG đưa lời khuyên "
    "điều trị hay chăm sóc cụ thể, KHÔNG ghi dữ kiện nguồn \"user\" nào ngoài đúng lời người dùng đã nói. Khi gọi `record_reasoning` "
    "(stage after_evidence / final) để `hypotheses` là danh sách rỗng. Chỉ được: (1) nói rõ mình chưa tra cứu được nguồn nào để đối "
    "chiếu nên chưa thể nhận định về bệnh; (2) nhắc lại những gì người dùng đã mô tả; (3) đặt câu hỏi thêm về thông tin còn thiếu ở cuối câu trả lời "
    "HOẶC khuyên khám da liễu kèm các dấu hiệu cần đi khám ngay; (4) nhắc đây là thông tin tham khảo."
)


@wrap_model_call
async def evidence_rules(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """(a) Đã tra cứu mà không có bằng chứng -> thêm quy tắc cứng vào system prompt cho các lần gọi model còn lại của lượt."""
    if evidence_status(turn_messages(request.state["messages"])) == "none":
        base = request.system_message.content if request.system_message else ""
        request = request.override(system_message=SystemMessage(content=f"{base}{_NO_EVIDENCE_RULES}"))
    return await handler(request)
