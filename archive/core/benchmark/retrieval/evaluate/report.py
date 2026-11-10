import argparse
from collections import defaultdict
from pathlib import Path

from benchmark.common.jsonl import read_jsonl
from benchmark.common.stats import bootstrap_ci, paired_diff_ci
from benchmark.retrieval import snapshot_store
from benchmark.retrieval.evaluate.metrics import hit_at_k, mrr_at_k, recall_at_k
from benchmark.retrieval.evaluate.systems import DESCRIPTIONS, SYSTEMS
from benchmark.retrieval.paths import DATA, SETS
from benchmark.retrieval.schema import Qrel, Query, Run, RunConfig

KS = (1, 3, 5, 10)
PAIRS = [("hybrid", "rrf"), ("hybrid", "semantic"), ("hybrid", "bm25_expand"), ("hybrid", "hybrid_no_expand"), ("hybrid", "semantic_rerank"), ("rrf", "bm25")]


def score(runs: list[Run], relevant: dict[str, set[str]]) -> dict[str, dict[str, dict[str, float]]]:
    """{hệ thống: {chỉ số: {qid: giá trị}}}, chỉ tính query có nhãn."""
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for r in runs:
        if r.qid not in relevant:
            continue
        ranked = [h.chunk_id for h in r.hits]
        for k in KS:
            out[r.system][f"hit@{k}"][r.qid] = hit_at_k(ranked, relevant[r.qid], k)
        out[r.system]["recall@10"][r.qid] = recall_at_k(ranked, relevant[r.qid], 10)
        out[r.system]["mrr@10"][r.qid] = mrr_at_k(ranked, relevant[r.qid], 10)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--qrels", default=str(SETS / "qrels.jsonl"))
    p.add_argument("--queries", default=str(SETS / "queries.jsonl"))
    args = p.parse_args()
    run_dir = DATA / "runs" / args.run_id
    runs = read_jsonl(run_dir / "runs.jsonl", Run)
    config = RunConfig.model_validate_json((run_dir / "config.json").read_text(encoding="utf-8"))
    chunks = snapshot_store.load(config.snapshot)

    relevant: dict[str, set[str]] = defaultdict(set)
    for q in read_jsonl(Path(args.qrels), Qrel):
        if q.relevance >= 1:
            relevant[q.qid].add(q.chunk_id)
    scores = score(runs, relevant)
    qids = sorted({r.qid for r in runs} & set(relevant))
    book = {q: chunks[next(iter(relevant[q]))].document_title for q in qids if next(iter(relevant[q])) in chunks}
    fallback = defaultdict(int)
    for r in runs:
        if r.ranked_by == "fallback":
            fallback[r.system] += 1

    qset = {q.qid: q.set for q in read_jsonl(Path(args.queries), Query)}
    metrics = [f"hit@{k}" for k in KS] + ["recall@10", "mrr@10"]
    lines = [f"# Retrieval theo chunk nguồn — run `{args.run_id}`", "", f"n = {len(qids)} query có nhãn, snapshot `{config.snapshot}`.",
             "Nhãn chỉ gồm các chunk RAGAS nêu nên hit@k, recall@k là cận dưới (chưa qua pooling + chấm). recall@10 = tỉ lệ chunk đúng nằm trong top-10.", "",
             "| Hệ thống | Mô tả | " + " | ".join(metrics) + " |", "|---|---|" + "---|" * len(metrics)]
    for s in (s for s in SYSTEMS if s in scores):
        cells = []
        for m in metrics:
            mean, lo, hi = bootstrap_ci([scores[s][m][q] for q in qids])
            cells.append(f"{mean:.2f} [{lo:.2f}, {hi:.2f}]")
        lines.append(f"| {s} | {DESCRIPTIONS[s]} | " + " | ".join(cells) + " |")

    lines += ["", "## So sánh cặp (hiệu hit@5, CI 95%)", "", "| A − B | hiệu | CI |", "|---|---|---|"]
    for a, b in PAIRS:
        if a in scores and b in scores:
            mean, lo, hi = paired_diff_ci([scores[a]["hit@5"][q] for q in qids], [scores[b]["hit@5"][q] for q in qids])
            lines.append(f"| {a} − {b} | {mean:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")

    sets = sorted({qset.get(q, "?") for q in qids})
    lines += ["", "## Theo bộ câu hỏi (hit@5 / recall@10)", "", "| Hệ thống | " + " | ".join(f"{t} (n={sum(qset.get(q) == t for q in qids)})" for t in sets) + " |", "|---|" + "---|" * len(sets)]
    for s in (s for s in SYSTEMS if s in scores):
        cells = []
        for t in sets:
            qs = [q for q in qids if qset.get(q, "?") == t]
            cells.append(f"{sum(scores[s]['hit@5'][q] for q in qs) / max(1, len(qs)):.2f} / {sum(scores[s]['recall@10'][q] for q in qs) / max(1, len(qs)):.2f}")
        lines.append(f"| {s} | " + " | ".join(cells) + " |")

    titles = sorted(set(book.values()))
    lines += ["", "## hit@5 theo sách của chunk nguồn", "", "| Hệ thống | " + " | ".join(f"{t[:28]} (n={sum(b == t for b in book.values())})" for t in titles) + " |",
              "|---|" + "---|" * len(titles)]
    for s in (s for s in SYSTEMS if s in scores):
        cells = [f"{sum(scores[s]['hit@5'][q] for q in qids if book.get(q) == t) / max(1, sum(book.get(q) == t for q in qids)):.2f}" for t in titles]
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    if fallback:
        lines += ["", f"Cảnh báo: reranker lỗi, rơi về thứ tự RRF/nhánh: {dict(fallback)} — số liệu hệ thống rerank bị lẫn."]
    text = "\n".join(lines)
    (run_dir / "report.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
