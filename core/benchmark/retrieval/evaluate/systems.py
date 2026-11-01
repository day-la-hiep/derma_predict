import asyncio
import random
import time
from typing import Any

from agent.tools.hybrid_retrieval.bm25 import bm25_search
from agent.tools.hybrid_retrieval.kg import ExtractedEntity, extract_entities
from agent.tools.hybrid_retrieval.pipeline import LEG_LIMIT, HybridResult, rank_candidates, run_hybrid, to_candidates
from agent.tools.hybrid_retrieval.reranker import rerank
from agent.tools.hybrid_retrieval.semantic import semantic_search
from benchmark.retrieval.evaluate.cache import Cache, digest
from benchmark.retrieval.schema import ChunkRecord, Hit, Run

SYSTEMS = ["random", "semantic", "bm25", "bm25_expand", "rrf", "hybrid", "hybrid_no_expand", "semantic_rerank", "bm25_expand_rerank"]
DEPTH = 20
_RERANK_TRIES = 3

DESCRIPTIONS = {
    "random": "ngẫu nhiên (mốc sàn)",
    "semantic": "semantic thô",
    "bm25": "BM25 query gốc",
    "bm25_expand": "BM25 + mở rộng Việt-Anh",
    "rrf": "RRF(semantic, bm25_expand), chưa rerank",
    "hybrid": "hybrid thật: RRF + rerank (có mở rộng query)",
    "hybrid_no_expand": "hybrid, BM25 dùng query gốc (khi mở rộng query bị lỗi)",
    "semantic_rerank": "semantic + rerank",
    "bm25_expand_rerank": "BM25 mở rộng + rerank (= keyword_search)",
}
_NEEDS_EXPANSION = {"bm25_expand", "rrf", "hybrid", "bm25_expand_rerank"}


async def _no_entities(query: str) -> list[ExtractedEntity]:
    return []


def _hits(ids: list[str]) -> list[Hit]:
    return [Hit(chunk_id=c, rank=r) for r, c in enumerate(ids[:DEPTH], start=1)]


def _scored(ranked: list[dict[str, Any]]) -> list[Hit]:
    return [Hit(chunk_id=c["_id"], rank=r, score=c.get("score")) for r, c in enumerate(ranked[:DEPTH], start=1)]


def _ids(payloads: list[dict[str, Any]]) -> list[str]:
    return [str(p["chunk_id"]) for p in payloads]


class Retriever:
    # hybrid/rrf/hybrid_no_expand chạy thẳng `run_hybrid` của agent; ở đây chỉ chen cache và lọc theo snapshot qua các hàm truyền vào
    def __init__(self, corpus: dict[str, ChunkRecord], snapshot: str, llm_model: str, cache: Cache | None = None) -> None:
        self.corpus = corpus
        self.snapshot = snapshot
        self.llm_model = llm_model
        self.cache = cache or Cache()
        self._ids = sorted(corpus)

    async def _leg(self, kind: str, query: str) -> list[dict[str, Any]]:
        key = f"{kind}|{self.snapshot}|{query}"
        cached = self.cache.get(key)
        if cached is None:
            fn = semantic_search if kind == "sem" else bm25_search
            payloads = await fn(query, LEG_LIMIT)
            cached = [str(p["chunk_id"]) for p in payloads]
            self.cache.set(key, cached)
        return [self.corpus[c].model_dump() for c in cached if c in self.corpus]

    async def _semantic(self, query: str, limit: int) -> list[dict[str, Any]]:
        return await self._leg("sem", query)

    async def _bm25(self, query: str, limit: int) -> list[dict[str, Any]]:
        return await self._leg("bm25", query)

    async def _entities(self, query: str) -> list[ExtractedEntity]:
        key = f"ent|{self.llm_model}|{query}"
        cached = self.cache.get(key)
        if cached is None:
            cached = [e.model_dump() for e in await extract_entities(query)]  # lỗi thì để `run_hybrid` ghi chú như tool thật
            self.cache.set(key, cached)
        return [ExtractedEntity.model_validate(e) for e in cached]

    async def _rerank(self, query: str, passages: list[str]) -> list[float] | None:
        key = f"rr|{self.snapshot}|{digest(query, *passages)}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        for attempt in range(_RERANK_TRIES):
            scores = await rerank(query, passages)
            if scores is not None:
                self.cache.set(key, scores)
                return scores
            await asyncio.sleep(2 * (attempt + 1))
        return None

    async def _pipeline(self, text: str, expand: bool = True) -> HybridResult:
        return await run_hybrid(
            text,
            semantic_fn=self._semantic,
            bm25_fn=self._bm25,
            entities_fn=self._entities if expand else _no_entities,
            rerank_fn=self._rerank,
        )

    async def _single_leg_rerank(self, text: str, payloads: list[dict[str, Any]], notes: list[str]) -> tuple[list[Hit], str]:
        candidates = to_candidates(payloads)
        ranked = await rank_candidates(text, candidates, self._rerank)
        if ranked is None:
            notes.append("reranker không dùng được -> giữ thứ tự nhánh")
            return _hits([c["_id"] for c in candidates]), "fallback"
        return _scored(ranked), "reranker"

    async def run_all(self, qid: str, text: str, systems: list[str] | None = None) -> list[Run]:
        systems = systems or SYSTEMS
        notes: list[str] = []
        hybrid = await self._pipeline(text) if _NEEDS_EXPANSION & set(systems) else None
        no_expand = await self._pipeline(text, expand=False) if "hybrid_no_expand" in systems else None
        if hybrid:
            notes += hybrid.notes
        sem = hybrid.semantic if hybrid else await self._leg("sem", text)
        bm25_raw = await self._leg("bm25", text)
        results: list[Run] = []

        async def one(system: str) -> Run:
            start = time.perf_counter()
            ranked_by: str | None = None
            extra: list[str] = []
            hits: list[Hit]
            if system == "random":
                hits = _hits(random.Random(qid).sample(self._ids, DEPTH))
            elif system == "semantic":
                hits = _hits(_ids(sem))
            elif system == "bm25":
                hits = _hits(_ids(bm25_raw))
            elif system == "bm25_expand":
                assert hybrid
                hits = _hits(_ids(hybrid.bm25))
            elif system == "rrf":
                assert hybrid
                hits = _hits([c["_id"] for c in hybrid.candidates])
            elif system in ("hybrid", "hybrid_no_expand"):
                result = hybrid if system == "hybrid" else no_expand
                assert result
                hits, ranked_by = _scored(result.ranked), "reranker" if result.reranked else "fallback"
                if system == "hybrid_no_expand":
                    extra = result.notes
            elif system == "semantic_rerank":
                hits, ranked_by = await self._single_leg_rerank(text, sem, extra)
            elif system == "bm25_expand_rerank":
                assert hybrid
                hits, ranked_by = await self._single_leg_rerank(text, hybrid.bm25, extra)
            else:
                raise ValueError(f"hệ thống không có: {system}")
            return Run(qid=qid, system=system, hits=hits, ranked_by=ranked_by, notes=[*notes, *extra], latency_ms=(time.perf_counter() - start) * 1000)

        for s in systems:
            results.append(await one(s))
        return results
