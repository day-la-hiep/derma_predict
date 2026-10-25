"""Tool tra cứu ca bệnh tương tự từ kho báo cáo kết luận thực tế đã được bác sĩ chẩn đoán và điều trị."""

import json
import logging
from typing import Any

from langchain_core.tools import tool

from agent.tools.hybrid_retrieval.corpus import FINALIZE_REPORT_CORPUS
from agent.tools.hybrid_retrieval.pipeline import run_hybrid
from app.api.deps import get_file_store_service

logger = logging.getLogger("agent.tools.search_finalize_report")

_MAX_LIMIT = 5


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def search_finalize_report(query: str, limit: int = 3) -> str:
    """Tra cứu các ca bệnh da liễu thực tế tương tự trong kho báo cáo kết luận của bệnh viện (do bác sĩ đã khám, chẩn đoán và xử trí).
    Tìm theo ngữ nghĩa + từ khoá (tên bệnh, thuốc) rồi xếp hạng lại theo độ liên quan tới query.

    Dùng khi:
    - Cần đối chiếu các triệu chứng, tổn thương da, diễn tiến bệnh của người dùng với các ca bệnh lâm sàng thực tế đã được bác sĩ chẩn đoán xác định.
    - Cần tham khảo hướng điều trị, dặn dò chăm sóc và lập luận lâm sàng của bác sĩ chuyên khoa đối với bệnh cảnh tương tự.
    - Tìm bằng chứng ca lâm sàng thực tế để hỗ trợ xếp hạng giả thuyết hoặc phân biệt các bệnh có biểu hiện gần giống nhau.

    `relevance_score` là độ liên quan 0..1 sau rerank (không phải xác suất chẩn đoán); `ranked_by` cho biết có rerank được hay chỉ dùng
    thứ tự trộn. Phần `notes` nêu nhánh nào không dùng được — khi đó nói rõ là chưa tra được nguồn đó thay vì suy đoán.

    Args:
        query: Mô tả triệu chứng, vị trí tổn thương, tiền sử hoặc tên bệnh nghi ngờ cần tìm ca tương tự (vd: "mảng da khô ngứa nhiều ở khuỷu tay", "sẩn phù rải rác tự hết", "nghi vảy nến mảng vảy trắng bạc").
        limit: Số lượng ca bệnh tương tự tối đa cần lấy (mặc định 3, tối đa 5).
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    logger.info("🔍 [search_finalize_report] Gọi tool tra cứu ca bệnh | query='%s' | limit=%d", query, limit)
    try:
        result = await run_hybrid(query, corpus=FINALIZE_REPORT_CORPUS)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ [search_finalize_report] Lỗi khi tra cứu ca bệnh: %s", exc, exc_info=True)
        return _dumps({"evidence_found": False, "query": query, "cases": [], "error": f"Lỗi khi tra cứu ca bệnh: {exc}"})

    notes = result.notes
    if not result.candidates:
        logger.info("ℹ️ [search_finalize_report] Không tìm thấy ca bệnh nào phù hợp cho query='%s'", query)
        return _dumps({
            "evidence_found": False,
            "query": query,
            "cases": [],
            "notes": [*notes, "Không tìm thấy ca bệnh tương tự trong kho báo cáo kết luận tham khảo."],
        })
    if result.reranked:
        ranked_by = "reranker"
    else:
        notes.append("Không rerank được (reranker không khả dụng) — dùng thứ tự trộn semantic + BM25.")
        ranked_by = "rrf"

    file_store = get_file_store_service()
    cases: list[dict[str, Any]] = []
    for c in result.ranked[:limit]:
        images: list[dict[str, Any]] = []
        for img in c["images"]:
            storage_key = img.get("storage_key")
            url = None
            if storage_key:
                try:
                    url = file_store.presigned_url(storage_key)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[search_finalize_report] không tạo được presigned URL cho %s: %s", storage_key, exc)
            images.append({
                "confirmed_label": img.get("confirmed_label"),
                "body_site": img.get("body_site"),
                "description": img.get("description"),
                "storage_key": storage_key,
                "url": url,
            })
        cases.append({
            **{k: v for k, v in c.items() if not k.startswith("_") and k not in ("score", "images")},
            "relevance_score": c.get("score"),
            "images": images,
        })

    logger.info(
        "✅ [search_finalize_report] Tìm thấy %d ca bệnh tương tự (Top 1: '%s', ranked_by=%s)",
        len(cases),
        cases[0].get("diagnosis", "N/A"),
        ranked_by,
    )
    return _dumps({
        "evidence_found": True,
        "query": query,
        "ranked_by": ranked_by,
        "total_cases": len(cases),
        "cases": cases,
        "notes": notes,
    })
