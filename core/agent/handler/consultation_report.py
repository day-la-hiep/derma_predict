"""Handler xử lý sinh Báo cáo tiền tư vấn & trích xuất Dữ kiện lâm sàng trong Agent Worker."""
import json
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.common.llm import get_model
from agent.common.text_utils import tokenize
from agent.dto.schemas import AgentResponseMessage, TurnRequest
from app.api.deps import get_postgres_client, get_rabbitmq_client
from app.config.constants import AGENT_RESPONSE_QUEUE
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """Bạn là trợ lý y khoa chuyên sâu da liễu.
Nhiệm vụ của bạn là phân tích các nguồn dữ liệu lâm sàng của bệnh nhân (dữ kiện lâm sàng đã biết, tóm tắt các lần khám trước, và đoạn hội thoại đợt khám hiện tại giữa bệnh nhân và trợ lý AI), sau đó:
1. Rút trích các DỮ KIỆN LÂM SÀNG (clinical facts) mới hoặc cập nhật từ đoạn hội thoại hiện tại.
2. Soạn một BÁO CÁO TIỀN TƯ VẤN (Pre-consultation Report) súc tích, chuyên nghiệp cho Bác sĩ da liễu đọc trước khi nhận ca, kết hợp tiền sử bệnh nhân và diễn biến đợt khám này.

Mỗi tin trong đoạn hội thoại hiện tại có số thứ tự dạng `[#3][PATIENT]: ...`.

BẮT BUỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON SAU (không kèm markdown code block hoặc text thừa):
{
  "facts": [
    {
      "template_label": "Tên chuẩn của triệu chứng/tổn thương/thuốc",
      "fact_type": "symptom | lesion | history | medication | allergy | image_finding | other",
      "detail": "Mô tả chi tiết cụ thể của bệnh nhân",
      "source_messages": [3]
    }
  ],
  "summary": "Nội dung tóm tắt lâm sàng (định dạng Markdown)"
}

Yêu cầu cho phần `summary` (dùng Markdown chuyên nghiệp):
- ## Tiền sử & Cơ địa đã biết: Tóm tắt ngắn gọn dị ứng, bệnh nền, thuốc đã/đang dùng từ dữ kiện trước đây (nếu có).
- ## Diễn biến các lần khám trước: Tóm tắt chẩn đoán hoặc diễn biến từ lần khám trước (nếu có).
- ## Lý do khám & Bệnh sử đợt này: Tóm tắt triệu chứng chính, thời gian khởi phát ghi nhận từ hội thoại đợt này.
- ## Vị trí & Đặc điểm tổn thương: Mô tả hình thái, vị trí vùng da bị bệnh đợt này.
- ## Đánh giá sơ bộ của AI: 1–3 bệnh nghi ngờ xếp theo độ phù hợp, độ tin cậy (Cao/Vừa/Thấp), có đối chiếu với tiền sử/diễn biến cũ nếu liên quan.
- ## Dấu hiệu cờ đỏ (Red Flags): Đã kiểm tra loại trừ hay nghi ngờ có cờ đỏ gì.
- ## Đề xuất cho Bác sĩ tiếp quản: Gợi ý câu hỏi lâm sàng cần làm rõ hoặc cận lâm sàng nên chỉ định.
- Lưu ý: Ghi rõ 'Kết luận AI chỉ mang tính chất tham khảo hỗ trợ tiền lâm sàng' ở cuối.

Yêu cầu cho `source_messages`: số thứ tự các tin trong đoạn hội thoại hiện tại chứa bằng chứng cho fact đó (ưu tiên tin của bệnh nhân); không bịa số không có trong hội thoại.
"""


def _validate_facts_evidence(
    raw_facts: list[dict[str, Any]],
    messages_content: list[str],
) -> list[dict[str, Any]]:
    """Middleware logic: Kiểm tra đối chiếu dữ kiện lâm sàng với tin nhắn nguồn.
    Loại bỏ hoặc làm sạch các fact có chỉ số tin nhắn không hợp lệ hoặc không có căn cứ từ lời bệnh nhân.
    """
    valid_facts: list[dict[str, Any]] = []
    total_messages = len(messages_content)

    for rf in raw_facts:
        f_label = str(rf.get("template_label", "")).strip()
        f_detail = str(rf.get("detail", "")).strip()
        source_indices = rf.get("source_messages") or []

        # Lọc chỉ số hợp lệ
        valid_indices: list[int] = []
        for idx in source_indices:
            if isinstance(idx, int) and 1 <= idx <= total_messages:
                valid_indices.append(idx)

        # Kiểm tra token overlap với tin nhắn nguồn tương ứng
        if valid_indices:
            source_text = " ".join(messages_content[i - 1] for i in valid_indices)
            source_tokens = tokenize(source_text)
            fact_tokens = tokenize(f"{f_label} {f_detail}")
            # Nếu fact có từ khóa nhưng không hề trùng khớp gì với tin nhắn nguồn được trích dẫn -> log warning
            if fact_tokens and source_tokens and len(fact_tokens & source_tokens) == 0:
                logger.warning(
                    "Fact '%s' không khớp từ khóa với tin nhắn nguồn [#%s]",
                    f_label,
                    valid_indices,
                )

        rf["source_messages"] = valid_indices
        valid_facts.append(rf)

    return valid_facts


async def handle_consultation_report(req: TurnRequest) -> None:
    """Xử lý task sinh báo cáo tiền tư vấn do Core yêu cầu qua RabbitMQ."""
    session_id = req.session_id or ""
    conversation_id = req.conversation_id
    patient_profile_id = req.patient_profile_id or ""
    reason = req.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn"

    logger.info(
        "Bắt đầu sinh báo cáo tiền tư vấn cho session=%s conversation=%s",
        session_id,
        conversation_id,
    )

    try:
        async with get_postgres_client().session_factory() as db:
            consultation_repo = ConsultationRepository(db)
            message_repo = MessageRepository(db)

            # 1. Tiền sử / dữ kiện lâm sàng đã biết
            past_facts_data = await consultation_repo.get_active_facts_with_provenance(patient_profile_id)
            if past_facts_data:
                past_facts_text = "\n".join(
                    f"- [{tpl.fact_type.upper()}] {tpl.label}: {fact.detail}"
                    for fact, tpl, _ in past_facts_data
                )
            else:
                past_facts_text = "Chưa ghi nhận dữ kiện lâm sàng tiền sử nào trước đó."

            # 2. Báo cáo lần khám gần nhất trước đó
            latest_past_report = await consultation_repo.get_latest_past_report(
                patient_profile_id, exclude_session_id=session_id
            )
            if latest_past_report and latest_past_report.summary:
                past_report_text = latest_past_report.summary
            else:
                past_report_text = "Chưa có báo cáo khám trước đó (đây là lần đầu hoặc chưa có phiên tư vấn nào)."

            # 3. Đoạn hội thoại đợt khám hiện tại
            raw_messages = await message_repo.list_by_conversation(conversation_id)
            messages = [
                m
                for m in raw_messages
                if m.content and not m.message_type.startswith("consultation_")
            ]

        # Tin nhắn được đánh số để LLM tham chiếu nguồn
        chat_transcript = "\n".join(
            f"[#{i}][{m.sender.upper()}]: {m.content}" for i, m in enumerate(messages, start=1)
        )
        messages_content = [m.content or "" for m in messages]

        summary_text = ""
        validated_facts: list[dict[str, Any]] = []
        provenance_pairs: list[list[str]] = []

        try:
            # Pre-condition check (Gatekeeper): nếu hội thoại không có tin nhắn nào từ bệnh nhân
            patient_messages = [m for m in messages if m.sender == "patient"]
            if not patient_messages:
                summary_text = (
                    f"## Tóm tắt phiên tư vấn\n"
                    f"- **Lý do khám**: {reason}\n"
                    f"- **Tiền sử ghi nhận**: {past_facts_text if past_facts_data else 'Chưa có'}\n"
                    f"- **Ghi nhận**: Bệnh nhân gửi yêu cầu tư vấn nhưng chưa trao đổi chi tiết về triệu chứng đợt này.\n"
                    f"- **Đề xuất Bác sĩ**: Cần hỏi trực tiếp triệu chứng khởi phát và vị trí tổn thương của bệnh nhân.\n\n"
                    f"*Kết luận AI chỉ mang tính chất tham khảo hỗ trợ tiền lâm sàng.*"
                )
            else:
                llm = get_model()
                prompt = [
                    SystemMessage(content=REPORT_SYSTEM_PROMPT),
                    HumanMessage(
                        content=(
                            "DƯỚI ĐÂY LÀ CÁC NGUỒN DỮ LIỆU CỦA BỆNH NHÂN:\n\n"
                            "=== 1. DỮ KIỆN LÂM SÀNG / TIỀN SỬ ĐÃ GHI NHẬN TỪ TRƯỚC ===\n"
                            f"{past_facts_text}\n\n"
                            "=== 2. TÓM TẮT LẦN KHÁM GẦN NHẤT TRƯỚC ĐÓ ===\n"
                            f"{past_report_text}\n\n"
                            "=== 3. ĐOẠN HỘI THOẠI ĐỢT KHÁM HIỆN TẠI ===\n"
                            f"{chat_transcript}\n\n"
                            "Hãy phân tích và sinh báo cáo JSON:"
                        )
                    ),
                ]
                response = await llm.ainvoke(prompt)
                raw_content = response.content
                if isinstance(raw_content, list):
                    raw_content = "\n".join(str(c) for c in raw_content)

                cleaned = str(raw_content).strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()

                parsed = json.loads(cleaned)
                summary_text = parsed.get("summary", "")
                raw_facts = parsed.get("facts", [])

                # Chạy qua middleware validation & evidence check
                validated_facts = _validate_facts_evidence(raw_facts, messages_content)

                # Chuẩn bị fact_id và provenance pairs
                for rf in validated_facts:
                    fact_id = f"cf-{uuid.uuid4()}"
                    rf["id"] = fact_id
                    for idx in rf.get("source_messages", []):
                        if 1 <= idx <= len(messages):
                            provenance_pairs.append([fact_id, messages[idx - 1].id])

        except Exception as exc:  # noqa: BLE001
            logger.exception("Lỗi khi worker sinh báo cáo tiền tư vấn: %s", exc)
            summary_text = (
                f"## Tóm tắt phiên tư vấn (Tự động)\n"
                f"- **Lý do khám**: {reason}\n"
                f"- **Tiền sử ghi nhận**: {past_facts_text if past_facts_data else 'Chưa có'}\n"
                f"- **Ghi nhận**: Bệnh nhân yêu cầu bác sĩ tư vấn trực tiếp.\n"
                f"- *Hệ thống đang đồng bộ dữ kiện lâm sàng.*"
            )

        # Đẩy kết quả về Core qua RabbitMQ
        response_msg = AgentResponseMessage(
            conversation_id=conversation_id,
            message_id=req.message_id,
            status="report_ready",
            session_id=session_id,
            report_summary=summary_text,
            facts=validated_facts,
            provenance_pairs=provenance_pairs,
        )

        await get_rabbitmq_client().publish(
            AGENT_RESPONSE_QUEUE,
            response_msg.model_dump_json().encode("utf-8"),
        )
        logger.info("Đã gửi kết quả báo cáo tiền tư vấn session=%s về Core", session_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi nghiêm trọng không thể xử lý báo cáo session=%s: %s", session_id, exc)
        failed_msg = AgentResponseMessage(
            conversation_id=conversation_id,
            message_id=req.message_id,
            status="report_failed",
            session_id=session_id,
            report_summary="Không thể sinh báo cáo tiền tư vấn do lỗi hệ thống.",
        )
        try:
            await get_rabbitmq_client().publish(
                AGENT_RESPONSE_QUEUE,
                failed_msg.model_dump_json().encode("utf-8"),
            )
        except Exception:
            logger.exception("Không thể gửi report_failed về response queue cho session=%s", session_id)
