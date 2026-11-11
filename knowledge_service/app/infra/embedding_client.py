"""Embedding dùng chung (OpenRouter)"""
import time

import httpx

from app.config.settings import settings
from app.infra.text_clean import clean_text

_BATCH = 32
# Qwen3-Embedding được huấn luyện với query dạng "Instruct: ...\nQuery: ..." (đoạn văn thì để nguyên)
_QUERY_INSTRUCTION = "Given a Vietnamese or English dermatology question, retrieve relevant textbook passages that answer it"


class EmbeddingClient:
    def _post(self, batch: list[str]) -> list[list[float]]:
        for attempt in range(3):
            try:
                resp = httpx.post(
                    f"{settings.OPENROUTER_BASE_URL}/embeddings",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                    json={"model": settings.EMBEDDING_MODEL, "input": batch, "encoding_format": "float"},
                    timeout=120,
                )
                resp.raise_for_status()
                return [d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"])]
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        raise AssertionError("không tới được đây")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.OPENROUTER_API_KEY:
            raise RuntimeError("Thiếu OPENROUTER_API_KEY để gọi embedding.")
        texts = [clean_text(t) for t in texts]
        vectors = [v for i in range(0, len(texts), _BATCH) for v in self._post(texts[i : i + _BATCH])]
        if vectors and len(vectors[0]) != settings.EMBEDDING_DIM:
            raise RuntimeError(f"{settings.EMBEDDING_MODEL} trả {len(vectors[0])} chiều, khác EMBEDDING_DIM={settings.EMBEDDING_DIM}.")
        return vectors

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        """Trả (vector từng văn bản, số chiều, tên model)."""
        return self._embed(texts), settings.EMBEDDING_DIM, settings.EMBEDDING_MODEL

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"Instruct: {_QUERY_INSTRUCTION}\nQuery: {text}"])[0]
