import logging
from typing import Any

from derma_shared.errors import AppError
from langchain_core.messages import HumanMessage, SystemMessage

from app.common.llm import get_model
from app.reasoning.patient_fact_extractor import DETAIL_MAX_CHARS, MAX_FACTS, ExtractedFacts, facts_text

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2

DESCRIPTION_SYSTEM = """Bạn là bộ phận chuyển MÔ TẢ CỦA BÁC SĨ thành DỮ KIỆN LÂM SÀNG nội bộ của hệ thống da liễu. Người dùng không đọc đầu ra này: chỉ gọi hàm, KHÔNG chào hỏi, KHÔNG viết văn bản.

Đầu vào là đoạn bác sĩ tự mô tả sau khi khám trực tiếp. Nêu các dữ kiện bác sĩ ghi nhận mà CHƯA có trong "Dữ kiện đã biết".
* Chỉ ghi điều bác sĩ khám thấy hoặc hỏi được: tổn thương (vị trí, hình thái, kích thước, màu, phân bố) là lesion; triệu chứng cơ năng là symptom; tiền sử / bệnh nền / yếu tố tiếp xúc là history; thuốc đang dùng là medication; dị ứng là allergy.
* Tuyệt đối KHÔNG suy diễn chẩn đoán, KHÔNG thêm dữ kiện, mức độ hay con số mà bác sĩ không viết. Kết luận bệnh KHÔNG phải là dữ kiện.
* Nhãn ngắn (tối đa 8 từ). `detail` giữ đúng lời bác sĩ, không diễn giải thêm.
* Dữ kiện đã biết mà mô tả không đổi thì KHÔNG nhắc lại. Cùng ý với một dữ kiện đã biết nhưng mô tả có chi tiết khác thì dùng lại ĐÚNG NGUYÊN VĂN nhãn đã biết và `detail` là giá trị đầy đủ mới.
* `body_site` luôn để trống (vùng đã gắn theo lần khám). `source_messages` luôn để rỗng.
* Mô tả không có dữ kiện lâm sàng nào thì trả danh sách rỗng."""


class DescriptionExtractionError(AppError):
    """Model không trả kết quả hợp lệ: clinical phải báo lỗi chứ không được chốt thiếu dữ kiện."""

    status_code = 502


def _key(fact_type: str, label: str) -> tuple[str, str]:
    return fact_type, " ".join(label.lower().split())


async def extract_facts_from_description(description: str, known: list[dict[str, Any]], model: str | None = None) -> list[dict[str, str]]:
    """Trả [{fact_type, label, detail}] bác sĩ mô tả mà `known` (dict có `fact_type`, `template_label`, `detail`) chưa có; lỗi LLM thì ném `DescriptionExtractionError`."""
    text = description.strip()
    if not text:
        return []
    messages = [
        SystemMessage(content=DESCRIPTION_SYSTEM),
        HumanMessage(content=f"Dữ kiện đã biết:\n{facts_text(known)}\n\nMô tả của bác sĩ:\n{text}\n\nGọi hàm ExtractedFacts."),
    ]
    structured = get_model(model).with_structured_output(ExtractedFacts, method="function_calling")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = await structured.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001  # sai schema / lỗi mạng: thử lại rồi báo lỗi
            logger.warning("lần %d/%d: không trích được dữ kiện từ mô tả của bác sĩ: %s", attempt + 1, _MAX_ATTEMPTS, exc)
            continue
        if not isinstance(result, ExtractedFacts):
            logger.warning("lần %d/%d: model không trả ExtractedFacts (nhận %s)", attempt + 1, _MAX_ATTEMPTS, type(result).__name__)
            continue
        known_by_key = {_key(str(f.get("fact_type", "")), str(f.get("template_label", ""))): str(f.get("detail", "")).strip() for f in known}
        out: dict[tuple[str, str], dict[str, str]] = {}
        for f in result.facts:
            label, detail = f.template_label.strip(), f.detail.strip()[:DETAIL_MAX_CHARS]
            key = _key(f.fact_type, label)
            if not label or known_by_key.get(key) == detail:  # trùng hệt dữ kiện đã biết thì bỏ
                continue
            out[key] = {"fact_type": f.fact_type, "label": label, "detail": detail}
        return list(out.values())[:MAX_FACTS]
    logger.error("không chuyển được mô tả của bác sĩ thành dữ kiện sau %d lần thử", _MAX_ATTEMPTS)
    raise DescriptionExtractionError("Chưa chuyển được mô tả thành dữ kiện, vui lòng thử lại.")
