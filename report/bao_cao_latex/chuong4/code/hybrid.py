async def run_hybrid(
    query: str,
    *,
    corpus: RetrievalCorpus = DOCUMENT_CORPUS,
    filter: RetrievalFilter | None = None,
    semantic_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    bm25_fn: Callable[[str, int], Awaitable[Payloads]] | None = None,
    entities_fn: Callable[[str], Awaitable[list[ExtractedEntity]]] | None = None,
    graph_fn: Callable[[list[ExtractedEntity], int], Awaitable[Payloads]] | None = None,
    rerank_fn: Callable[[str, list[str]], Awaitable[list[float] | None]] | None = None,
) -> HybridResult:
    notes: list[str] = []
    semantic_fn = semantic_fn or (lambda q, n: semantic_leg(q, n, corpus, filter))
    bm25_fn = bm25_fn or (lambda q, n: bm25_search(q, n, corpus, filter))
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
