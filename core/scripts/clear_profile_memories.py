"""Xoá memory dài hạn cũ (đa phần là thông tin lâm sàng dạng câu tự do) của mọi hồ sơ; mặc định chỉ liệt kê, `--apply` mới xoá.

    cd core && .venv/bin/python scripts/clear_profile_memories.py [--apply]
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # chạy được từ `core/` mà không cần cài package

from agent.persistence import postgres_persistence  # noqa: E402
from agent.tools.memory import MEMORY, META, PENDING  # noqa: E402


async def main(apply: bool) -> None:
    async with postgres_persistence() as (store, _):
        # giữ `memories_archive`: không được nạp vào prompt, chỉ để truy vết
        for suffix in (MEMORY, PENDING, META):
            for ns in await store.alist_namespaces(suffix=(suffix,), limit=10_000):
                items = await store.asearch(ns, limit=10_000)
                print(f"{'/'.join(ns)}: {len(items)} mục")
                for item in items:
                    if suffix == MEMORY:
                        print(f"  - {item.value.get('content', '')}")
                    if apply:
                        await store.adelete(ns, item.key)
    print("Đã xoá." if apply else "Chạy thử: chưa xoá gì, thêm --apply để xoá.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
