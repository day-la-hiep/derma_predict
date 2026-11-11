def load_edges(driver: Any, terms: list[dict[str, Any]]) -> None:
    # (loại cạnh OBO, từ, đến); `is_a` thành IS_A, còn lại giữ tên quan hệ gốc (viết hoa) và chiều gốc
    by_type: dict[str, list[dict[str, str]]] = {"IS_A": []}
    for t in terms:
        by_type["IS_A"] += [{"x": t["id"], "y": p} for p in t["is_a"]]
        for r in t["relationships"]:
            if not REL_RE.match(r["type"]):
                raise SystemExit(f"loại quan hệ lạ trong OBO: {r['type']!r}")  # type ghép thẳng vào Cypher nên phải chặn
            by_type.setdefault(r["type"].upper(), []).append({"x": t["id"], "y": r["target"]})
    with driver.session() as s:
        for rel, rows in by_type.items():
            q = f"UNWIND $batch AS row MATCH (x:DermoTerm {{id: row.x}}), (y:DermoTerm {{id: row.y}}) MERGE (x)-[:{rel}]->(y)"
            for batch in batched(rows):
                s.run(q, batch=batch).consume()
            print(f"  [cạnh] {rel}: {len(rows)}")
