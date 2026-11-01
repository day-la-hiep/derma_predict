"""Tool truy vấn đồ thị tri thức trích từ sách giáo khoa (Neo4j, source='DOC')."""

import json
import logging
from typing import Any

from langchain_core.tools import tool

from app.api.deps import get_document_graph_service

logger = logging.getLogger("agent.tools.query_document_graph")


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def query_document_graph(entity: str, relation: str | None = None, limit: int = 10) -> str:
    """Truy vấn đồ thị tri thức trích từ sách giáo khoa đã số hoá (quan hệ giữa bệnh/thuốc/triệu chứng...).

    Dùng khi:
    - Cần quan hệ cụ thể từ sách (điều trị, chống chỉ định, triệu chứng, biến chứng...) cho một bệnh/thuốc.
    - Cần trích dẫn nguồn (sách, trang) cho câu trả lời.

    Kết quả gồm chủ thể, quan hệ, đối tượng, câu trích (evidence), trang, document_id. Chỉ là gợi ý, đối chiếu qua hybrid_retrieval.

    Args:
        entity: Tên bệnh/thuốc/triệu chứng (tiếng Anh hoặc tiếng Việt) cần truy vấn.
        relation: Loại quan hệ (vd 'INDICATION', 'CONTRAINDICATION', 'TREATS'); None = tất cả.
        limit: Số quan hệ tối đa (mặc định 10).
    """
    try:
        service = get_document_graph_service()
    except Exception as exc:  # noqa: BLE001
        return _dumps({"evidence_found": False, "error": f"Chưa cấu hình đồ thị tri thức: {exc}"})

    if not service.configured:
        return _dumps({"evidence_found": False, "note": "Đồ thị tri thức (Neo4j) chưa được cấu hình."})

    try:
        rows = await service.query_document_graph(entity, relation, limit)
    except Exception as exc:  # noqa: BLE001
        logger.error("Lỗi truy vấn đồ thị tài liệu: %s", exc, exc_info=True)
        return _dumps({"evidence_found": False, "entity": entity, "error": f"Lỗi truy vấn: {exc}"})

    if not rows:
        return _dumps({
            "evidence_found": False,
            "entity": entity,
            "note": "Không tìm thấy quan hệ nào trong đồ thị trích từ sách cho thực thể này.",
        })

    return _dumps({
        "evidence_found": True,
        "entity": entity,
        "total": len(rows),
        "triples": rows,
    })