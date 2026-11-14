from app.state.v3.diagnosis import EvidenceRow, Hypothesis

# shortcut: ngưỡng chọn tay; tune khi có tập đánh giá.
DELTA = 0.15
MAX_ROUNDS = 3
SINGLE_MIN_MATCHED = 2
MIN_MATCHED_TO_STOP = 3


def should_stop(hypotheses: list[Hypothesis], evidence: list[EvidenceRow], rounds: int, has_question: bool) -> tuple[bool, str]:
    """Dừng hỏi khi đủ chắc, hết lượt hỏi hoặc không còn gì để hỏi; trả kèm lý do để ghi vào bước lập luận."""
    if rounds >= MAX_ROUNDS:
        return True, f"đã hỏi {rounds}/{MAX_ROUNDS} câu"
    top_row = next((r for r in evidence if hypotheses and r.disease_id == hypotheses[0].disease_id), None)
    top_matched = len(top_row.matched) if top_row else 0
    # chỉ dừng theo khoảng cách điểm khi bệnh đầu có đủ dấu hiệu khớp: đo thật, KG thưa đẩy bệnh hiếm lên đầu chỉ nhờ 2 triệu chứng chung
    if len(hypotheses) >= 2 and hypotheses[0].score - hypotheses[1].score >= DELTA and top_matched >= MIN_MATCHED_TO_STOP:
        return True, f"{hypotheses[0].name} hơn giả thuyết thứ hai {hypotheses[0].score - hypotheses[1].score:.2f} điểm (≥ {DELTA}), khớp {top_matched} dấu hiệu"
    if len(hypotheses) == 1 and top_matched >= SINGLE_MIN_MATCHED:
        return True, f"chỉ còn {hypotheses[0].name}, khớp {top_matched} dấu hiệu"
    if not has_question:
        return True, "không còn câu hỏi phân biệt nào"
    return False, "chưa đủ chắc, cần hỏi thêm"
