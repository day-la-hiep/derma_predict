import argparse
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from app.config.settings import settings
from benchmark.common.jsonl import read_jsonl, write_jsonl
from benchmark.retrieval import snapshot_store
from benchmark.retrieval.evaluate.systems import DEPTH, SYSTEMS, Retriever
from benchmark.retrieval.paths import DATA, SETS
from benchmark.retrieval.schema import Query, Run, RunConfig


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return ""


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", default=str(SETS / "queries.jsonl"))
    p.add_argument("--systems", nargs="+", default=SYSTEMS)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    p.add_argument("--limit", type=int, default=0, help="chỉ chạy N query đầu (thử nhanh)")
    p.add_argument("--concurrency", type=int, default=3)
    args = p.parse_args()

    snap = args.snapshot or snapshot_store.latest()
    queries = read_jsonl(Path(args.queries), Query)
    if args.limit:
        queries = queries[: args.limit]
    retriever = Retriever(snapshot_store.load(snap), snap, settings.AGENT_MODEL)

    out = DATA / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    config = RunConfig(
        run_id=args.run_id, snapshot=snap, systems=args.systems, depth=DEPTH, embedding_model=settings.EMBEDDING_MODEL,
        reranker_model=settings.RERANKER_MODEL, llm_model=settings.AGENT_MODEL, date=f"{datetime.now():%Y-%m-%d}", git_commit=_git_commit(),
    )
    (out / "config.json").write_text(config.model_dump_json(indent=1), encoding="utf-8")

    sem = asyncio.Semaphore(args.concurrency)
    results: dict[str, list[Run]] = {}

    async def go(q: Query) -> None:
        async with sem:
            try:
                runs = await retriever.run_all(q.qid, q.text, args.systems)
            except Exception as exc:  # noqa: BLE001  # một query lỗi không làm hỏng cả lượt chạy
                print(f"! {q.qid}: {type(exc).__name__}: {exc}")
                return
            results[q.qid] = runs
            fallback = [r.system for r in runs if r.ranked_by == "fallback"]
            print(f"{q.qid} xong" + (f"  (reranker lỗi: {fallback})" if fallback else ""))

    await asyncio.gather(*(go(q) for q in queries))
    write_jsonl(out / "runs.jsonl", (r for q in queries for r in results.get(q.qid, [])))
    print(f"{len(results)}/{len(queries)} query -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
