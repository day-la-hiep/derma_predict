def load_edges(driver: Any) -> None:
    # quan hệ chưa có cạnh nào thì CREATE (nhanh, MERGE trên nút bậc cao của drug_drug rất chậm); đã có thì MERGE để chạy lại không nhân đôi
    fresh = {rel for rel in RELATIONS.values()} - existing_relations(driver)
    buffers: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    totals: dict[str, int] = {}
    with driver.session() as s, (IN_DIR / "edges.csv").open(encoding="utf-8", newline="") as f:

        def flush(key: tuple[str, str, str]) -> None:
            relation, xt, yt = key
            rel = RELATIONS[relation]
            verb = "CREATE" if rel in fresh else "MERGE"
            q = (f"UNWIND $batch AS row MATCH (x:{NODE_LABELS[xt]} {{id: row.x_id}}), (y:{NODE_LABELS[yt]} {{id: row.y_id}}) "
                 f"{verb} (x)-[r:{rel}]->(y) SET r.display_relation = row.display_relation")
            s.run(q, batch=buffers[key]).consume()
            totals[rel] = totals.get(rel, 0) + len(buffers[key])
            buffers[key] = []

        for i, r in enumerate(csv.DictReader(f), 1):
            key = (r["relation"], r["x_type"], r["y_type"])
            buffers.setdefault(key, []).append({"x_id": r["x_id"], "y_id": r["y_id"], "display_relation": r["display_relation"]})
            if len(buffers[key]) >= BATCH_SIZE:
                flush(key)
            if i % 500_000 == 0:
                print(f"  ... {i} dòng cạnh", flush=True)
        for key in list(buffers):
            if buffers[key]:
                flush(key)
    for rel, n in sorted(totals.items()):
        print(f"  [cạnh] {rel}: {n} ({'mới' if rel in fresh else 'upsert'})")
