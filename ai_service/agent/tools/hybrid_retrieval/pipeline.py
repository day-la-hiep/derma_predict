"""Các bước tra cứu sách dùng chung cho tool của agent và benchmark (`core/benchmark/`)"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx

from agent.tools.hybrid_retrieval.corpus import DOCUMENT_CORPUS, Corpus
from agent.tools.hybrid_retrieval.fusion import merge_by_id
from agent.tools.hybrid_retrieval.kg import ExtractedEntity, extract_entities
from app.config.settings import settings
from app.deps import get_knowledge_client

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
    graph: Payloads = field(default_factory=lambda: Payloads())  # chunk do cạnh DOC trỏ tới; rỗng khi nhánh tắt
    candidates: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())  # sau RRF, chưa rerank
    ranked: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())  # sau rerank, hoặc thứ tự RRF nếu không rerank được
    reranked: bool = False


async def rerank(query: str, passages: list[str]) -> list[float] | None:
    """Điểm liên quan 0..1 (Qwen3-Reranker qua OpenRouter) cho từng đoạn, cùng thứ tự `passages`; `None` nếu reranker không dùng được."""
    if not passages:
        return []
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.OPENROUTER_BASE_URL}/rerank",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json={"model": settings.RERANKER_MODEL, "query": query, "documents": passages},
            )
            resp.raise_for_status()
        scores = [0.0] * len(passages)
        for r in resp.json()["results"]:
            scores[r["index"]] = float(r["relevance_score"])
        return scores
    except Exception as exc:  # noqa: BLE001  # mất mạng, hết quota, model không có trên OpenRouter...
        logger.warning("không dùng được %s: %s", settings.RERANKER_MODEL, exc)
        return None


async def graph_search(entities: list[ExtractedEntity], limit: int, corpus: Corpus = DOCUMENT_CORPUS) -> Payloads:
    """Chunk sách mà cạnh DOC của thực thể trỏ tới; rỗng khi không phải corpus sách hoặc không có thực thể y khoa."""
    names = [t for e in entities if e.type != "other" for t in (e.text, e.vi) if t]
    if corpus.name != DOCUMENT_CORPUS.name or not names:
        return []
    return await get_knowledge_client().search_by_graph(names, limit)


def expand_query(query: str, entities: list[ExtractedEntity]) -> str:
    """BM25 chỉ khớp đúng chữ: thêm tên Anh + Việt của thực thể để bắt cả sách viết khác ngôn ngữ với câu hỏi."""
    seen = query.lower()
    extra: list[str] = []
    for term in (t for e in entities for t in (e.text, e.vi)):
        if term and term.lower() not in seen:
            seen += " " + term.lower()
            extra.append(term)
    return " ".join([query, *extra])


def to_candidates(payloads: Payloads, corpus: Corpus = DOCUMENT_CORPUS) -> list[dict[str, Any]]:
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
    corpus: Corpus = DOCUMENT_CORPUS,
    semantic_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    bm25_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    entities_fn: Callable[[str], Awaitable[list[ExtractedEntity]]] | None = None,
    graph_fn: Callable[[list[ExtractedEntity], int], Awaitable[Payloads]] | None = None,
    rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]] | None = None,
) -> HybridResult:
    notes: list[str] = []
    semantic_fn = semantic_fn or (lambda q, n: get_knowledge_client().search_semantic(q, n, corpus=corpus.name))
    bm25_fn = bm25_fn or (lambda q, n: get_knowledge_client().search_bm25(q, n, corpus=corpus.name))
    graph_fn = graph_fn or (lambda e, n: graph_search(e, n, corpus))
    # trích thực thể một lần để mở rộng query BM25 (Việt–Anh)
    try:
        entities = await (entities_fn or extract_entities)(query)
    except Exception as exc:  # noqa: BLE001
        logger.error("[hybrid] không trích được thực thể để mở rộng query: %s", exc, exc_info=True)
        entities = []
        notes.append(f"Không mở rộng được query Việt–Anh ({type(exc).__name__}) — BM25 dùng query gốc.")
    bm25_query = expand_query(query, entities)
    semantic_r, bm25_r, graph_r = await asyncio.gather(
        semantic_fn(query, LEG_LIMIT), bm25_fn(bm25_query, LEG_LIMIT), graph_fn(entities, LEG_LIMIT), return_exceptions=True
    )
    semantic = _unwrap("semantic", semantic_r, notes)
    bm25 = _unwrap("bm25", bm25_r, notes)
    graph = _unwrap("graph", graph_r, notes)

    # trộn các nhánh theo RRF, khử trùng theo id của nguồn
    candidates = to_candidates(merge_by_id(semantic, bm25, graph, POOL, corpus.id_key), corpus)
    from_graph = {str(p.get(corpus.id_key)) for p in graph}
    candidates = [{**c, "via_graph": True} if c["_id"] in from_graph else c for c in candidates]  # agent thấy chunk nào do đồ thị đề xuất
    reranked = await rank_candidates(query, candidates, rerank_fn) if candidates else None
    return HybridResult(
        bm25_query=bm25_query,
        notes=notes,
        semantic=semantic,
        bm25=bm25,
        graph=graph,
        candidates=candidates,
        ranked=reranked if reranked is not None else candidates,
        reranked=reranked is not None,
    )
