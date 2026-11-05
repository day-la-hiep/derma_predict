"""Lưu vào kho tri thức"""
from datetime import UTC, datetime
from typing import Any

from . import StageContext, StageError

BATCH = 64


def _embed_all(ctx: StageContext, chunks: list[dict[str, Any]]) -> tuple[list[list[float]], int, str]:
    embeddings: list[list[float]] = []
    dim, model = 0, ""
    for i in range(0, len(chunks), BATCH):
        part = chunks[i : i + BATCH]
        vecs, dim, model = ctx.require_embedding().embed([c["context_text"] for c in part])
        embeddings += vecs
        ctx.progress(i + len(part), len(chunks) * 2, "tạo vector cho đoạn nội dung")
    return embeddings, dim, model


def run(ctx: StageContext) -> dict:
    files, vectors = ctx.files, ctx.require_vectors()
    # Bước 1: đọc `chunks.jsonl`
    chunks = files.read_jsonl("chunks.jsonl")
    if not chunks:
        raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
    document_id = ctx.document_id
    extra: dict[str, Any] = {
        "document_title": ctx.meta().get("title", document_id),
        "source_bucket": files.bucket,
        "source_pdf": files.key("source.pdf"),
    }
    # Bước 2: tạo embedding cho từng chunk
    ctx.progress(0, len(chunks), "chuẩn bị kho tri thức")
    embeddings, dim, model = _embed_all(ctx, chunks)
    # Bước 3: thay toàn bộ point của tài liệu trong Qdrant
    vectors.ensure_collection(dim)
    vectors.delete_chunks(document_id)  # bỏ các đoạn cũ của tài liệu (đã đổi hoặc không còn)
    for i in range(0, len(chunks), BATCH):
        vectors.upsert_chunks(document_id, chunks[i : i + BATCH], embeddings[i : i + BATCH], extra,
                              language=ctx.profile.indexing.text_language)
        ctx.progress(len(chunks) + min(i + BATCH, len(chunks)), len(chunks) * 2, "lưu vào Qdrant")
    # Bước 4: đếm lại để chắc đã lưu đủ
    stored = vectors.count_chunks(document_id)
    if stored != len(chunks):
        raise StageError(f"Số đoạn đã lưu ({stored}) khác số đoạn cần lưu ({len(chunks)}).")
    # Bước 5: ghi `index.json`
    info = {"collection": vectors.collection, "points": stored, "embedding_model": model, "dimension": dim,
            "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    files.write_json("index.json", info)
    return {"points": stored, "collection": info["collection"], "embedding_model": model, "dimension": dim}
