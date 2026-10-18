"""Các bước tra cứu sách dùng chung cho tool của agent và benchmark (`core/benchmark/`)"""
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agent.tools.hybrid_retrieval.bm25 import bm25_search
from agent.tools.hybrid_retrieval.fusion import book_result, merge_chunks
from agent.tools.hybrid_retrieval.kg import ExtractedEntity, extract_entities
from agent.tools.hybrid_retrieval.reranker import rerank
from agent.tools.hybrid_retrieval.semantic import semantic_search as semantic_leg

T = TypeVar("T")

LEG_LIMIT = 20  # số chunk lấy về từ mỗi nhánh (semantic / BM25) trước khi trộn / rerank
POOL = 20  # số chunk giữ lại sau RRF để đem rerank
PASSAGE_CHARS = 3000  # cắt đoạn đưa vào reranker (giới hạn kích thước request / chi phí token)

Payloads = list[dict[str, Any]]


@dataclass
class HybridResult:
    bm25_query: str
    notes: list[str] = field(default_factory=lambda: list[str]())
    semantic: Payloads = field(default_factory=lambda: Payloads())
    bm25: Payloads = field(default_factory=lambda: Payloads())
    candidates: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())  # sau RRF, chưa rerank
    ranked: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())  # sau rerank, hoặc thứ tự RRF nếu không rerank được
    reranked: bool = False


def expand_query(query: str, entities: list[ExtractedEntity]) -> str:
    """BM25 chỉ khớp đúng chữ: thêm tên Anh + Việt của thực thể để bắt cả sách viết khác ngôn ngữ với câu hỏi."""
    seen = query.lower()
    extra: list[str] = []
    for term in (t for e in entities for t in (e.text, e.vi)):
        if term and term.lower() not in seen:
            seen += " " + term.lower()
            extra.append(term)
    return " ".join([query, *extra])


def to_candidates(payloads: Payloads) -> list[dict[str, Any]]:
    # khoá bắt đầu bằng "_" bị `_clean` của tool loại khỏi kết quả trả cho agent
    return [
        {**book_result(p), "_chunk_id": str(p.get("chunk_id") or ""), "_passage": str(p.get("context_text") or p.get("text", ""))[:PASSAGE_CHARS]}
        for p in payloads
    ]


async def rank_candidates(
    query: str, candidates: list[dict[str, Any]], rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]] | None = None
) -> list[dict[str, Any]] | None:
    """Xếp theo điểm rerank; `None` nếu reranker không dùng được."""
    scores = await (rerank_fn or rerank)(query, [c["_passage"] for c in candidates])
    if scores is None:
        return None
    # làm tròn TRƯỚC khi sắp xếp: điểm sát nhau thành hoà và giữ thứ tự cũ (RRF / nhánh)
    scored = [{**c, "score": round(s, 3)} for c, s in zip(candidates, scores, strict=True)]
    return sorted(scored, key=lambda c: c["score"], reverse=True)


def _unwrap(name: str, result: list[T] | BaseException, notes: list[str]) -> list[T]:
    """Nhánh lỗi -> rỗng + ghi chú, để các nhánh còn lại vẫn cho kết quả."""
    if isinstance(result, BaseException):
        notes.append(f"Nhánh {name} không dùng được: {type(result).__name__}: {result}")
        return []
    return result


async def run_hybrid(
    query: str,
    *,
    semantic_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    bm25_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    entities_fn: Callable[[str], Awaitable[list[ExtractedEntity]]] | None = None,
    rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]] | None = None,
) -> HybridResult:
    notes: list[str] = []
    # trích thực thể một lần để mở rộng query BM25 (Việt–Anh)
    try:
        entities = await (entities_fn or extract_entities)(query)
    except Exception as exc:  # noqa: BLE001
        entities = []
        notes.append(f"Không mở rộng được query Việt–Anh ({type(exc).__name__}) — BM25 dùng query gốc.")
    bm25_query = expand_query(query, entities)
    semantic_r, bm25_r = await asyncio.gather(
        (semantic_fn or semantic_leg)(query, LEG_LIMIT), (bm25_fn or bm25_search)(bm25_query, LEG_LIMIT), return_exceptions=True
    )
    semantic = _unwrap("semantic", semantic_r, notes)
    bm25 = _unwrap("bm25", bm25_r, notes)

    # trộn 2 nhánh chunk theo RRF, khử trùng theo chunk_id
    candidates = to_candidates(merge_chunks(semantic, bm25, POOL))
    reranked = await rank_candidates(query, candidates, rerank_fn) if candidates else None
    return HybridResult(
        bm25_query=bm25_query,
        notes=notes,
        semantic=semantic,
        bm25=bm25,
        candidates=candidates,
        ranked=reranked if reranked is not None else candidates,
        reranked=reranked is not None,
    )
