"""Tool tra cứu ca bệnh tương tự theo ẢNH tổn thương da (phân loại ảnh → tìm báo cáo kết luận có ảnh cùng nhãn)."""

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from agent.context.agent_context import AgentContext
from agent.tools.skin_image_classifier import _resolve_object_key, get_predictor
from app.api.deps import get_file_store_service, get_finalize_report_index_service

logger = logging.getLogger("agent.tools.search_finalize_report_by_image")


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def search_finalize_report_by_image(object_key: str, runtime: ToolRuntime[AgentContext, Any]) -> str:
    """Tra cứu các ca bệnh da liễu thực tế có ẢNH tổn thương tương tự trong kho báo cáo kết luận.

    Dùng khi người dùng gửi ảnh tổn thương da và cần đối chiếu với các ca bệnh lâm sàng đã được bác sĩ chẩn đoán
    (trong đó có ảnh bệnh đã lưu). Tool tự phân loại ảnh bằng CNN để lấy bệnh nghi ngờ, rồi tìm các ca bệnh
    tương tự trong kho (kèm ảnh bệnh đã lưu) để hỗ trợ xếp hạng giả thuyết.

    KẾT QUẢ CHỈ LÀ THAM KHẢO, KHÔNG PHẢI CHẨN ĐOÁN.

    Args:
        object_key: Object key MinIO của ảnh người dùng gửi, lấy nguyên văn từ phần "[Ảnh đính kèm]".
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    object_key = _resolve_object_key(object_key, ctx.image_keys)
    file_store = get_file_store_service()
    image_bytes = await file_store.get_object_bytes(object_key)
    if image_bytes is None:
        return _dumps({"evidence_found": False, "error": f"Không tìm thấy ảnh với object_key='{object_key}'."})

    predictor = get_predictor()
    try:
        preds = await asyncio.to_thread(predictor.predict, image_bytes, 3)
    except Exception as exc:  # noqa: BLE001
        logger.error("Lỗi phân loại ảnh: %s", exc, exc_info=True)
        return _dumps({"evidence_found": False, "error": f"Lỗi phân loại ảnh: {exc}"})

    top_label = preds[0]["disease"] if preds else ""
    top_conf = preds[0]["confidence"] if preds else 0.0

    service = get_finalize_report_index_service()
    try:
        cases = await service.search_reports(query=top_label, limit=5)
    except Exception as exc:  # noqa: BLE001
        logger.error("Lỗi tra cứu ca bệnh: %s", exc, exc_info=True)
        return _dumps({"evidence_found": False, "query_label": top_label, "error": f"Lỗi tra cứu: {exc}"})

    if not cases:
        return _dumps({
            "evidence_found": False,
            "query_label": top_label,
            "cnn_confidence": round(float(top_conf), 3),
            "note": "Không tìm thấy ca bệnh tương tự trong kho báo cáo kết luận tham khảo.",
        })

    formatted = []
    for c in cases:
        images_out = []
        for img in (c.get("images") or []):
            sk = img.get("storage_key")
            url = None
            if sk:
                try:
                    url = file_store.presigned_url(sk)
                except Exception:  # noqa: BLE001
                    url = None
            images_out.append({
                "confirmed_label": img.get("confirmed_label"),
                "body_site": img.get("body_site"),
                "description": img.get("description"),
                "url": url,
            })
        formatted.append({
            "case_id": c.get("case_id"),
            "diagnosis": c.get("diagnosis"),
            "relevance_score": c.get("score"),
            "cnn_top_label": top_label,
            "patient_info": {
                "gender": c.get("gender"),
                "age": c.get("age"),
            },
            "symptoms_and_facts": c.get("clinical_facts", []),
            "doctor_assessment": c.get("doctor_reasoning"),
            "urgency": c.get("urgency"),
            "treatment_instructions": c.get("treatment_instructions"),
            "doctor_notes": c.get("doctor_notes"),
            "images": images_out,
        })

    return _dumps({
        "evidence_found": True,
        "query_label": top_label,
        "cnn_confidence": round(float(top_conf), 3),
        "total_cases": len(formatted),
        "cases": formatted,
    })