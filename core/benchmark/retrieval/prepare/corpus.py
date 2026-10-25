import asyncio
import hashlib
import json
import sys
from collections import Counter
from datetime import date

from app.api.deps import get_knowledge_base_service
from app.config.settings import settings
from benchmark.common.jsonl import write_jsonl
from benchmark.retrieval.schema import ChunkRecord
from benchmark.retrieval.snapshot_store import CORPUS_DIR

def _to_record(payload: dict) -> ChunkRecord:
    path = payload.get("toc_path")
    text = str(payload.get("text", ""))
    return ChunkRecord(
        chunk_id=str(payload["chunk_id"]),
        content_hash=hashlib.sha1(text.encode("utf-8")).hexdigest(),
        document_id=str(payload.get("document_id") or ""),
        document_title=str(
            payload.get("document_title") or payload.get("document_id") or "?"
        ),
        toc_path=[str(p) for p in path if p]
        if isinstance(path, list)
        else ([str(path)] if path else []),
        text=text,
        context_text=str(payload.get("context_text") or ""),
    )


async def snapshot(name: str | None = None) -> str:
    records = [
        r.payload
        for r in await get_knowledge_base_service().all_document_chunks()
        if r.payload and r.payload.get("chunk_id")
    ]
    # giữ một bản theo chunk_id
    unique = {c.chunk_id: c for c in (_to_record(p) for p in records)}
    chunks = sorted(unique.values(), key=lambda c: c.chunk_id)
    name = name or f"{date.today():%Y%m%d}-{len(chunks)}"
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(CORPUS_DIR / f"{name}.jsonl", chunks)
    manifest = {
        "name": name,
        "date": f"{date.today()}",
        "chunks": len(chunks),
        "duplicates_dropped": len(records) - len(chunks),
        "per_document": dict(Counter(c.document_title for c in chunks)),
        "collection": settings.QDRANT_DOCUMENT_COLLECTION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "reranker_model": settings.RERANKER_MODEL,
    }
    (CORPUS_DIR / f"{name}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return name


if __name__ == "__main__":
    print(asyncio.run(snapshot(sys.argv[1] if len(sys.argv) > 1 else None)))
