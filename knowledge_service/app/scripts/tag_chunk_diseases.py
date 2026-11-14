import argparse
import asyncio
import csv
import logging
import random
import re
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

from app.config.settings import settings
from app.infra.neo4j_client import Neo4jClient

logger = logging.getLogger("tag_chunk_diseases")

FIELDS = ("primary_disease_ids", "mentioned_disease_ids")
BATCH = 256
MIN_NAME_CHARS = 4
MAX_NGRAM = 6
# Node bệnh PrimeKG mang tên nhóm (khớp ở rất nhiều chunk nhưng không chỉ một bệnh cụ thể); lọc theo tần suất thì loại nhầm bệnh thật như psoriasis.
GENERIC_NAMES = frozenset({
    "disease", "syndrome", "infection", "injury", "cancer", "carcinoma", "sarcoma", "neoplasm", "tumor", "dermatitis", "keratosis",
    "hyperplasia", "inflammation", "allergy", "immunodeficiency", "skin disease",
})
_NUMBERING = re.compile(r"^\s*(chương|chapter|phần|part)?\s*[\dIVXivx]+([.\-]\d+)*[.:)]?\s+", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_DISEASE_NAMES = "MATCH (d:Entity {type: 'disease'}) RETURN d.id AS id, toLower(d.name) AS name"


def clean_heading(heading: str) -> str:
    return _NUMBERING.sub("", heading).strip().lower()


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def find_names(text: str, names: dict[str, list[str]]) -> set[str]:
    """Các tên bệnh có trong text, khớp cụm dài nhất từ trái sang ("contact dermatitis" không tính thêm "dermatitis")."""
    words = tokenize(text)
    found: set[str] = set()
    i = 0
    while i < len(words):
        for n in range(min(MAX_NGRAM, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + n])
            if phrase in names:
                found.add(phrase)
                i += n
                break
        else:
            i += 1
    return found - GENERIC_NAMES


def match_heading(toc_path: list[str], names: dict[str, list[str]]) -> list[str]:
    """Duyệt tiêu đề từ lá lên gốc, tiêu đề đầu tiên trùng chính xác tên bệnh (bỏ số mục, bỏ 's' cuối) thì lấy id của nó."""
    for heading in reversed(toc_path or []):
        cleaned = clean_heading(heading)
        for variant in (cleaned, cleaned[:-1] if cleaned.endswith("s") else ""):
            if variant and variant in names and variant not in GENERIC_NAMES:
                return names[variant]
    return []


def build_tags(chunks: list[dict[str, Any]], names: dict[str, list[str]]) -> dict[str, dict[str, list[str]]]:
    mentions = {c["chunk_id"]: find_names(str(c.get("text") or ""), names) for c in chunks}
    tags: dict[str, dict[str, list[str]]] = {}
    for c in chunks:
        primary = match_heading(c.get("toc_path") or [], names)
        mentioned = sorted({i for n in mentions[c["chunk_id"]] for i in names[n]} - set(primary))
        tags[c["chunk_id"]] = {"primary_disease_ids": primary, "mentioned_disease_ids": mentioned}
    return tags


async def load_disease_names() -> dict[str, list[str]]:
    neo4j = Neo4jClient.from_settings()
    try:
        rows = await neo4j.run(_DISEASE_NAMES)
    finally:
        await neo4j.close()
    names: dict[str, list[str]] = {}
    for r in rows:
        name = " ".join(tokenize(r["name"] or ""))
        if len(name) >= MIN_NAME_CHARS:
            names.setdefault(name, []).append(f"disease:{r['id']}")
    return names


def scroll_chunks(client: QdrantClient, collection: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        points, offset = client.scroll(collection, limit=BATCH, offset=offset, with_payload=["chunk_id", "toc_path", "text"], with_vectors=False)
        chunks += [{"point_id": p.id, **(p.payload or {})} for p in points]
        if offset is None:
            return chunks


def write_sample(chunks: list[dict[str, Any]], tags: dict[str, dict[str, list[str]]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["chunk_id", "toc_path", "primary_disease_ids", "mentioned_disease_ids", "text"])
        for c in random.Random(0).sample(chunks, min(50, len(chunks))):
            t = tags[c["chunk_id"]]
            writer.writerow([c["chunk_id"], " > ".join(c.get("toc_path") or []), " ".join(t["primary_disease_ids"]),
                             " ".join(t["mentioned_disease_ids"][:10]), str(c.get("text") or "")[:300]])


def main() -> None:
    parser = argparse.ArgumentParser(description="Gắn primary/mentioned_disease_ids cho chunk sách trong Qdrant (không embed lại).")
    parser.add_argument("--dry-run", action="store_true", help="chỉ in thống kê và file mẫu, không ghi Qdrant")
    parser.add_argument("--sample", default="../tmp/tag_sample.csv")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    collection = settings.QDRANT_DOCUMENT_COLLECTION
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    names = asyncio.run(load_disease_names())
    chunks = [c for c in scroll_chunks(client, collection) if c.get("chunk_id")]
    tags = build_tags(chunks, names)
    total = max(len(chunks), 1)
    with_primary = sum(1 for t in tags.values() if t["primary_disease_ids"])
    with_mentioned = sum(1 for t in tags.values() if t["mentioned_disease_ids"])
    none = sum(1 for t in tags.values() if not t["primary_disease_ids"] and not t["mentioned_disease_ids"])
    logger.info("%s: %d chunk, %d tên bệnh | có primary %.1f%% · có mentioned %.1f%% · không có gì %.1f%%",
                collection, len(chunks), len(names), 100 * with_primary / total, 100 * with_mentioned / total, 100 * none / total)
    write_sample(chunks, tags, Path(args.sample))
    logger.info("mẫu 50 chunk: %s", args.sample)
    if args.dry_run:
        return
    for c in chunks:
        client.set_payload(collection, payload=tags[c["chunk_id"]], points=[c["point_id"]], wait=False)
    for field in FIELDS:
        client.create_payload_index(collection, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
    logger.info("đã ghi %d chunk và tạo index %s", len(chunks), ", ".join(FIELDS))


if __name__ == "__main__":
    main()
