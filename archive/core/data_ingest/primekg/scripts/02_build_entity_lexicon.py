#!/usr/bin/env python3
"""Từ điển thực thể PrimeKG (bản đầy đủ) cho bước trích graph từ tài liệu: khớp tên trong sách vào id PrimeKG thật.

Input : primekg/input/kg.csv
Output: primekg/output/entity_lexicon.csv (id,name,type,source), duy nhất theo (type, id)
"""
import argparse
import csv
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SOURCE_DIR = Path(__file__).resolve().parents[1]
# Chỉ các loại mà sách lâm sàng nhắc tới; khớp với `pipeline/document_ingest/graph_schema.py::ENTITY_TYPES`.
TYPES = {"disease", "effect/phenotype", "drug", "exposure", "gene/protein"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=SOURCE_DIR / "input" / "kg.csv")
    ap.add_argument("--output", type=Path, default=SOURCE_DIR / "output" / "entity_lexicon.csv")
    args = ap.parse_args()
    if not args.input.exists():
        print(f"[lỗi] không thấy {args.input}")
        return 1
    # id PrimeKG chỉ duy nhất trong từng loại nút nên khoá là (type, id)
    nodes: dict[tuple[str, str], tuple[str, str]] = {}
    with args.input.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for side in ("x", "y"):
                t = r[f"{side}_type"]
                if t in TYPES:
                    nodes[(t, r[f"{side}_id"])] = (r[f"{side}_name"], r[f"{side}_source"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "type", "source"])
        for (t, i), (name, source) in sorted(nodes.items()):
            w.writerow([i, name, t, source])
    print(f"-> {len(nodes)} thực thể -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
