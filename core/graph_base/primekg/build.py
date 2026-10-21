import csv
import json
import time
from collections import Counter

from graph_base._common import BUILD_DIR, RAW_DIR
from graph_base.primekg.download import DEST as KG_CSV
from graph_base.primekg.schema import NODE_LABELS, RELATIONS

OUT_DIR = BUILD_DIR / "primekg"
EDGE_HEADER = ["relation", "display_relation", "x_type", "x_id", "y_type", "y_id"]


def main() -> None:
    if not KG_CSV.exists():
        raise SystemExit(f"Thiếu {KG_CSV}; chạy `make kg-download` trước ({RAW_DIR}).")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    nodes: dict[tuple[str, str], tuple[str, str]] = {}  # (type, id) -> (name, source); id chỉ duy nhất theo loại
    seen: set[int] = set()
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    skipped: Counter[str] = Counter()
    with KG_CSV.open(encoding="utf-8", newline="") as f, (OUT_DIR / "edges.csv").open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(EDGE_HEADER)
        for r in csv.DictReader(f):
            rel, xt, yt, xi, yi = r["relation"], r["x_type"], r["y_type"], r["x_id"], r["y_id"]
            if not (xt and yt and xi and yi):
                skipped["dòng thiếu type/id"] += 1
                continue
            if rel not in RELATIONS or xt not in NODE_LABELS or yt not in NODE_LABELS:
                skipped["ngoài phạm vi"] += 1
                continue
            key = hash((rel, xt, xi, yt, yi))
            if key in seen:
                skipped["cạnh trùng"] += 1
                continue
            seen.add(key)
            nodes.setdefault((xt, xi), (r["x_name"], r["x_source"]))
            nodes.setdefault((yt, yi), (r["y_name"], r["y_source"]))
            w.writerow([rel, r["display_relation"], xt, xi, yt, yi])
            edge_counts[(rel, xt, yt)] += 1
    with (OUT_DIR / "nodes.csv").open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(["id", "name", "type", "source"])
        for (t, i), (name, source) in sorted(nodes.items()):
            w.writerow([i, name, t, source])
    summary = {
        "nodes": dict(Counter(t for t, _ in nodes)),
        "edges": [{"relation": k[0], "x_type": k[1], "y_type": k[2], "count": v} for k, v in sorted(edge_counts.items())],
        "skipped": dict(skipped),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(nodes)} nút, {sum(edge_counts.values())} cạnh, bỏ {dict(skipped)} ({time.time() - t0:.0f}s) -> {OUT_DIR}")


if __name__ == "__main__":
    main()
