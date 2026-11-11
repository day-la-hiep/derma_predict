import hashlib
import json
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

CORE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE_DIR))

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"
BUILD_DIR = DATA_DIR / "build"
BATCH_SIZE = 5000

T = TypeVar("T")


def batched(rows: list[T], size: int = BATCH_SIZE) -> Iterator[list[T]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def file_digest(path: Path) -> dict[str, str]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            md5.update(chunk)
            sha.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def download(url: str, dest: Path, *, md5: str | None = None, force: bool = False) -> Path:
    """Tải về `dest`; bỏ qua nếu đã có (và đúng md5 khi nguồn công bố md5). Ghi `<dest>.meta.json`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        if md5 is None or file_digest(dest)["md5"] == md5:
            print(f"đã có {dest} -> bỏ qua (dùng --force để tải lại)")
            return dest
        print(f"{dest} sai md5 -> tải lại")
    part = dest.with_suffix(dest.suffix + ".part")
    md5_h, sha_h, size, t0 = hashlib.md5(), hashlib.sha256(), 0, time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "derma-graph-base/1.0"})  # urllib mặc định bị Dataverse chặn (403)
    with urllib.request.urlopen(req) as resp, part.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            md5_h.update(chunk)
            sha_h.update(chunk)
            size += len(chunk)
            if size % (50 << 20) < (1 << 20):
                print(f"  {size / 1e6:.0f} MB ...", flush=True)
    if md5 is not None and md5_h.hexdigest() != md5:
        part.unlink()
        raise RuntimeError(f"md5 sai: {md5_h.hexdigest()} (cần {md5})")
    part.replace(dest)
    meta = {"url": url, "bytes": size, "md5": md5_h.hexdigest(), "sha256": sha_h.hexdigest(),
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    dest.with_suffix(dest.suffix + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"-> {dest} ({size / 1e6:.1f} MB, {time.time() - t0:.0f}s)")
    return dest


def neo4j_driver() -> Any:
    from neo4j import GraphDatabase

    from app.config.settings import settings

    print(f"Kết nối Neo4j: {settings.NEO4J_URL}")
    driver = GraphDatabase.driver(settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    driver.verify_connectivity()
    return driver


def delete_in_chunks(driver: Any, label: str) -> None:
    # xoá cạnh trước, theo đợt nhỏ: DETACH DELETE một nút thuốc có hàng trăm nghìn cạnh DRUG_DRUG làm hết bộ nhớ giao dịch của Neo4j
    # label lấy từ hằng số trong code, không phải input người dùng
    with driver.session() as session:
        session.run(f"MATCH (:{label})-[r]->() CALL (r) {{ DELETE r }} IN TRANSACTIONS OF 10000 ROWS").consume()
        session.run(f"MATCH ()-[r]->(:{label}) CALL (r) {{ DELETE r }} IN TRANSACTIONS OF 10000 ROWS").consume()
        session.run(f"MATCH (n:{label}) CALL (n) {{ DELETE n }} IN TRANSACTIONS OF 5000 ROWS").consume()
