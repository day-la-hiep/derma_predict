import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.common.llm import get_model
from agent.common.text_utils import tokenize

logger = logging.getLogger(__name__)

MAX_FACTS = 30
_MAX_ATTEMPTS = 2

FactType = Literal["symptom", "lesion", "history", "medication", "allergy", "image_finding", "other"]

FACT_SYSTEM = """Bạn là bộ phận trích DỮ KIỆN LÂM SÀNG nội bộ của hệ thống tư vấn da liễu. Người dùng không đọc đầu ra này: chỉ gọi hàm, KHÔNG chào hỏi, KHÔNG viết văn bản.

Từ đoạn hội thoại, nêu các dữ kiện MỚI hoặc ĐÃ THAY ĐỔI so với "Dữ kiện đã biết".
* Chỉ dựa vào lời người bệnh ([PATIENT]) hoặc ảnh người bệnh gửi. Dòng [AI] chỉ để hiểu ngữ cảnh (vd câu hỏi AI vừa hỏi), KHÔNG phải nguồn dữ kiện.
* Tuyệt đối không suy diễn, không thêm triệu chứng, tiền sử, mức độ mà người bệnh không nói.
* Dữ kiện đã biết mà không đổi thì KHÔNG nhắc lại. Dữ kiện bị người bệnh đính chính thì trả lại cùng nhãn với chi tiết mới.
* Không có dữ kiện lâm sàng nào mới (chào hỏi, hỏi chung) thì trả danh sách rỗng.
* `source_messages`: số thứ tự `[#i]` của các tin [PATIENT] làm căn cứ; không bịa số."""


class ExtractedFact(BaseModel):
    template_label: str = Field(description="Tên chuẩn ngắn của dữ kiện (tối đa 8 từ), vd 'Ngứa', 'Mụn nước', 'Dị ứng penicillin'")
    fact_type: FactType
    detail: str = Field(description="Chi tiết đúng như người bệnh mô tả: vị trí, thời gian, mức độ (tối đa 25 từ)")
    source_messages: list[int] = Field(default_factory=list)


class ExtractedFacts(BaseModel):
    """Bản ghi NỘI BỘ của hệ thống, người dùng không đọc: chỉ điền các trường, không chào hỏi."""

    facts: list[ExtractedFact] = Field(default_factory=list)


def validate_facts_evidence(raw_facts: list[dict[str, Any]], messages_content: list[str]) -> list[dict[str, Any]]:
    """Lọc chỉ số tin nhắn sai và cảnh báo khi fact không trùng từ khoá nào với tin nguồn đã trích dẫn."""
    valid_facts: list[dict[str, Any]] = []
    total_messages = len(messages_content)

    for rf in raw_facts:
        f_label = str(rf.get("template_label", "")).strip()
        f_detail = str(rf.get("detail", "")).strip()
        source_indices = rf.get("source_messages") or []

        valid_indices: list[int] = []
        for idx in source_indices:
            if isinstance(idx, int) and 1 <= idx <= total_messages:
                valid_indices.append(idx)

        if valid_indices:
            source_text = " ".join(messages_content[i - 1] for i in valid_indices)
            source_tokens = tokenize(source_text)
            fact_tokens = tokenize(f"{f_label} {f_detail}")
            if fact_tokens and source_tokens and len(fact_tokens & source_tokens) == 0:
                logger.warning(
                    "Fact '%s' không khớp từ khóa với tin nhắn nguồn [#%s]",
                    f_label,
                    valid_indices,
                )

        rf["source_messages"] = valid_indices
        valid_facts.append(rf)

    return valid_facts


def _key(fact: dict[str, Any]) -> tuple[str, str]:
    return str(fact.get("fact_type", "")), " ".join(str(fact.get("template_label", "")).lower().split())


def merge_facts(known: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gộp theo (loại, nhãn): fact mới ghi đè fact cũ cùng khoá; giữ tối đa `MAX_FACTS` mục mới nhất."""
    merged = {_key(f): f for f in known}
    for f in new:
        key = _key(f)
        merged.pop(key, None)
        merged[key] = f
    return list(merged.values())[-MAX_FACTS:]


def facts_text(facts: list[dict[str, Any]]) -> str:
    return "\n".join(f"- [{f['fact_type']}] {f['template_label']}: {f['detail']}" for f in facts) or "(chưa có)"


async def extract_facts(known: list[dict[str, Any]], transcript: list[tuple[str, str]], model: str | None = None) -> list[dict[str, Any]]:
    """`transcript` là các cặp (người nói: "PATIENT" | "AI", nội dung) mới kể từ lần trích trước; trả fact mới/đổi, đã kiểm tra nguồn, [] khi lỗi."""
    if not any(who == "PATIENT" for who, _ in transcript):
        return []
    lines = "\n".join(f"[#{i}][{who}]: {text}" for i, (who, text) in enumerate(transcript, 1))
    messages = [
        SystemMessage(content=FACT_SYSTEM),
        HumanMessage(content=f"Dữ kiện đã biết:\n{facts_text(known)}\n\nĐoạn hội thoại mới:\n{lines}\n\nGọi hàm ExtractedFacts."),
    ]
    structured = get_model(model).with_structured_output(ExtractedFacts, method="function_calling")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = await structured.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001  # model trả sai schema / lỗi mạng: không làm hỏng lượt chat
            logger.warning("lần %d/%d: không trích được dữ kiện: %s", attempt + 1, _MAX_ATTEMPTS, exc)
            continue
        if isinstance(result, ExtractedFacts):
            raw = [f.model_dump() for f in result.facts]
            return validate_facts_evidence(raw, [text for _, text in transcript])
        logger.warning("lần %d/%d: model không trả ExtractedFacts (nhận %s)", attempt + 1, _MAX_ATTEMPTS, type(result).__name__)
    logger.warning("bỏ qua bước trích dữ kiện lượt này, giữ nguyên %d dữ kiện đã biết", len(known))
    return []
