_RRF_K = 60  # hằng số chuẩn của RRF: giảm ảnh hưởng chênh lệch thứ hạng ở đầu danh sách


def rrf(*rankings: list[str]) -> dict[str, float]:
    """Điểm RRF theo id"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    return scores

def merge_by_id(
    semantic: list[dict[str, Any]], bm25: list[dict[str, Any]], graph: list[dict[str, Any]], limit: int, id_key: str = "chunk_id"
) -> list[dict[str, Any]]:
    """Payload của ba nhánh, khử trùng theo `id_key`, xếp theo điểm RRF giảm dần, lấy `limit` đầu."""
    legs = [semantic, bm25, graph]
    payloads: dict[str, dict[str, Any]] = {}
    for payload in (p for leg in legs for p in leg):
        payloads.setdefault(str(payload.get(id_key)), payload)
    scores = rrf(*([str(p.get(id_key)) for p in leg] for leg in legs))
    return [payloads[k] for k in sorted(scores, key=lambda k: scores[k], reverse=True)[:limit]]
