import json
import sys

from graph_base._common import BUILD_DIR, neo4j_driver
from graph_base.primekg.schema import NODE_LABELS, RELATIONS


def check_primekg(driver, errors: list[str]) -> None:
    summary = json.loads((BUILD_DIR / "primekg" / "summary.json").read_text(encoding="utf-8"))
    with driver.session() as s:
        for type_, expected in summary["nodes"].items():
            got = s.run(f"MATCH (n:{NODE_LABELS[type_]}) WHERE n.added_by IS NULL RETURN count(n) AS c").single()["c"]
            print(f"  nút {type_}: {got}/{expected}")
            if got != expected:
                errors.append(f"nút {type_}: {got} != {expected}")
        for relation, rel in RELATIONS.items():
            # đếm theo cặp (type đầu, type đuôi): vừa so số lượng, vừa lộ cạnh nối nhầm loại
            rows = s.run(f"MATCH (a)-[r:{rel}]->(b) WHERE r.document_id IS NULL RETURN a.type AS x, b.type AS y, count(*) AS c")
            got = {(r["x"], r["y"]): r["c"] for r in rows}
            expected = {(e["x_type"], e["y_type"]): e["count"] for e in summary["edges"] if e["relation"] == relation}
            print(f"  cạnh {rel}: {sum(got.values())}/{sum(expected.values())}")
            if got != expected:
                errors.append(f"cạnh {rel}: {got} != {expected}")


def check_dermo(driver, errors: list[str]) -> None:
    summary = json.loads((BUILD_DIR / "dermo" / "summary.json").read_text(encoding="utf-8"))
    with driver.session() as s:
        def one(q: str) -> int:
            return s.run(q).single()["c"]

        checks = [("term", one("MATCH (t:DermoTerm) WHERE t.added_by IS NULL RETURN count(t) AS c"), summary["terms"]),
                  ("IS_A", one("MATCH (:DermoTerm)-[r:IS_A]->(:DermoTerm) RETURN count(r) AS c"), summary["is_a"] - summary["dangling_refs"]),
                  *[(rel.upper(), one(f"MATCH (:DermoTerm)-[r:{rel.upper()}]->(:DermoTerm) WHERE r.document_id IS NULL RETURN count(r) AS c"), n)
                    for rel, n in summary["relationships"].items()]]
        for name, got, expected in checks:
            print(f"  DermO {name}: {got}/{expected}")
            if got != expected:
                errors.append(f"DermO {name}: {got} != {expected}")
        tagged = one("MATCH (t:DermoTerm) WHERE any(x IN t.synonyms WHERE x CONTAINS '<new synonym>') RETURN count(t) AS c")
        print(f"  DermO synonym còn tag: {tagged}")
        if tagged:
            errors.append(f"{tagged} term còn tag <new synonym>")


def main() -> None:
    driver = neo4j_driver()
    errors: list[str] = []
    print("PrimeKG:")
    check_primekg(driver, errors)
    print("DermO:")
    check_dermo(driver, errors)
    driver.close()
    if errors:
        print("\nLỖI:\n" + "\n".join(f"- {e}" for e in errors))
        sys.exit(1)
    print("\nOK: Neo4j khớp dữ liệu build.")


if __name__ == "__main__":
    main()
