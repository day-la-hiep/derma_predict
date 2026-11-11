from collections.abc import Callable
from typing import Any

from app.infra.embedding_client import EmbeddingClient

BATCH = 64


def embed_chunks(chunks: list[dict[str, Any]], embedding: EmbeddingClient,
                 on_progress: Callable[[int, int, str], None]) -> tuple[list[list[float]], int, str]:
    """Vector cho từng chunk (theo `context_text`) -> (vectors, số chiều, tên model)."""
    vectors: list[list[float]] = []
    dim, model = 0, ""
    for i in range(0, len(chunks), BATCH):
        part = chunks[i : i + BATCH]
        vecs, dim, model = embedding.embed([c["context_text"] for c in part])
        vectors += vecs
        on_progress(i + len(part), len(chunks), "tạo vector cho đoạn nội dung")
    return vectors, dim, model
