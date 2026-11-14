from app.state.v3.diagnosis import EvidenceRow, Hypothesis

# shortcut: ngưỡng chọn tay; tune khi có tập đánh giá.
DELTA = 0.15
MAX_ROUNDS = 3
SINGLE_MIN_MATCHED = 2


def should_stop(hypotheses: list[Hypothesis], evidence: list[EvidenceRow], rounds: int, has_question: bool) -> tuple[bool, str]:
    """Dừng hỏi khi đủ chắc, hết lượt hỏi hoặc không còn gì để hỏi; trả kèm lý do để ghi vào bước lập luận."""
    if rounds >= MAX_ROUNDS:
        return True, f"đã hỏi {rounds}/{MAX_ROUNDS} câu"
    if len(hypotheses) >= 2 and hypotheses[0].score - hypotheses[1].score >= DELTA:
        return True, f"{hypotheses[0].name} hơn giả thuyết thứ hai {hypotheses[0].score - hypotheses[1].score:.2f} điểm (≥ {DELTA})"
    if len(hypotheses) == 1:
        row = next((r for r in evidence if r.disease_id == hypotheses[0].disease_id), None)
        if row and len(row.matched) >= SINGLE_MIN_MATCHED:
            return True, f"chỉ còn {hypotheses[0].name}, khớp {len(row.matched)} dấu hiệu"
    if not has_question:
        return True, "không còn câu hỏi phân biệt nào"
    return False, "chưa đủ chắc, cần hỏi thêm"
