"""Tool tra cứu cho agent"""
import json
import logging
from typing import Any

from langchain_core.tools import tool

from agent.tools.hybrid_retrieval.bm25 import bm25_search
from agent.tools.hybrid_retrieval.kg import extract_entities
from agent.tools.hybrid_retrieval.kg_templates import INTENTS, Intent, run_intent
from agent.tools.hybrid_retrieval.pipeline import LEG_LIMIT, expand_query, rank_candidates, run_hybrid, to_candidates
from agent.tools.hybrid_retrieval.semantic import semantic_search as semantic_leg

logger = logging.getLogger(__name__)

_MAX_TOP_K = 10
_MAX_KG_TOP_K = 30


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _clean(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"rank": i, **{k: v for k, v in r.items() if not k.startswith("_") and v != ""}} for i, r in enumerate(results, start=1)]


def _with_bm25_query(payload: dict[str, Any], query: str, bm25_query: str | None) -> dict[str, Any]:
    """Chỉ ghi `bm25_query` khi nó khác câu hỏi gốc, để người thử thấy được query BM25 thật sự đã chạy."""
    return {**payload, "bm25_query": bm25_query} if bm25_query and bm25_query != query else payload


async def _book_response(
    query: str, payloads: list[dict[str, Any]], top_k: int, leg: str, empty_note: str, bm25_query: str | None = None
) -> str:
    """Rerank các đoạn sách của một nhánh theo câu hỏi; không rerank được thì giữ thứ tự của nhánh đó."""
    notes: list[str] = []
    if not payloads:
        return _dump(_with_bm25_query({"query": query, "evidence_found": False, "results": [], "notes": [empty_note]}, query, bm25_query))
    candidates = to_candidates(payloads)
    ranked = await rank_candidates(query, candidates)
    if ranked is not None:
        candidates = ranked
        ranked_by = "reranker"
    else:
        notes.append(f"Không rerank được (reranker không khả dụng) — giữ thứ tự của nhánh {leg}.")
        ranked_by = leg
    return _dump(
        _with_bm25_query(
            {"query": query, "evidence_found": True, "ranked_by": ranked_by, "results": _clean(candidates[:top_k]), "notes": notes},
            query,
            bm25_query,
        )
    )


async def _bm25_query(query: str) -> str:
    try:
        entities = await extract_entities(query)
    except Exception as exc:  # noqa: BLE001  # LLM lỗi -> vẫn tìm từ khoá bằng query gốc
        logger.error("[keyword_search] không trích được thực thể để mở rộng query: %s", exc, exc_info=True)
        entities = []
    return expand_query(query, entities)


@tool
async def hybrid_retrieval(query: str, top_k: int = 5) -> str:
    """Tra cứu tri thức da liễu từ SÁCH GIÁO KHOA đã số hoá trong MỘT lần gọi: tìm theo ngữ nghĩa + từ khoá rồi xếp hạng lại
    theo độ liên quan tới câu hỏi. Là tool MẶC ĐỊNH cho yêu cầu chung chung hoặc chưa rõ cần loại thông tin nào (mô tả bệnh,
    triệu chứng, phân biệt chẩn đoán, điều trị, chống chỉ định, yếu tố nguy cơ) — kèm nguồn trích dẫn. Khi đã lập luận rõ cần
    đúng thông tin gì thì cân nhắc `semantic_search` / `keyword_search`; cần quan hệ bệnh–triệu chứng–thuốc từ đồ thị thì dùng
    `knowledge_graph_query`.

    Mỗi kết quả có `source="book"` kèm `title`, `section`, `pages` để trích dẫn. `score` là độ liên quan 0..1 sau rerank (không
    phải xác suất chẩn đoán); `ranked_by` cho biết có rerank được hay chỉ dùng thứ tự trộn. Phần `notes` nêu nhánh nào không
    dùng được — khi đó nói rõ là chưa tra được nguồn đó thay vì suy đoán.

    Args:
        query: Câu hỏi hoặc mô tả cần tra, tiếng Việt hoặc Anh, nêu rõ bệnh / triệu chứng / thuốc. Mỗi lần gọi một chủ đề cụ
            thể sẽ cho kết quả tốt hơn một câu dài trộn nhiều ý.
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    result = await run_hybrid(query)
    notes = result.notes
    if not result.candidates:
        return _dump(
            _with_bm25_query(
                {
                    "query": query,
                    "evidence_found": False,
                    "results": [],
                    "notes": [*notes, "KHÔNG có bằng chứng: không có đoạn sách nào khớp (chưa index sách, hoặc không có đoạn liên quan)."],
                },
                query,
                result.bm25_query,
            )
        )
    if result.reranked:
        ranked_by = "reranker"
    else:
        notes.append("Không rerank được (reranker không khả dụng) — dùng thứ tự trộn semantic + BM25.")
        ranked_by = "rrf"
    return _dump(
        _with_bm25_query(
            {"query": query, "evidence_found": True, "ranked_by": ranked_by, "results": _clean(result.ranked[:top_k]), "notes": notes},
            query,
            result.bm25_query,
        )
    )


@tool
async def semantic_search(query: str, top_k: int = 5) -> str:
    """Tìm đoạn SÁCH GIÁO KHOA da liễu đã số hoá theo NGỮ NGHĨA (embedding) — hợp với câu hỏi diễn đạt tự nhiên, mô tả triệu
    chứng, khái niệm; bắt được cả khi sách dùng từ khác với câu hỏi. Dùng để lấy bằng chứng (mô tả bệnh, triệu chứng, phân biệt
    chẩn đoán, điều trị, chống chỉ định, yếu tố nguy cơ) kèm nguồn trích dẫn. Cần khớp đúng tên thuốc / mã / thuật ngữ → dùng
    `keyword_search`. Tool chuyên biệt: dùng khi đã rõ cần tra theo ngữ nghĩa; yêu cầu chung chung → `hybrid_retrieval`.

    Mỗi kết quả có `source="book"` kèm `title`, `section`, `pages` để trích dẫn; `score` là độ liên quan 0..1 sau rerank (không
    phải xác suất chẩn đoán). `evidence_found=false` hoặc `notes` báo lỗi → nói rõ là chưa tra được nguồn này thay vì suy đoán.

    Args:
        query: Câu hỏi hoặc mô tả cần tra, tiếng Việt hoặc Anh, nêu rõ bệnh / triệu chứng / thuốc. Mỗi lần một chủ đề cụ thể.
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    try:
        payloads = await semantic_leg(query, LEG_LIMIT)
    except Exception as exc:  # noqa: BLE001  # Qdrant / embedding lỗi -> báo cho model thay vì làm hỏng cả lượt
        logger.error("[semantic_search] lỗi: %s", exc, exc_info=True)
        return _dump({"query": query, "evidence_found": False, "results": [], "notes": [f"semantic_search không dùng được: {type(exc).__name__}: {exc}"]})
    return await _book_response(
        query, payloads, top_k, "semantic", "KHÔNG có đoạn sách nào khớp (chưa index sách, hoặc không có đoạn liên quan)."
    )


@tool
async def keyword_search(query: str, top_k: int = 5) -> str:
    """Tìm đoạn SÁCH GIÁO KHOA da liễu đã số hoá theo TỪ KHOÁ (BM25) — hợp khi cần khớp đúng tên thuốc, hoạt chất, mã, tên bệnh
    hay thuật ngữ chuyên môn mà tìm theo ngữ nghĩa hay bỏ lỡ. Query nên là vài từ khoá chính (tên bệnh / thuốc / thuật ngữ), không
    phải câu dài. Câu hỏi diễn đạt tự nhiên, mô tả triệu chứng → dùng `semantic_search`.

    Kết quả cùng dạng với `semantic_search`: `source="book"` kèm `title`, `section`, `pages`; `score` là độ liên quan 0..1 sau
    rerank. `evidence_found=false` → không đoạn nào chứa từ khoá đó.

    Args:
        query: Các từ khoá cần khớp, tiếng Việt hoặc Anh (vd "methotrexate chống chỉ định", "vảy nến mảng").
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    bm25_query = query
    try:
        bm25_query = await _bm25_query(query)
        payloads = await bm25_search(bm25_query, LEG_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.error("[keyword_search] lỗi: %s", exc, exc_info=True)
        return _dump({"query": query, "evidence_found": False, "results": [], "notes": [f"keyword_search không dùng được: {type(exc).__name__}: {exc}"]})
    return await _book_response(
        query, payloads, top_k, "bm25", "KHÔNG có đoạn sách nào chứa các từ khoá này (chưa index sách, hoặc không khớp).", bm25_query
    )


@tool
async def knowledge_graph_query(intent: Intent, entities: list[str], top_k: int = 10) -> str:
    """Tra ĐỒ THỊ TRI THỨC PrimeKG / DermO / hồ sơ BYT theo ĐÚNG MỤC ĐÍCH (`intent`) — mỗi intent chạy một truy vấn riêng trên đúng
    nhóm quan hệ cần thiết, nên cho kết quả gọn và đúng chỗ hơn tìm chung. Kết quả CHỈ LÀ GỢI Ý (`source="kg"`, điểm đồ thị là
    heuristic), KHÔNG phải bằng chứng lâm sàng và không phải chẩn đoán: muốn khẳng định phải đối chiếu bằng `hybrid_retrieval` /
    `semantic_search` / `keyword_search`. Có thể gọi nhiều lần với intent khác nhau cho cùng một bệnh.

    `intent` (chọn một):
    - `diseases_with_symptom`: có triệu chứng, chưa rõ bệnh → bệnh ứng viên xếp theo độ đặc hiệu. `entities` = các triệu chứng.
    - `differential`: đã có 1–3 bệnh nghi ngờ → bệnh dễ nhầm + triệu chứng nên hỏi để phân biệt. `entities` = các bệnh.
    - `disease_overview`: hồ sơ nhanh một bệnh (triệu chứng, vị trí, nguy cơ, cờ đỏ, bệnh liên quan). `entities` = bệnh.
    - `symptoms_of_disease`: triệu chứng có / không có của một bệnh. `entities` = bệnh.
    - `red_flags_risk`: cờ đỏ, yếu tố nguy cơ, vị trí thường gặp của bệnh (dùng khi cần kiểm tra dấu hiệu nguy hiểm).
    - `treatments`: thuốc chỉ định / dùng ngoài chỉ định cho bệnh. `entities` = bệnh.
    - `contraindications`: chống chỉ định. `entities` = thuốc hoặc bệnh.
    - `drug_profile`: chỉ định, chống chỉ định, tác dụng phụ, tương tác của thuốc (≥2 thuốc → chỉ tương tác giữa chúng).

    `entities`: tên bằng tiếng Anh y khoa chuẩn thì khớp tốt nhất (vd "psoriasis", "pruritus", "methotrexate"); tiếng Việt vẫn được
    thử dịch. `notes` báo thực thể không có trong đồ thị / lỗi (Neo4j chưa chạy...) → nói rõ là chưa tra được thay vì suy đoán.

    Args:
        intent: Mục đích tra cứu, một trong các giá trị ở trên.
        entities: Tên bệnh / triệu chứng / thuốc (tối đa 6), loại phải khớp intent.
        top_k: Số dòng dữ kiện trả về (1-30, mặc định 10).
    """
    top_k = min(max(top_k, 1), _MAX_KG_TOP_K)
    query = f"{intent}: {', '.join(entities)}"
    if intent not in INTENTS:
        return _dump({"query": query, "results": [], "notes": [f"intent '{intent}' không hợp lệ — chọn một trong: {', '.join(INTENTS)}."]})
    try:
        facts, notes, resolved = await run_intent(intent, entities, top_k)
    except Exception as exc:  # noqa: BLE001
        logger.error("[knowledge_graph_query] lỗi intent=%s: %s", intent, exc, exc_info=True)
        return _dump({"query": query, "results": [], "notes": [f"knowledge_graph_query không dùng được: {type(exc).__name__}: {exc}"]})
    results = _clean([{"source": "kg", "title": "PrimeKG / DermO", **f} for f in facts])
    return _dump({"query": query, "intent": intent, **resolved, "results": results, "notes": notes})
