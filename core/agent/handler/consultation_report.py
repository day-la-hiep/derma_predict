"""Handler xử lý sinh Báo cáo tiền tư vấn & trích xuất Dữ kiện lâm sàng trong Agent Worker."""
import json
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.common.llm import get_model
from agent.common.fact_extractor import validate_facts_evidence
from agent.dto.schemas import AgentResponseMessage, TurnRequest
from app.api.deps import get_postgres_client, get_rabbitmq_client
from app.config.constants import AGENT_RESPONSE_QUEUE
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """Bạn là trợ lý y khoa chuyên sâu da liễu, hỗ trợ tổng hợp báo cáo lâm sàng khách quan, trung thực và chính xác.
Nhiệm vụ của bạn là phân tích các nguồn dữ liệu lâm sàng được cung cấp (tiền sử đã biết, tóm tắt lần khám trước, và toàn bộ đoạn hội thoại đợt khám hiện tại gồm tin nhắn của bệnh nhân [PATIENT], trợ lý [AI] và bác sĩ [DOCTOR]), sau đó:
1. Rút trích các DỮ KIỆN LÂM SÀNG (clinical facts) mới hoặc cập nhật từ đoạn hội thoại hiện tại kèm chỉ số tin nhắn chứng cứ (`source_messages`).
2. Soạn BÁO CÁO TỔNG HỢP LÂM SÀNG (Pre-consultation Report) súc tích, chuyên nghiệp cho Bác sĩ da liễu đọc để nắm bắt tình hình ca bệnh.

CÁC NGUYÊN TẮC CỐT LÕI (BẮT BUỘC TUÂN THỦ NGHIÊM NGẶT):
1. CHỈ DỰA VÀO NỘI DUNG THỰC TẾ TRONG TIN NHẮN VÀ DỮ LIỆU ĐƯỢC CẤP:
   - Mọi thông tin (triệu chứng, thời gian khởi phát, vị trí, tiền sử, thuốc) BẮT BUỘC phải được trích dẫn trực tiếp từ các tin nhắn hoặc dữ liệu tiền sử có thật.
   - TUYỆT ĐỐI KHÔNG TỰ SUY DIỄN, DỰ ĐOÁN LINH TINH HOẶC BỊA ĐẶT (HALLUCINATION): Không tự ý thêm triệu chứng, không bịa đặt tiền sử hay mức độ nghiêm trọng mà các bên không đề cập.
   - THIẾU THÔNG TIN THÌ GHI RÕ: Nếu một thông tin không được đề cập trong tin nhắn (ví dụ: chưa rõ thời gian khởi phát, chưa rõ tiền sử dị ứng), BẮT BUỘC ghi rõ "Chưa ghi nhận trong hội thoại", tuyệt đối KHÔNG tự ý đoán mò hay giả định.
2. THU THẬP ĐẦY ĐỦ NHẬN ĐỊNH CỦA BÁC SĨ:
   - Nếu trong hội thoại có tin nhắn từ Bác sĩ (`[DOCTOR]`), phải thu thập và tóm tắt đầy đủ, chính xác các nhận định chuyên môn, đánh giá tổn thương, chẩn đoán sơ bộ/phân biệt, lời dặn dò và chỉ định điều trị/xét nghiệm mà Bác sĩ đã trao đổi.
   - Nếu chưa có tin nhắn nào từ Bác sĩ trong hội thoại này, ghi rõ: "Chưa ghi nhận trao đổi từ bác sĩ trong đợt này."
3. ĐÁNH GIÁ SƠ BỘ TỪ HỘI THOẠI:
   - Chỉ tổng hợp các bệnh lý nghi ngờ hoặc hướng nhận định đã được trợ lý AI hoặc Bác sĩ nêu ra trong đoạn chat. KHÔNG tự bịa thêm các chẩn đoán hoặc bệnh lý ngoài nội dung đã trao đổi.

Mỗi tin trong đoạn hội thoại hiện tại có số thứ tự dạng `[#i][PATIENT]: ...`, `[#i][AI]: ...`, hoặc `[#i][DOCTOR]: ...`.

BẮT BUỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON SAU (không kèm markdown code block hoặc text thừa):
{
  "facts": [
    {
      "template_label": "Tên chuẩn của triệu chứng/tổn thương/thuốc/nhận định",
      "fact_type": "symptom | lesion | history | medication | allergy | image_finding | other",
      "detail": "Mô tả chi tiết cụ thể từ nội dung trao đổi",
      "source_messages": [1]
    }
  ],
  "summary": "Nội dung tóm tắt lâm sàng (định dạng Markdown)"
}

Yêu cầu cho phần `summary` (dùng Markdown chuyên nghiệp, rõ ràng theo các đề mục sau):
- ## Lý do khám & Bệnh sử đợt này: Tóm tắt triệu chứng chính, thời gian khởi phát, diễn biến theo đúng mô tả của bệnh nhân trong hội thoại. Nếu chưa rõ, ghi "Chưa ghi nhận trong hội thoại".
- ## Vị trí & Đặc điểm tổn thương: Mô tả hình thái, vị trí, tính chất vùng da bị bệnh theo đúng tin nhắn/ảnh trong hội thoại. Không tự suy diễn đặc điểm không có trong tin nhắn.
- ## Tiền sử & Cơ địa đã biết: Tóm tắt dị ứng, bệnh nền, thuốc đã/đang dùng ghi nhận từ dữ kiện tiền sử hoặc lời kể bệnh nhân. Nếu không có, ghi "Chưa ghi nhận".
- ## Diễn biến các lần khám trước: Tóm tắt chẩn đoán hoặc diễn biến từ lần khám trước đó (nếu có dữ liệu). Nếu không có, ghi "Chưa có dữ liệu khám trước".
- ## Nhận định & Chỉ định của Bác sĩ: Thu thập toàn bộ nhận định chuyên môn, chẩn đoán, đánh giá tổn thương, lời khuyên và chỉ định (thuốc, xét nghiệm, chăm sóc) do Bác sĩ (`[DOCTOR]`) đưa ra trong hội thoại (nếu có). Nếu chưa có tin nhắn bác sĩ, ghi rõ "Chưa ghi nhận trao đổi từ bác sĩ trong đợt này."
- ## Đánh giá sơ bộ từ hội thoại (AI & Dữ kiện): Tóm tắt nhận định sơ bộ, các bệnh nghi ngờ và độ tin cậy đã được phân tích trong hội thoại (từ trợ lý AI hoặc dữ kiện đối chiếu). Nêu rõ căn cứ từ hội thoại; KHÔNG tự đưa thêm bệnh lý ngoài nội dung trao đổi.
- ## Dấu hiệu cờ đỏ (Red Flags): Các dấu hiệu nguy hiểm (sốt, đau dữ dội, nhiễm trùng lan nhanh, tổn thương niêm mạc...) đã được kiểm tra, loại trừ hoặc nghi ngờ trong tin nhắn. Nếu không ghi nhận dấu hiệu nào, ghi rõ "Chưa ghi nhận dấu hiệu cờ đỏ".
- ## Đề xuất cho Bác sĩ tiếp quản: Các câu hỏi lâm sàng cần làm rõ thêm với bệnh nhân về những chi tiết chưa được đề cập trong hội thoại, hoặc cận lâm sàng nên cân nhắc.
- Dòng lưu ý bắt buộc ở cuối: *Lưu ý: Báo cáo do AI tổng hợp chỉ dựa trên thông tin trao đổi trong tin nhắn và dữ liệu tiền sử, mang tính chất hỗ trợ tham khảo, không thay thế chẩn đoán y khoa chính thức của Bác sĩ.*

Yêu cầu cho `source_messages`: Mảng chứa số thứ tự các tin nhắn (`[#i]`) trực tiếp làm bằng chứng cho fact đó (triệu chứng từ `[PATIENT]`, nhận định/chỉ định từ `[DOCTOR]`). Tuyệt đối không bịa số thứ tự không có trong hội thoại.
"""


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
                    f"*Lưu ý: Báo cáo do AI tổng hợp chỉ dựa trên thông tin trao đổi trong tin nhắn và dữ liệu tiền sử, mang tính chất hỗ trợ tham khảo, không thay thế chẩn đoán y khoa chính thức của Bác sĩ.*"
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
                            "=== 3. ĐOẠN HỘI THOẠI ĐỢT KHÁM HIỆN TẠI (GỒM BỆNH NHÂN [PATIENT], AI [AI], VÀ BÁC SĨ [DOCTOR] NẾU CÓ) ===\n"
                            f"{chat_transcript}\n\n"
                            "Hãy phân tích và sinh báo cáo JSON tuân thủ nghiêm ngặt: chỉ dựa vào nội dung có thật trong tin nhắn, không tự suy đoán linh tinh, thu thập đầy đủ nhận định và chỉ định của Bác sĩ (nếu có):"
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
                validated_facts = validate_facts_evidence(raw_facts, messages_content)

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
