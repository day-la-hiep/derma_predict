from functools import lru_cache

# Phủ định và đơn vị/liều mang nghĩa lâm sàng ("không có dị ứng", "5 mg"): không bao giờ bỏ, kể cả khi danh sách có chứa
PROTECTED = frozenset({
    "không", "chưa", "chẳng", "chả", "no", "not", "nor", "without", "never",
    "mg", "mcg", "g", "kg", "ml", "l", "iu", "%",
})

_VI = frozenset(
    "và của là các những một được bị bởi cho với trong ngoài trên dưới tại từ đến khi nếu thì mà này đó kia ấy nên cũng đã đang sẽ "
    "vẫn còn rất hơn như về theo để do vì bằng hay hoặc nhưng song các mỗi mọi lại ra vào lên xuống".split()
)
_EN = frozenset(
    "a an the and or but if of at by for with about as into on in to from up down out over under is are was were be been being "
    "am do does did have has had this that these those it its which who whom whose what when where why how there here than then "
    "so such can could will would shall should may might also".split()
)


@lru_cache
def get_stopwords(language: str) -> frozenset[str]:
    """Stopword cho `vi` / `en` / `mixed` (hợp của hai), đã trừ `PROTECTED`."""
    words = _VI | _EN if language == "mixed" else {"vi": _VI, "en": _EN}[language]
    return words - PROTECTED
