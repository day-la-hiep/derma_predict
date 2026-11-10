"""Tiện ích xử lý text và trích xuất token cho agent."""
import re

_WORD = re.compile(r"\w+", re.UNICODE)
_STOP = {
    "có", "không", "và", "của", "là", "bị", "ở", "cũng", "đang", "với", "một", "các", "những", "này", "khi", "để", "đã", "rất", "thì",
    "mà", "cho", "từ", "tại", "ra", "vào", "nhưng", "hoặc", "nên", "như", "được", "tôi", "em", "anh", "chị", "bác", "sĩ", "ơi",
    # từ "kể lại" (model hay viết "người dùng trả lời ... khi được hỏi ...") — không mang thông tin y khoa nên không tính
    "người", "dùng", "trả", "lời", "hỏi", "nói", "biết", "về", "mô", "tả",
}


def tokenize(text: str) -> set[str]:
    """Tách từ và lọc stop words cơ bản cho tiếng Việt."""
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 2 and w not in _STOP}
