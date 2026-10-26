from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _as_list(value: Any) -> Any:
    """Model hay trả 1 chuỗi thay vì list — bọc lại thay vì từ chối cả lần lập luận."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


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

    facts: list[str] = Field(min_length=1, description="Dữ kiện đã biết, đúng điều người dùng đã nói hoặc thấy trong ảnh: cụm từ, mỗi mục tối đa 15 từ, không viết thành câu")
    hypotheses: list[PlanHypothesis] = Field(description="Tối đa 4 giả thuyết")
    queries: list[str] = Field(min_length=1, description="Tối đa 4 truy vấn tra cứu: cụm từ khoá, mỗi mục tối đa 12 từ, mỗi truy vấn một chủ đề; không phải câu hỏi gửi người dùng")

    _coerce = field_validator("facts", "queries", mode="before")(_as_list)
    _trim = field_validator("hypotheses", "queries", mode="after")(_first4)
    _short = field_validator("facts", "queries", mode="after")(_clip)


class ReflectHypothesis(BaseModel):
    disease: str = Field(description="Tên bệnh ngắn (tối đa 8 từ), không phải câu văn")
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

    _coerce = field_validator("queries", mode="before")(_as_list)
    _trim = field_validator("hypotheses", "queries", mode="after")(_first4)
    _short = field_validator("queries", "answered", "next_reason", mode="after")(_clip)


def render_plan(data: PlanInput) -> str:
    lines = ["**Lập luận ban đầu**", "", "Dữ kiện đã có:"]
    lines += [f"[{i}] {f}" for i, f in enumerate(data.facts, 1)]
    lines += ["", "Các giả thuyết (chỉ để cân nhắc, chưa có bằng chứng):"]
    for i, h in enumerate(data.hypotheses, 1):
        lines.append(f"{i}. {h.disease}")
        if h.missing:
            lines.append(f"   Còn thiếu: {'; '.join(h.missing)}")
    lines += ["", "Sẽ tra cứu: " + "; ".join(data.queries)]
    return "\n".join(lines)


def render_reflect(data: ReflectInput, plan: list[dict[str, Any]], notes: list[str], next_action: str) -> str:
    lines = ["**Cập nhật lập luận sau bằng chứng**", "", f"Kết quả vừa rồi: {data.answered}", "", "Các giả thuyết:"]
    if not plan:
        lines.append("Chưa có giả thuyết nào đủ căn cứ để nêu.")
    for i, h in enumerate(plan, 1):
        lines.append(f"{i}. {h['disease']} — độ tin cậy {h['confidence']}")
        lines.append(f"   Nguồn: {', '.join(h['cites']) or '—'}")
        if h["missing"]:
            lines.append(f"   Còn thiếu: {'; '.join(h['missing'])}")
    if notes:
        lines += ["", "Kiểm tra trích dẫn:", *[f"- {n}" for n in notes]]
    action = "tra cứu thêm" if next_action == "retrieve" else "trả lời"
    lines += ["", f"Bước tiếp theo: {action} — {data.next_reason}"]
    return "\n".join(lines)
