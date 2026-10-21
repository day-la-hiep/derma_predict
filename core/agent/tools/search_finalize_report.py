"""Tool tra cứu ca bệnh tương tự từ kho báo cáo kết luận thực tế đã được bác sĩ chẩn đoán và điều trị."""

import json
import logging
from typing import Any

from langchain_core.tools import tool

from app.api.deps import get_file_store_service, get_finalize_report_index_service

logger = logging.getLogger("agent.tools.search_finalize_report")


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def search_finalize_report(query: str, limit: int = 3) -> str:
    """Tra cứu các ca bệnh da liễu thực tế tương tự trong kho báo cáo kết luận của bệnh viện (do bác sĩ đã khám, chẩn đoán và xử trí).

    Dùng khi:
    - Cần đối chiếu các triệu chứng, tổn thương da, diễn tiến bệnh của người dùng với các ca bệnh lâm sàng thực tế đã được bác sĩ chẩn đoán xác định.
    - Cần tham khảo hướng điều trị, dặn dò chăm sóc và lập luận lâm sàng của bác sĩ chuyên khoa đối với bệnh cảnh tương tự.
    - Tìm bằng chứng ca lâm sàng thực tế để hỗ trợ xếp hạng giả thuyết hoặc phân biệt các bệnh có biểu hiện gần giống nhau.

    Args:
        query: Mô tả triệu chứng, vị trí tổn thương, tiền sử hoặc tên bệnh nghi ngờ cần tìm ca tương tự (vd: "mảng da khô ngứa nhiều ở khuỷu tay", "sẩn phù rải rác tự hết", "nghi vảy nến mảng vảy trắng bạc").
        limit: Số lượng ca bệnh tương tự tối đa cần lấy (mặc định 3, tối đa 5).
    """
    limit = max(1, min(limit, 5))
    logger.info("🔍 [search_finalize_report] Gọi tool tra cứu ca bệnh | query='%s' | limit=%d", query, limit)
    try:
        service = get_finalize_report_index_service()
        cases = await service.search_reports(query=query, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ [search_finalize_report] Lỗi khi tra cứu ca bệnh: %s", exc, exc_info=True)
        return _dumps({
            "evidence_found": False,
            "query": query,
            "cases": [],
            "error": f"Lỗi khi tra cứu ca bệnh: {exc}",
        })

    if not cases:
        logger.info("ℹ️ [search_finalize_report] Không tìm thấy ca bệnh nào phù hợp cho query='%s'", query)
        return _dumps({
            "evidence_found": False,
            "query": query,
            "cases": [],
            "note": "Không tìm thấy ca bệnh tương tự trong kho báo cáo kết luận tham khảo.",
        })

    top_diagnosis = cases[0].get("diagnosis", "N/A")
    top_score = cases[0].get("score", 0.0)
    logger.info(
        "✅ [search_finalize_report] Tìm thấy %d ca bệnh tương tự (Top 1: '%s', điểm=%.3f)",
        len(cases),
        top_diagnosis,
        top_score,
    )

    # Lọc và định dạng các ca tìm thấy
    file_store = get_file_store_service()
    formatted_cases = []
    for c in cases:
        images_out = []
        for img in (c.get("images") or []):
            storage_key = img.get("storage_key")
            url = None
            if storage_key:
                try:
                    url = file_store.presigned_url(storage_key)
                except Exception:  # noqa: BLE001
                    url = None
            images_out.append({
                "confirmed_label": img.get("confirmed_label"),
                "body_site": img.get("body_site"),
                "description": img.get("description"),
                "storage_key": storage_key,
                "url": url,
            })
        formatted_cases.append({
            "case_id": c.get("case_id"),
            "diagnosis": c.get("diagnosis"),
            "relevance_score": c.get("score"),
            "patient_info": {
                "gender": c.get("gender"),
                "age": c.get("age"),
                "allergies": c.get("allergies"),
                "medical_history": c.get("medical_history"),
            },
            "symptoms_and_facts": c.get("clinical_facts", []),
            "doctor_assessment": c.get("doctor_reasoning"),
            "urgency": c.get("urgency"),
            "treatment_instructions": c.get("treatment_instructions"),
            "doctor_notes": c.get("doctor_notes"),
            "case_summary": c.get("summary"),
            "images": images_out,
        })

    return _dumps({
        "evidence_found": True,
        "query": query,
        "total_cases": len(formatted_cases),
        "cases": formatted_cases,
    })
