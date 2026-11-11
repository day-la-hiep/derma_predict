import json
import re
from typing import Any

from graph_base._common import BUILD_DIR
from graph_base.dermo.download import DEST as OBO

OUT_DIR = BUILD_DIR / "dermo"
DEF_RE = re.compile(r'^"(.*)"\s*\[')
SYN_RE = re.compile(r'^"(.*)"\s+([A-Z]+)\s*\[')
NEW_SYN_TAG = "<new synonym>"  # nhãn biên tập của tác giả dính vào đầu synonym mới, không phải một phần của tên


def new_term() -> dict[str, Any]:
    return {"id": "", "name": "", "def": None, "synonyms": [], "xrefs": [], "alt_ids": [], "is_a": [],
            "relationships": [], "is_obsolete": False}


def parse(lines: list[str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    header: dict[str, str] = {}
    terms: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    in_term = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("["):
            in_term = line == "[Term]"
            cur = new_term() if in_term else None
            if cur is not None:
                terms.append(cur)
            continue
        if ":" not in line:
            continue
        tag, _, value = line.partition(":")
        value = value.strip()
        if cur is None:
            if not in_term and not terms:
                header[tag] = value
            continue
        if tag == "id":
            cur["id"] = value
        elif tag == "name":
            cur["name"] = value
        elif tag == "def" and (m := DEF_RE.match(value)):
            cur["def"] = m.group(1)
        elif tag == "synonym" and (m := SYN_RE.match(value)):
            text = m.group(1).removeprefix(NEW_SYN_TAG).strip()
            if text:
                cur["synonyms"].append({"text": text, "scope": m.group(2)})
        elif tag == "xref":
            cur["xrefs"].append(value.split()[0])
        elif tag == "alt_id":
            cur["alt_ids"].append(value)
        elif tag == "is_a":
            cur["is_a"].append(value.split()[0])
        elif tag == "relationship":
            rel, target = value.split()[:2]
            cur["relationships"].append({"type": rel, "target": target})
        elif tag == "is_obsolete":
            cur["is_obsolete"] = value == "true"
    return header, terms


def main() -> None:
    if not OBO.exists():
        raise SystemExit("Thiếu dermatology.obo; chạy `make kg-download` trước.")
    header, terms = parse(OBO.read_text(encoding="utf-8").splitlines(keepends=True))
    ids = [t["id"] for t in terms]
    if len(ids) != len(set(ids)):
        raise SystemExit("id term trùng trong OBO")
    known = set(ids)
    dangling = sum(1 for t in terms for p in t["is_a"] if p not in known) + \
        sum(1 for t in terms for r in t["relationships"] if r["target"] not in known)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "terms.json").write_text(
        json.dumps({"metadata": header, "terms": terms}, ensure_ascii=False, indent=1), encoding="utf-8")
    rels: dict[str, int] = {}
    for t in terms:
        for r in t["relationships"]:
            rels[r["type"]] = rels.get(r["type"], 0) + 1
    summary = {"terms": len(terms), "is_a": sum(len(t["is_a"]) for t in terms), "relationships": rels,
               "with_def": sum(1 for t in terms if t["def"]), "dangling_refs": dangling,
               "version": header.get("format-version"), "date": header.get("date")}
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{summary} -> {OUT_DIR}")


if __name__ == "__main__":
    main()
