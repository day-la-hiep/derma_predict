"""Các bước tra cứu sách dùng chung cho tool của agent và benchmark (`core/benchmark/`)"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agent.tools.hybrid_retrieval.bm25 import bm25_search
from agent.tools.hybrid_retrieval.fusion import merge_by_id
from agent.tools.hybrid_retrieval.kg import ExtractedEntity, extract_entities
from agent.tools.hybrid_retrieval.reranker import rerank
from agent.tools.hybrid_retrieval.semantic import semantic_search as semantic_leg
from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS
from app.services.retrieval_service import RetrievalFilter, RetrievalCorpus

T = TypeVar("T")

logger = logging.getLogger(__name__)

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


def to_candidates(payloads: Payloads, corpus: RetrievalCorpus = DOCUMENT_CORPUS) -> list[dict[str, Any]]:
    # khoá bắt đầu bằng "_" bị `_clean` của tool loại khỏi kết quả trả cho agent
    return [
        {**corpus.to_result(p), "_id": str(p.get(corpus.id_key) or ""), "_passage": str(p.get("context_text") or p.get("text", ""))[:PASSAGE_CHARS]}
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
        logger.error("[hybrid] nhánh %s lỗi: %s: %s", name, type(result).__name__, result, exc_info=result)
        notes.append(f"Nhánh {name} không dùng được: {type(result).__name__}: {result}")
        return []
    return result


async def run_hybrid(
    query: str,
    *,
    corpus: RetrievalCorpus = DOCUMENT_CORPUS,
    filter: RetrievalFilter | None = None,
    semantic_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    bm25_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    entities_fn: Callable[[str], Awaitable[list[ExtractedEntity]]] | None = None,
    rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]] | None = None,
) -> HybridResult:
    notes: list[str] = []
    semantic_fn = semantic_fn or (lambda q, n: semantic_leg(q, n, corpus, filter))
    bm25_fn = bm25_fn or (lambda q, n: bm25_search(q, n, corpus, filter))
    # trích thực thể một lần để mở rộng query BM25 (Việt–Anh)
    try:
        entities = await (entities_fn or extract_entities)(query)
    except Exception as exc:  # noqa: BLE001
        logger.error("[hybrid] không trích được thực thể để mở rộng query: %s", exc, exc_info=True)
        entities = []
        notes.append(f"Không mở rộng được query Việt–Anh ({type(exc).__name__}) — BM25 dùng query gốc.")
    bm25_query = expand_query(query, entities)
    semantic_r, bm25_r = await asyncio.gather(
        semantic_fn(query, LEG_LIMIT), bm25_fn(bm25_query, LEG_LIMIT), return_exceptions=True
    )
    semantic = _unwrap("semantic", semantic_r, notes)
    bm25 = _unwrap("bm25", bm25_r, notes)

    # trộn 2 nhánh theo RRF, khử trùng theo id của nguồn
    candidates = to_candidates(merge_by_id(semantic, bm25, POOL, corpus.id_key), corpus)
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
