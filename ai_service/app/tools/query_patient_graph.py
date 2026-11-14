"""Tool mở rộng từ dữ kiện của chính người bệnh qua đồ thị tri thức (PrimeKG + cạnh trích từ sách)."""

import json
import logging
from typing import Any

from langchain.tools import ToolRuntime, tool

from app.context.agent_context import AgentContext
from app.deps import get_knowledge_client
from app.reasoning.patient_fact_store import save_turn_facts

logger = logging.getLogger("agent.tools.query_patient_graph")

_MAX_TOP_K = 8


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def query_patient_graph(runtime: ToolRuntime[AgentContext, Any], top_k: int = 5) -> str:
    """Mở rộng từ CHÍNH các dữ kiện đã ghi nhận của người bệnh (triệu chứng, hình thái tổn thương, thuốc đang dùng, tiền sử, tiếp xúc) qua đồ thị tri thức:
    bệnh ứng viên, triệu chứng nên hỏi tiếp để phân biệt, ghi chú về thuốc đang dùng và câu trích từ sách giáo khoa.

    Dùng khi đã có vài dữ kiện của người bệnh và cần định hướng bệnh nào đáng tra cứu tiếp, hoặc cần biết hỏi thêm triệu chứng nào.
    KHÔNG có tham số về dữ kiện: tool tự lấy từ hồ sơ của người bệnh trong hội thoại này. Triệu chứng người bệnh nói KHÔNG có được dùng để trừ điểm bệnh.

    Kết quả chỉ là GỢI Ý để định hướng tra cứu, KHÔNG phải chẩn đoán và không thay thế `hybrid_retrieval`. Phần `book_evidence` là câu trích từ sách.
    Dữ kiện chưa khớp được nút đồ thị nằm ở `unmatched` và không tham gia mở rộng; đồ thị thưa nên có thể không có ứng viên.

    Args:
        top_k: Số bệnh ứng viên tối đa (mặc định 5, tối đa 8).
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    if not ctx.patient_profile_id:
        return _dumps({"evidence_found": False, "note": "Hội thoại chưa gắn hồ sơ bệnh nhân nên chưa có dữ kiện để mở rộng."})
    # fact của chính lượt này chưa ghi vào graph (turn.py ghi cuối lượt): ghi sớm để mở rộng được từ chúng
    await save_turn_facts(ctx)
    try:
        data = await get_knowledge_client().get_patient_graph_context(ctx.patient_profile_id, max(1, min(top_k, _MAX_TOP_K)))
    except Exception as exc:  # noqa: BLE001
        logger.error("Lỗi mở rộng đồ thị từ dữ kiện bệnh nhân: %s", exc, exc_info=True)
        return _dumps({"evidence_found": False, "error": f"Lỗi truy vấn: {exc}"})
    found = bool(data["candidates"] or data["questions"] or data["drug_notes"] or data["book_evidence"])
    return _dumps({"evidence_found": found, **data})
