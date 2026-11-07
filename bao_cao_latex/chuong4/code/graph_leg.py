async def graph_search(
    entities: list[ExtractedEntity],
    limit: int,
    corpus: RetrievalCorpus = DOCUMENT_CORPUS,
) -> list[dict[str, Any]]:
    """Payload chunk theo số cạnh trỏ tới giảm dần; rỗng khi không phải corpus sách, không có thực thể y khoa hoặc chưa có cạnh DOC."""
    if corpus.name != DOCUMENT_CORPUS.name:
        return []
    names = [
        t for e in entities if e.type != "other" for t in (e.text, e.vi) if t
    ]
    chunk_ids = await get_document_graph_service().chunks_for_entities(
        names, limit
    )
    return await get_retrieval_service().fetch(corpus, chunk_ids)

async def chunks_for_entities(self, names: list[str], limit: int = 20) -> list[str]:
    """`chunk_id` mà cạnh DOC của các thực thể trỏ tới, nhiều cạnh nhất trước. Khớp tên chính xác trước, không có mới khớp chứa."""
    names = [n.strip().lower() for n in dict.fromkeys(names) if n and n.strip()]
    if not self.configured or not names:
        return []
    query = """
        MATCH (n) WHERE (n:Entity OR n:DermoTerm) AND {match}
        WITH n LIMIT 10
        MATCH (n)-[r]-()
        WHERE r.source = 'DOC'
        UNWIND coalesce(r.chunk_ids, []) AS chunk_id
        RETURN chunk_id, count(DISTINCT r) AS weight
        ORDER BY weight DESC, chunk_id
        LIMIT $lim
    """
    exact = "(toLower(coalesce(n.name,'')) IN $names OR any(s IN coalesce(n.synonyms, []) WHERE toLower(s) IN $names))"
    contains = "any(q IN $names WHERE toLower(coalesce(n.name,'')) CONTAINS q OR any(s IN coalesce(n.synonyms, []) WHERE toLower(s) CONTAINS q))"
    for match in (exact, contains):
        rows = await self.neo4j.run(_cypher(query.replace("{match}", match)), names=names, lim=limit)
        if rows:
            return [str(r["chunk_id"]) for r in rows]
    return []
