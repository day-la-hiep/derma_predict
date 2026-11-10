from typing import Any

from agent.common.clinical_codes import ALIASES as _ALIASES, canon as _canon


def format_cnn_top_labels(top: list[dict[str, Any]]) -> str:
    return "; ".join(f"{r['disease']} {r['confidence'] * 100:.0f}%" for r in top)


def format_similar_cases_hint(label: str, cases: list[dict[str, Any]]) -> str:
    rows = [f"{c.get('diagnosis')}: {str(c.get('doctor_reasoning') or '')[:120]}" for c in cases]
    return f"Ca bệnh có nhãn gần '{label}': " + " | ".join(rows)


def merge_cnn_candidates(cnn: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    """Nhãn CNN của mọi ảnh gộp theo bệnh (lấy độ tin cậy cao nhất), top `top_k`."""
    best: dict[str, float] = {}
    for r in cnn:
        for t in r["top"]:
            best[t["disease"]] = max(best.get(t["disease"], 0.0), float(t["confidence"]))
    return [{"disease": d, "confidence": c} for d, c in sorted(best.items(), key=lambda kv: -kv[1])[:top_k]]


def cross_check_image_against_hypotheses(candidates: list[dict[str, Any]], descriptions: list[str], hypotheses: list[str]) -> str | None:
    """So nhận định của làn ảnh (nhãn CNN + mô tả) với giả thuyết của làn chữ; None khi làn chữ chưa có giả thuyết nào."""
    if not hypotheses or not (candidates or descriptions):
        return None
    cand = {_canon(c["disease"]): c for c in candidates}
    text = {_canon(h): h for h in hypotheses}
    described = " ".join(descriptions).lower()
    agree = [f"{text[k]} ~ {cand[k]['disease']} {cand[k]['confidence'] * 100:.0f}%" for k in text if k in cand]
    image_only = [f"{c['disease']} {c['confidence'] * 100:.0f}%" for k, c in cand.items() if k not in text]
    text_only = []
    for k, h in text.items():
        if k in cand:
            continue
        mentioned = k in _ALIASES and any(a in described for a in _ALIASES[k])
        text_only.append(h + (" (mô tả ảnh có nhắc tới)" if mentioned else " (ảnh không ủng hộ)"))
    lines = [
        "Kiểm tra chéo ảnh và mô tả của người bệnh (chỉ là gợi ý, vẫn cần bằng chứng E#):",
        "- Trùng khớp: " + ("; ".join(agree) or "(không có)"),
        "- Chỉ ảnh gợi ý: " + ("; ".join(image_only) or "(không có)"),
        "- Chỉ mô tả của người bệnh gợi ý: " + ("; ".join(text_only) or "(không có)"),
    ]
    return "\n".join(lines)
