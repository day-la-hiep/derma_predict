def run_graph_index(self, run: StageRunState) -> dict[str, Any]:
    if self._graph is None or not self._graph.configured:
        raise StageError("Chưa cấu hình đồ thị tri thức (Neo4j).")
    files, graph, lexicon = run.files, self._graph, self._get_lexicon()
    schema = self._get_schema(run.stage_id)
    # triple đã duyệt (status ok) + trang in của chunk để ghi nguồn
    ok = [t for t in (DocumentTriple.model_validate(x) for x in files.read_jsonl("triples.jsonl")) if t.status == "ok"]
    if not ok:
        raise StageError("Chưa có quan hệ nào đã khớp đủ hai đầu để lưu — hãy duyệt bước Trích quan hệ trước.")
    printed = {c["chunk_id"]: c["page_printed_start"] for c in files.read_jsonl("chunks.jsonl")}  # chỉ cần 2 field: không dựng cả DocumentChunk
    run.progress(0, 3, "kiểm tra nút trong đồ thị")
    existing = graph.existing_nodes(step6_graph_index.get_primekg_pairs(ok))
    nodes, edges, skipped, merged = step6_graph_index.build_graph_payload(
        ok, printed, self._repo.meta(run.document_id).get("title", run.document_id), schema, lexicon, existing,
    )
    run.progress(1, 3, "ghi vào Neo4j")
    graph.replace_document(run.document_id, nodes, edges)
    run.progress(2, 3, "đếm lại cạnh đã lưu")
    stored = graph.count_edges(run.document_id)
    if stored != len(edges):
        raise StageError(f"Số quan hệ đã lưu ({stored}) khác số cần lưu ({len(edges)}) — kiểm tra nút DermO/PrimeKG có trong Neo4j "
                         "(thiếu nút thì cạnh không được tạo).")
    summary = step6_graph_index.summarize_graph_payload(nodes, edges, skipped, merged, stored)
    info = {k: summary[k] for k in ("edges", "nodes_added", "by_relation", "new_entities")}
    files.write_json("graph_index.json", {**info, "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")})
    return summary
