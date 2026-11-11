from benchmark.common.jsonl import read_jsonl
from benchmark.retrieval.paths import DATA
from benchmark.retrieval.schema import ChunkRecord

CORPUS_DIR = DATA / "corpus"


def load(name: str) -> dict[str, ChunkRecord]:
    return {c.chunk_id: c for c in read_jsonl(CORPUS_DIR / f"{name}.jsonl", ChunkRecord)}


def latest() -> str:
    files = sorted(CORPUS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(
            "Chưa có snapshot: chạy `python -m benchmark.retrieval.prepare.corpus` trước."
        )
    return files[-1].stem
