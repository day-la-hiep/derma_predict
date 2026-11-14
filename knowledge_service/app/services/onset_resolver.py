import re
import unicodedata
from datetime import date, timedelta

# Số chữ → số; "năm" vừa là số 5 vừa là đơn vị "năm" nên quy tắc dưới tách theo vị trí
_NUMBER_WORDS = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
}
_UNIT_DAYS = {"ngày": 1, "tuần": 7, "tháng": 30, "năm": 365}
_NUMBER = "|".join(["\\d+", *_NUMBER_WORDS])
_RELATIVE = re.compile(rf"(?<![\w])({_NUMBER})\s*(ngày|tuần|tháng|năm)\b")
_MONTH = re.compile(r"tháng\s*(\d{1,2})\b")
_FIXED_OFFSETS = (
    ("hôm kia", 2), ("hôm qua", 1), ("hôm nay", 0), ("sáng nay", 0), ("vừa mới", 0), ("mới bị", 0),
    ("tuần trước", 7), ("tuần rồi", 7), ("tháng trước", 30), ("tháng rồi", 30), ("năm ngoái", 365),
    ("nửa tháng", 15),
)
# Không suy ra được ngày: trả rỗng thay vì đoán
_UNRESOLVABLE = ("từ nhỏ", "từ bé", "bẩm sinh", "từ lâu", "lâu rồi", "không rõ", "không nhớ")


def _parse_count(token: str) -> int | None:
    return int(token) if token.isdigit() else _NUMBER_WORDS.get(token)


def resolve_onset(text: str, reference: date) -> date | None:
    """Đổi cụm khởi phát người dùng nói thành ngày ước lượng, tính từ ngày của tin nguồn."""
    low = unicodedata.normalize("NFC", text).lower().strip()
    if not low or any(p in low for p in _UNRESOLVABLE):
        return None
    for phrase, days in _FIXED_OFFSETS:
        if phrase in low:
            return reference - timedelta(days=days)
    relative = _RELATIVE.search(low)
    if relative:
        count = _parse_count(relative.group(1))
        if count is not None:
            return reference - timedelta(days=count * _UNIT_DAYS[relative.group(2)])
    month = _MONTH.search(low)
    if month and 1 <= int(month.group(1)) <= 12:
        candidate = date(reference.year, int(month.group(1)), 1)
        return candidate if candidate <= reference else date(reference.year - 1, int(month.group(1)), 1)
    return None
