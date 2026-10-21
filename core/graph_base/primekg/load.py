import argparse
import csv
import time
from typing import Any

from graph_base._common import BATCH_SIZE, BUILD_DIR, batched, delete_in_chunks, neo4j_driver
from graph_base.primekg.schema import NODE_LABELS, RELATIONS

IN_DIR = BUILD_DIR / "primekg"


def prepare(driver: Any) -> None:
    with driver.session() as s:
        # ràng buộc cũ ép `Entity.id` duy nhất toàn cục, trong khi id PrimeKG chỉ duy nhất theo loại (HPO 972 và NCBI 972 trùng số)
        s.run("DROP CONSTRAINT entity_id IF EXISTS").consume()
        for label in NODE_LABELS.values():
            s.run(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE").consume()
        s.run("CREATE INDEX entity_id_lookup IF NOT EXISTS FOR (n:Entity) ON (n.id)").consume()


def load_nodes(driver: Any) -> None:
    by_type: dict[str, list[dict[str, str]]] = {}
    with (IN_DIR / "nodes.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            by_type.setdefault(r["type"], []).append(r)
    with driver.session() as s:
        for type_, rows in by_type.items():
            label = NODE_LABELS[type_]  # label lấy từ hằng số, không ghép từ dữ liệu
            q = f"UNWIND $batch AS row MERGE (n:{label} {{id: row.id}}) SET n:Entity, n.name = row.name, n.type = row.type, n.source = row.source"
            for batch in batched(rows):
                s.run(q, batch=batch).consume()
            print(f"  [nút] {type_} ({label}): {len(rows)}")


def existing_relations(driver: Any) -> set[str]:
    with driver.session() as s:
        return {rel for rel in RELATIONS.values()
                if s.run(f"MATCH ()-[r:{rel}]->() WHERE r.document_id IS NULL RETURN r LIMIT 1").single()}


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="xoá :Entity cùng mọi cạnh (kể cả cạnh DOC từ sách) rồi nạp lại")
    args = ap.parse_args()
    if not (IN_DIR / "edges.csv").exists():
        raise SystemExit("Thiếu dữ liệu build; chạy `make kg-build` trước.")
    driver = neo4j_driver()
    t0 = time.time()
    if args.reset:
        print("Xoá :Entity cũ ...")
        delete_in_chunks(driver, "Entity")
    prepare(driver)
    print("Nạp nút ...")
    load_nodes(driver)
    print("Nạp cạnh ...")
    load_edges(driver)
    driver.close()
    print(f"Xong trong {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
