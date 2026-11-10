def extract_triples(chunks: list[DocumentChunk], llm: LLMClient, lexicon: EntityLexicon, schema: GraphSchema, *, document_id: str,
                    allow_new: bool, chunks_per_call: int, limit_topics: int, on_progress: OnProgress,
                    on_log: OnLog) -> tuple[list[DocumentTriple], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Chunks -> (triple máy trích, chủ đề, thông tin chưa xếp vào ô, thống kê); chưa áp override."""
    by_id = {c.chunk_id: c for c in chunks}
    # Bước 1: gom chunk theo mục, LLM phân loại mục là bệnh / thuốc / khác
    topics = collect_topics(chunks)
    classify_topics(llm, topics, by_id, on_progress)
    used = [t for t in topics if t["kind"] in TOPIC_TYPES][: limit_topics or None]  # limit_topics: thử vài mục trước khi chạy cả sách
    on_log(f"{len(topics)} mục, {len(used)} mục bệnh/thuốc được trích")
    # Bước 2: khớp chính xác tên chủ đề vào từ điển
    linker = Linker(lexicon, allow_new, schema)
    for t in used:
        for et in TOPIC_ENTITY_TYPES[t["kind"]]:
            linker.ref(et, t["title"], t["en"], t.get("alt"))
    # Bước 3: LLM điền ô (slot) quan hệ cho từng mục, theo lô chunk, chạy song song
    jobs = [(t, ids) for t in used for ids in split_batches(t, chunks_per_call)]
    results = run_extractions(llm, schema, jobs, by_id, on_progress)
    # Bước 4: giữ mục có evidence nguyên văn trong chunk; khớp thực thể đầu kia
    stats: Counter[str] = Counter()
    unmapped: list[dict[str, Any]] = []
    grounded: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for t, ids, res in results:
        if res.get("error"):
            stats["llm_failed_calls"] += 1
            on_log(f"lỗi trích mục {t['title']!r} ({ids[0]}...): {res['error']}")
        unmapped += [{**u, "topic": t["title"], "chunk_id": ids[0]} for u in res["unmapped"]]
        for it in res["items"]:
            cid = find_grounded_chunk(it, ids, by_id)
            if cid is None:
                stats["evidence_dropped"] += 1
                continue
            grounded.append((t, it, cid))
            slot = schema.slot(it["slot"])
            assert slot is not None  # `extract` chỉ giữ ô có trong schema
            for rel in slot.relations:
                linker.ref(rel.object_type, it["text"], it["en"])
    # Bước 5: LLM chọn nút cho thuật ngữ chưa khớp chính xác
    linker.resolve_pending(llm, on_progress, on_log)
    # Bước 6: dựng triple (gộp trùng)
    triples = merge_triples([tr for t, it, cid in grounded
                             for tr in build_triples(document_id, t, it, cid, by_id[cid].page_start, linker)])
    for t in topics:
        t["links"] = {et: linker.final(et, t["title"], t["en"]).model_dump()
                      for et in TOPIC_ENTITY_TYPES.get(t["kind"], ()) if linker.key(et, t["title"], t["en"]) in linker.refs}
    return triples, topics, unmapped, dict(stats)
