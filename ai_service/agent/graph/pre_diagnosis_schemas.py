from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agent.common.clinical_codes import BODY_SITE_CHOICES


def _as_list(value: Any) -> Any:
    """Model hay trả 1 chuỗi thay vì list — bọc lại thay vì từ chối cả lần lập luận."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_strs(value: Any) -> Any:
    """Model nhỏ hay chép dạng object của `hypotheses` sang `queries` (`{"disease": "..."}`): lấy giá trị chữ đầu tiên thay vì từ chối."""
    texts = [next((v for v in item.values() if isinstance(v, str)), "") if isinstance(item, dict) else item for item in _as_list(value)]
    return [t for t in texts if t != ""]


def _first4(value: list[Any]) -> list[Any]:
    """Model hay trả 5+ mục dù prompt nói tối đa 4 — cắt bớt thay vì từ chối cả lần gọi (mỗi lần retry rất tốn thời gian)."""
    return value[:4]


_INTERNAL = (
    "Bản ghi NỘI BỘ của hệ thống, người dùng không đọc. Chỉ điền các trường: giá trị ngắn gọn, ngôi thứ ba, "
    "KHÔNG chào hỏi, KHÔNG đồng cảm, KHÔNG xưng hô (bạn / mình / tôi), KHÔNG viết thành câu trả lời cho bệnh nhân."
)
_MAX_CHARS = 160


def _clip(value: Any) -> Any:
    """Cắt giá trị chữ quá dài thay vì từ chối: model nhỏ hay viết cả đoạn vào một trường."""
    if isinstance(value, str):
        return value[:_MAX_CHARS]
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


class PlanHypothesis(BaseModel):
    disease: str = Field(description="Tên bệnh ngắn (tối đa 8 từ), không phải câu văn")
    missing: list[str] = Field(default_factory=list, description="Điều còn thiếu để xác nhận hoặc loại trừ: cụm danh từ, mỗi mục tối đa 10 từ")

    _coerce = field_validator("missing", mode="before")(_as_list)
    _short = field_validator("disease", "missing", mode="after")(_clip)


class PlanInput(BaseModel):
    __doc__ = _INTERNAL

    hypotheses: list[PlanHypothesis] = Field(description="Tối đa 4 giả thuyết")
    queries: list[str] = Field(default_factory=list, description="Tối đa 4 truy vấn tra cứu: cụm từ khoá, mỗi mục tối đa 12 từ, mỗi truy vấn một chủ đề; không phải câu hỏi gửi người dùng. Để RỖNG khi kết quả tra cứu đã có đủ cho câu hỏi này hoặc không cần tra cứu")

    _coerce = field_validator("queries", mode="before")(_as_strs)
    _trim = field_validator("hypotheses", "queries", mode="after")(_first4)
    _short = field_validator("queries", mode="after")(_clip)


CODE_CHOICES = "Acne | Actinic_Keratosis | Benign_tumors | Bullous | Candidiasis | DrugEruption | Eczema | Infestations_Bites | Lichen | Lupus | Moles | Psoriasis | Rosacea | Seborrh_Keratoses | SkinCancer | Sun_Sunlight_Damage | Tinea | Unknown_Normal | Vascular_Tumors | Vasculitis | Vitiligo | Warts | OTHER"


class ReflectHypothesis(BaseModel):
    disease: str = Field(description="Tên bệnh ngắn (tối đa 8 từ), không phải câu văn")
    # chuỗi thay vì Literal: model nhỏ hay ghi lệch, chuẩn hoá ở `agent/common/clinical_codes.py` thay vì bắt gọi lại cả lần lập luận
    code: str = Field(default="", description=f"Mã nhóm bệnh gần nhất, chọn đúng một: {CODE_CHOICES}")
    body_site: str = Field(default="", description=f"Vùng da của vấn đề giả thuyết này giải thích, chọn đúng một mã (phần trong ngoặc chỉ để giải thích): {BODY_SITE_CHOICES}; để trống nếu chưa rõ")
    confidence: Literal["cao", "vừa", "thấp"]
    cites: list[str] = Field(default_factory=list, description="Chỉ các mã bằng chứng E# (ví dụ E1, E3) ủng hộ giả thuyết; không viết chữ khác")
    missing: list[str] = Field(default_factory=list, description="Điều còn thiếu: cụm danh từ, mỗi mục tối đa 10 từ")

    _coerce = field_validator("cites", "missing", mode="before")(_as_list)
    _short = field_validator("disease", "missing", mode="after")(_clip)


class ReflectInput(BaseModel):
    __doc__ = _INTERNAL

    hypotheses: list[ReflectHypothesis] = Field(description="Tối đa 4 giả thuyết")
    next: Literal["retrieve", "answer"]
    queries: list[str] = Field(default_factory=list, description="Truy vấn mới khi next=retrieve: cụm từ khoá, mỗi mục tối đa 12 từ")
    answered: str = Field(description="Một câu ngôi thứ ba (tối đa 25 từ) về điều kết quả vừa rồi cho thấy; không chào hỏi, không xưng hô")
    next_reason: str = Field(description="Một câu ngôi thứ ba (tối đa 25 từ) giải thích lựa chọn `next`")

    _coerce = field_validator("queries", mode="before")(_as_strs)
    _trim = field_validator("hypotheses", "queries", mode="after")(_first4)
    _short = field_validator("queries", "answered", "next_reason", mode="after")(_clip)
