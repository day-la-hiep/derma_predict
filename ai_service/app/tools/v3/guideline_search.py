import asyncio
from typing import Any

from app.config.settings import settings
from app.deps import get_knowledge_client
from app.state.v3.facts import Fact
from app.tools.hybrid_retrieval.corpus import Corpus
from app.tools.hybrid_retrieval.fusion import book_result
from app.tools.hybrid_retrieval.pipeline import run_hybrid

SYMPTOM_POOL = 20
DISEASE_TOP = 4
MENTIONED_WEIGHT = 0.3
RRF_K = 60
# shortcut: chỉ 2 aspect đầu chạy ở khối 2; "warning signs" / "management" để khối kết luận gọi khi cần.
ASPECTS = ("diagnosis", "differential diagnosis")

# `book_result` bỏ khoá lạ: giữ id bệnh để gom điểm theo bệnh.
GUIDELINE_CORPUS = Corpus(
    name="document", id_key="chunk_id",
    to_result=lambda p: {**book_result(p), "primary_disease_ids": p.get("primary_disease_ids") or [], "mentioned_disease_ids": p.get("mentioned_disease_ids") or []},
)


async def _no_entities(_: str) -> list[Any]:
    # Query đã ghép từ tên chuẩn tiếng Anh của fact, không cần thêm lượt LLM trích thực thể để mở rộng BM25.
    return []


async def _no_rerank(_: str, __: list[str]) -> list[float] | None:
    return None


def build_symptom_query(facts: list[Fact]) -> str:
    present = [f for f in facts if f.assertion == "present" and f.source != "history"]
    names = list(dict.fromkeys(f.node_name or f.text_en for f in present if f.node_name or f.text_en))
    raw = [f.text for f in present if not (f.node_name or f.text_en)][:4]
    return " ".join([*names, *raw])


def aggregate_by_disease(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Điểm RRF theo thứ hạng chunk, cộng đủ cho bệnh chính của chunk, ×0.3 cho bệnh chỉ được nhắc tới."""
    scores: dict[str, float] = {}
    why: dict[str, list[tuple[float, str]]] = {}
    for rank, chunk in enumerate(chunks, 1):
        base = 1.0 / (RRF_K + rank)
        weighted = [(d, base) for d in chunk.get("primary_disease_ids") or []]
        weighted += [(d, base * MENTIONED_WEIGHT) for d in chunk.get("mentioned_disease_ids") or []]
        for disease_id, value in weighted:
            # tổng; đổi sang max nếu thấy bệnh có nhiều chunk thắng nhờ số lượng
            scores[disease_id] = scores.get(disease_id, 0.0) + value
            why.setdefault(disease_id, []).append((value, str(chunk.get("chunk_id"))))
    return [
        {"disease_id": d, "name": d, "score": round(s, 5), "why": [c for _, c in sorted(why[d], reverse=True)[:2]]}
        for d, s in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]


async def search_by_symptom(facts: list[Fact]) -> list[dict[str, Any]]:
    query = build_symptom_query(facts)
    if not query:
        return []
    result = await run_hybrid(query, corpus=GUIDELINE_CORPUS, entities_fn=_no_entities, rerank_fn=_no_rerank)
    return aggregate_by_disease(result.candidates[:SYMPTOM_POOL])


async def search_by_disease(disease_id: str, name: str) -> list[dict[str, Any]]:
    """Đoạn sách về một bệnh, lọc payload theo `AGENT_GUIDELINE_FILTER_FIELD`, rerank; mỗi chunk gắn `disease_id` để khối 3 biết thuộc bệnh nào."""
    kc = get_knowledge_client()
    eq = {settings.AGENT_GUIDELINE_FILTER_FIELD: disease_id}

    async def one(aspect: str) -> list[dict[str, Any]]:
        result = await run_hybrid(
            f"{name} {aspect}", corpus=GUIDELINE_CORPUS, entities_fn=_no_entities,
            semantic_fn=lambda q, n: kc.search_semantic(q, n, eq=eq), bm25_fn=lambda q, n: kc.search_bm25(q, n, eq=eq),
            graph_fn=lambda _e, _n: asyncio.sleep(0, []),
        )
        return result.ranked[:DISEASE_TOP]

    seen: set[str] = set()
    chunks: list[dict[str, Any]] = []
    for ranked in await asyncio.gather(*(one(a) for a in ASPECTS)):
        for c in ranked:
            if c["_id"] not in seen:
                seen.add(c["_id"])
                chunks.append({"chunk_id": c["_id"], "disease_id": disease_id, "text": c.get("text", ""), "section": c.get("section", ""),
                               "pages": c.get("pages", ""), "title": c.get("title", ""), "score": c.get("score")})
    return chunks
