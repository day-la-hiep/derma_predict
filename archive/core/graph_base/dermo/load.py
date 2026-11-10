import argparse
import json
import re
import time
from typing import Any

from graph_base._common import BUILD_DIR, batched, delete_in_chunks, neo4j_driver

IN_FILE = BUILD_DIR / "dermo" / "terms.json"
REL_RE = re.compile(r"^[a-z_]+$")


def load_terms(driver: Any, terms: list[dict[str, Any]]) -> None:
    rows = [{"id": t["id"], "name": t["name"], "def": t["def"], "synonyms": [s["text"] for s in t["synonyms"]],
             "xrefs": t["xrefs"], "alt_ids": t["alt_ids"], "is_obsolete": t["is_obsolete"]} for t in terms]
    q = ("UNWIND $batch AS row MERGE (t:DermoTerm {id: row.id}) "
         "SET t.name = row.name, t.def = row.def, t.synonyms = row.synonyms, t.xrefs = row.xrefs, "
         "t.alt_ids = row.alt_ids, t.is_obsolete = row.is_obsolete")
    with driver.session() as s:
        s.run("CREATE CONSTRAINT dermo_term_id IF NOT EXISTS FOR (t:DermoTerm) REQUIRE t.id IS UNIQUE").consume()
        for batch in batched(rows):
            s.run(q, batch=batch).consume()
    print(f"  [term] {len(rows)}")


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="xoá :DermoTerm cùng mọi cạnh (kể cả nút/cạnh DOC từ sách) rồi nạp lại")
    args = ap.parse_args()
    if not IN_FILE.exists():
        raise SystemExit("Thiếu dữ liệu build; chạy `make kg-build` trước.")
    terms = json.loads(IN_FILE.read_text(encoding="utf-8"))["terms"]
    driver = neo4j_driver()
    t0 = time.time()
    if args.reset:
        print("Xoá :DermoTerm cũ ...")
        delete_in_chunks(driver, "DermoTerm")
    load_terms(driver, terms)
    load_edges(driver, terms)
    driver.close()
    print(f"Xong trong {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
