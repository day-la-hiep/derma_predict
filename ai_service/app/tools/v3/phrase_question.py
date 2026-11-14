from typing import Any

from app.prompt.v3.pre_diagnosis_prompts import ASK_QUESTION

_BY_KIND = {
    "conflict": "Ảnh và lời kể của người bệnh chưa khớp về: {text}. Hỏi lại nhẹ nhàng để làm rõ (không nói hệ thống nghĩ ai sai).",
    "ambiguous": "Hỏi để xác nhận ý người bệnh: {text}.",
    "discriminate": "Hỏi người bệnh có dấu hiệu sau không (dịch sang lời thường tiếng Việt, không dùng thuật ngữ): {text}.",
    "missing": "Hỏi người bệnh có dấu hiệu sau không (dịch sang lời thường tiếng Việt, không dùng thuật ngữ): {text}.",
}
_DEFAULT = "Hỏi thêm về diễn biến: tổn thương xuất hiện từ khi nào, có lan rộng hay thay đổi không."


def build_ask_prompt(question: dict[str, Any] | None, image_issues: list[str]) -> str:
    parts = [_BY_KIND.get(question.get("kind", ""), _DEFAULT).format(text=question.get("text", "")) if question else _DEFAULT]
    if image_issues:
        # ảnh hỏng là thông tin người bệnh tự sửa được: nhắc gửi lại, vẫn chỉ một câu hỏi chính
        parts.append(f"Ảnh vừa gửi chưa dùng được ({'; '.join(image_issues)}): nhắc ngắn gửi lại ảnh rõ, đủ sáng, chụp gần vùng tổn thương.")
    return ASK_QUESTION.format(instruction="\n".join(parts))
