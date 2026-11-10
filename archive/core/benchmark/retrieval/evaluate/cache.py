import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from benchmark.retrieval.paths import DATA


def digest(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


class Cache:
    """Embedding, rerank và LLM đều tốn tiền / không tất định: lưu lại để chạy lại ra đúng kết quả cũ."""

    def __init__(self, path: Path | None = None) -> None:
        path = path or DATA / "cache.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def get(self, key: str) -> Any | None:
        row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: Any) -> None:
        self._db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        self._db.commit()
