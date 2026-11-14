from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Source = Literal["text", "image", "history", "agent_query"]
Assertion = Literal["present", "absent", "family", "history"]

# Ảnh do AI mô tả nên nhẹ hơn lời bệnh nhân; lịch sử giảm dần theo tuổi của fact.
_SOURCE_WEIGHT: dict[str, float] = {"text": 1.0, "image": 0.6, "history": 0.8, "agent_query": 0.0}
_HISTORY_HALF_LIFE_DAYS = 365.0


class Fact(BaseModel):
    slot: str
    text: str
    # Tên tiếng Anh y khoa do bước trích điền, dùng để tra đồ thị và khớp chữ khi chưa có node
    text_en: str = ""
    # id DermO/PrimeKG; None = chưa link được, giữ chữ gốc
    node_id: str | None = None
    node_name: str | None = None
    source: Source
    assertion: Assertion = "present"
    confidence: float = 1.0
    time: datetime
    provenance: list[str] = []
    # Ảnh và lời kể mâu thuẫn ở cùng slot: khối hỏi thêm cần hỏi lại.
    conflict: bool = False


def get_fact_key(fact: Fact) -> tuple[str, str]:
    return fact.slot, fact.node_id or fact.text.strip().lower()


def merge_facts(known: list[Fact], new: list[Fact]) -> list[Fact]:
    """Gộp tăng dần; fact cùng khoá chỉ bị thay khi bệnh nhân tự nói lại (đính chính)."""
    merged = {get_fact_key(f): f for f in known}
    for fact in new:
        key = get_fact_key(fact)
        if key not in merged or fact.source == "text":
            merged[key] = fact
    return list(merged.values())


def get_fact_weight(fact: Fact, now: datetime) -> float:
    weight = _SOURCE_WEIGHT[fact.source] * fact.confidence
    if fact.source == "history":
        age_days = max((now - fact.time).total_seconds() / 86400, 0.0)
        weight *= 0.5 ** (age_days / _HISTORY_HALF_LIFE_DAYS)
    return weight
