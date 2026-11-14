from typing import Any

from app.state.v3.diagnosis import Hypothesis

# shortcut: trọng số chọn tay, chưa tune trên tập validation; ghi vào báo cáo.
WEIGHTS = {"kg": 0.4, "cnn": 0.3, "rag": 0.2, "history": 0.1}
TOP_K = 6
# Điểm cho bệnh do LLM đề xuất mà không nguồn nào có điểm.
PROPOSED_BONUS = 0.05


def fuse_scores(signals: dict[str, list[dict[str, Any]]], proposed: list[dict[str, Any]] | None = None, top_k: int = TOP_K) -> list[Hypothesis]:
    """Mỗi nguồn chuẩn hoá về [0, 1] theo điểm cao nhất của nguồn đó rồi cộng có trọng số; nguồn rỗng = 0 cho mọi bệnh."""
    names: dict[str, str] = {}
    norm: dict[str, dict[str, float]] = {}
    for source, items in signals.items():
        best: dict[str, float] = {}
        for item in items:
            disease_id = item.get("disease_id")
            if not disease_id:
                continue
            names.setdefault(disease_id, str(item.get("name") or disease_id))
            best[disease_id] = max(best.get(disease_id, 0.0), float(item.get("score") or 0.0))
        top = max(best.values(), default=0.0)
        if top > 0:
            norm[source] = {d: v / top for d, v in best.items()}
    hypotheses = [
        Hypothesis(disease_id=d, name=names[d], score=round(sum(WEIGHTS.get(s, 0.0) * v.get(d, 0.0) for s, v in norm.items()), 4),
                   signals={s: round(v[d], 3) for s, v in norm.items() if d in v})
        for d in names
    ]
    ranked = sorted((h for h in hypotheses if h.score > 0), key=lambda h: h.score, reverse=True)
    top = ranked[:top_k]
    # Bệnh LLM đề xuất luôn được giữ (thêm sau top_k): KG có đuôi dài bệnh hiếm khớp vài triệu chứng chung, cắt top_k thì bệnh thường gặp bị loại.
    by_id = {h.disease_id: h for h in ranked}
    kept = {h.disease_id for h in top}
    for item in proposed or []:
        disease_id = item.get("disease_id")
        if not disease_id or disease_id in kept:
            continue
        kept.add(disease_id)
        base = by_id.get(disease_id) or Hypothesis(disease_id=disease_id, name=str(item.get("name") or disease_id), score=PROPOSED_BONUS)
        top.append(base.model_copy(update={"signals": {**base.signals, "proposed": 1.0}}))
    return top
