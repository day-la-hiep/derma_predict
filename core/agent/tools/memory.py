import asyncio
import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator, Literal

import psycopg
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import AsyncPostgresStore
from pydantic import BaseModel, Field

from agent.common.llm import get_model
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Memory theo hồ sơ bệnh nhân (`patient_profile_id`), không theo tài khoản: một tài khoản quản lý hồ sơ cho cả người nhà.
MEMORY = "memories"
PENDING = "memory_pending"
META = "memory_meta"
ARCHIVE = "memories_archive"
META_KEY = "state"

MAX_INJECTED = 10
MAX_EXISTING = 30
MAX_PENDING_READ = 500
MAX_CONTENT_CHARS = 200
_MAX_ATTEMPTS = 2
# Gom memory theo ngày chỉ khi có đủ thay đổi, tránh gọi LLM cho một danh sách gần như không đổi.
_MIN_CHANGES_FOR_AGE_CONSOLIDATION = 5

_profile_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

BATCH_SYSTEM = """Bạn là bộ phận cập nhật BỘ NHỚ DÀI HẠN nội bộ của hệ thống tư vấn da liễu. Người dùng không đọc đầu ra này: chỉ gọi hàm, KHÔNG chào hỏi, KHÔNG viết văn bản.

Bộ nhớ lưu những thông tin DÙNG LÂU DÀI về một bệnh nhân: tiền sử bệnh, bệnh nền, thuốc đang dùng, dị ứng, mang thai / cho con bú, cơ địa. KHÔNG lưu triệu chứng tức thời của lần này (vd "ngứa 3 ngày"), lời của trợ lý, hay suy đoán chẩn đoán.

Bạn nhận "Bộ nhớ hiện có" (mỗi dòng có nhãn M1, M2...) và "Tin nhắn mới của bệnh nhân" (nhiều tin gom lại). Đối chiếu rồi nêu các thao tác:
* add: thông tin dài hạn mới, chưa có bản nào nói về nó. `content`: một câu ngắn (tối đa 25 từ), đúng điều bệnh nhân nói.
* update: cùng chủ đề với một bản cũ hoặc mâu thuẫn với nó (vd "đã sinh" so với "đang mang thai", "hết dị ứng"): ghi `target_key` là nhãn của bản cũ (M1...) và `content` là nội dung MỚI thay thế hoàn toàn.
* skip: không cần ghi (đã có đúng ý đó, hoặc không phải thông tin dài hạn).
Chỉ dựa vào lời bệnh nhân; không bịa, không suy diễn. Không có gì đáng nhớ thì trả danh sách rỗng."""

CONSOLIDATE_SYSTEM = """Bạn là bộ phận gom BỘ NHỚ DÀI HẠN nội bộ của hệ thống tư vấn da liễu. Người dùng không đọc đầu ra này: chỉ gọi hàm, KHÔNG chào hỏi, KHÔNG viết văn bản.

Bạn nhận toàn bộ bộ nhớ của một bệnh nhân (cũ trước, mới sau). Trả về danh sách GỌN hơn:
* Gộp các mục trùng ý hoặc cùng chủ đề thành một mục.
* Khi hai mục mâu thuẫn, mục MỚI hơn (đứng sau) thắng.
* Mỗi mục một câu ngắn (tối đa 25 từ). Tối đa {limit} mục.
* TUYỆT ĐỐI không thêm thông tin không có trong danh sách, không bỏ thông tin còn đúng chỉ vì ngắn gọn."""


class MemoryOp(BaseModel):
    action: Literal["add", "update", "skip"]
    target_key: str = Field(default="", description="Nhãn M# của bản cũ cần thay, chỉ dùng khi action=update")
    content: str = Field(default="", description="Nội dung ngắn cho add / update")


class MemoryOps(BaseModel):
    """Bản ghi NỘI BỘ của hệ thống, người dùng không đọc: chỉ điền các trường, không chào hỏi."""

    ops: list[MemoryOp] = Field(default_factory=list)


class ConsolidatedMemory(BaseModel):
    """Bản ghi NỘI BỘ của hệ thống, người dùng không đọc: chỉ điền các trường, không chào hỏi."""

    items: list[str] = Field(default_factory=list)


def build_memory_store() -> BaseStore:
    """Store trong RAM (test, debug, module-level `chat_graph`); worker thay bằng store Postgres lúc khởi động."""
    return InMemoryStore()


@asynccontextmanager
async def postgres_memory_store() -> AsyncIterator[BaseStore]:
    """Store Postgres trong schema `langgraph` riêng để Alembic của Core không đụng tới; tự tạo bảng khi mở."""
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    sep = "&" if "?" in url else "?"
    async with AsyncPostgresStore.from_conn_string(f"{url}{sep}options=-csearch_path%3Dlanggraph") as store:
        await store.setup()
        yield store


def _now() -> datetime:
    return datetime.now(UTC)


def _clip(text: str) -> str:
    return " ".join(text.split())[:MAX_CONTENT_CHARS]


async def list_memories(store: BaseStore, profile_id: str, limit: int = MAX_EXISTING) -> list[tuple[str, str]]:
    """(khoá, nội dung) của hồ sơ, mới cập nhật nhất trước; không query nên không gọi embedding."""
    items = await store.asearch((profile_id, MEMORY), limit=200)
    items.sort(key=lambda i: i.updated_at, reverse=True)
    return [(i.key, str(i.value.get("content", ""))) for i in items[:limit] if i.value.get("content")]


async def buffer_message(store: BaseStore, profile_id: str, conversation_id: str, text: str) -> None:
    await store.aput(
        (profile_id, PENDING),
        str(uuid.uuid4()),
        {"text": text, "conversation_id": conversation_id, "at": _now().isoformat()},
    )


async def _pending(store: BaseStore, profile_id: str) -> list[tuple[str, str]]:
    items = await store.asearch((profile_id, PENDING), limit=MAX_PENDING_READ)
    items.sort(key=lambda i: i.created_at)
    return [(i.key, str(i.value.get("text", ""))) for i in items]


async def _load_meta(store: BaseStore, profile_id: str) -> dict[str, Any]:
    item = await store.aget((profile_id, META), META_KEY)
    return dict(item.value) if item is not None else {}


async def _save_meta(store: BaseStore, profile_id: str, meta: dict[str, Any]) -> None:
    await store.aput((profile_id, META), META_KEY, meta)


def _parse_time(value: Any, default: datetime) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        logger.warning("mốc thời gian memory không hợp lệ %r, dùng mặc định", value)
        return default


async def _call_structured[T: BaseModel](schema: type[T], system: str, human: str, model: str | None) -> T | None:
    structured = get_model(model).with_structured_output(schema, method="function_calling")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = await structured.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        except Exception as exc:  # noqa: BLE001  # model trả sai schema / lỗi mạng: không làm hỏng lượt chat
            logger.warning("lần %d/%d: gọi LLM cho memory lỗi: %s", attempt + 1, _MAX_ATTEMPTS, exc)
            continue
        if isinstance(result, schema):
            return result
        logger.warning("lần %d/%d: model không trả %s (nhận %s)", attempt + 1, _MAX_ATTEMPTS, schema.__name__, type(result).__name__)
    return None


async def apply_ops(store: BaseStore, profile_id: str, existing: list[tuple[str, str]], ops: list[MemoryOp]) -> int:
    """Áp các thao tác của LLM; trả số bản ghi đã thêm hoặc đổi. Nhãn M# lạ coi như add."""
    by_label = {f"M{i}": key for i, (key, _) in enumerate(existing, 1)}
    changed = 0
    for op in ops:
        content = _clip(op.content)
        if op.action == "skip" or not content:
            continue
        key = by_label.get(op.target_key.strip().upper()) if op.action == "update" else None
        if op.action == "update" and key is None:
            logger.warning("update với nhãn %r không có trong bộ nhớ hiện có, chuyển thành add", op.target_key)
        if key is not None:
            old = next(c for k, c in existing if k == key)
            logger.info("memory %s: ghi đè %r -> %r", profile_id, old, content)
        else:
            key = str(uuid.uuid4())
            logger.info("memory %s: thêm %r", profile_id, content)
        await store.aput((profile_id, MEMORY), key, {"content": content})
        changed += 1
    return changed


async def run_batch(store: BaseStore, profile_id: str, model: str | None = None) -> bool:
    """Một lần gọi LLM đối chiếu toàn bộ tin trong bộ đệm với bộ nhớ hiện có; lỗi thì giữ nguyên bộ đệm để lần sau thử lại."""
    pending = await _pending(store, profile_id)
    if not pending:
        return False
    existing = await list_memories(store, profile_id)
    current = "\n".join(f"M{i}. {c}" for i, (_, c) in enumerate(existing, 1)) or "(chưa có)"
    messages = "\n".join(f"- {t}" for _, t in pending)
    result = await _call_structured(
        MemoryOps, BATCH_SYSTEM, f"Bộ nhớ hiện có:\n{current}\n\nTin nhắn mới của bệnh nhân:\n{messages}\n\nGọi hàm MemoryOps.", model
    )
    if result is None:
        logger.warning("memory %s: bỏ qua batch, giữ %d tin trong bộ đệm", profile_id, len(pending))
        return False
    changed = await apply_ops(store, profile_id, existing, result.ops)
    for key, _ in pending:
        await store.adelete((profile_id, PENDING), key)
    meta = await _load_meta(store, profile_id)
    meta["last_batch_at"] = _now().isoformat()
    meta["changes_since_consolidate"] = int(meta.get("changes_since_consolidate", 0)) + changed
    await _save_meta(store, profile_id, meta)
    logger.info("memory %s: batch %d tin, %d thay đổi", profile_id, len(pending), changed)
    return True


def _should_consolidate(count: int, meta: dict[str, Any], now: datetime) -> bool:
    if count <= 1:
        return False
    if count >= settings.AGENT_MEMORY_CONSOLIDATE_AT:
        return True
    last = _parse_time(meta.get("last_consolidated_at"), now)
    aged = now - last >= timedelta(days=settings.AGENT_MEMORY_CONSOLIDATE_DAYS)
    return aged and int(meta.get("changes_since_consolidate", 0)) >= _MIN_CHANGES_FOR_AGE_CONSOLIDATION


async def consolidate(store: BaseStore, profile_id: str, model: str | None = None) -> bool:
    """Gom bộ nhớ thành danh sách gọn; chép bản cũ sang `memories_archive` trước khi thay, lỗi hoặc kết quả không hợp lệ thì giữ nguyên."""
    items = await store.asearch((profile_id, MEMORY), limit=200)
    items.sort(key=lambda i: i.updated_at)
    old = [(i.key, str(i.value.get("content", ""))) for i in items if i.value.get("content")]
    if len(old) <= 1:
        return False
    listing = "\n".join(f"- {c}" for _, c in old)
    result = await _call_structured(
        ConsolidatedMemory, CONSOLIDATE_SYSTEM.format(limit=MAX_INJECTED), f"Bộ nhớ hiện có (cũ trước, mới sau):\n{listing}\n\nGọi hàm ConsolidatedMemory.", model
    )
    new = [_clip(s) for s in (result.items if result else []) if _clip(s)]
    if not new or len(new) > MAX_INJECTED:
        logger.warning("memory %s: kết quả gom không hợp lệ (%d mục), giữ nguyên %d bản", profile_id, len(new), len(old))
        return False
    run_id = str(uuid.uuid4())
    at = _now().isoformat()
    for key, content in old:
        await store.aput((profile_id, ARCHIVE), str(uuid.uuid4()), {"content": content, "archived_at": at, "run_id": run_id})
    for key, _ in old:
        await store.adelete((profile_id, MEMORY), key)
    for content in new:
        await store.aput((profile_id, MEMORY), str(uuid.uuid4()), {"content": content})
    meta = await _load_meta(store, profile_id)
    meta["last_consolidated_at"] = at
    meta["changes_since_consolidate"] = 0
    await _save_meta(store, profile_id, meta)
    logger.info("memory %s: gom %d bản thành %d (bản cũ lưu ở %s, run %s)", profile_id, len(old), len(new), ARCHIVE, run_id)
    return True


def _should_batch(pending: int, meta: dict[str, Any], now: datetime) -> bool:
    if pending <= 0:
        return False
    if pending >= settings.AGENT_MEMORY_BATCH_MAX_PENDING:
        return True
    interval = settings.AGENT_MEMORY_BATCH_INTERVAL_MIN
    if interval <= 0:
        return False
    return now - _parse_time(meta.get("last_batch_at"), now) >= timedelta(minutes=interval)


async def after_turn(store: BaseStore, profile_id: str, conversation_id: str, text: str, model: str | None = None) -> None:
    """Chạy nền sau khi câu trả lời đã gửi: ghi tin người dùng vào bộ đệm, đủ điều kiện thì cập nhật memory theo batch rồi gom nếu cần."""
    if not profile_id or not text.strip():
        return
    async with _profile_locks[profile_id]:
        try:
            now = _now()
            meta = await _load_meta(store, profile_id)
            if not meta:
                # Mốc đầu tiên là lúc thấy hồ sơ này, để batch đầu tiên cũng đợi đủ một chu kỳ thay vì chạy ngay với một tin.
                meta = {"last_batch_at": now.isoformat(), "last_consolidated_at": now.isoformat(), "changes_since_consolidate": 0}
                await _save_meta(store, profile_id, meta)
            await buffer_message(store, profile_id, conversation_id, text.strip())
            pending = len(await _pending(store, profile_id))
            if not _should_batch(pending, meta, now):
                return
            if not await run_batch(store, profile_id, model):
                return
            meta = await _load_meta(store, profile_id)
            if _should_consolidate(len(await list_memories(store, profile_id, limit=200)), meta, _now()):
                await consolidate(store, profile_id, model)
        except Exception:  # noqa: BLE001  # tác vụ nền: lỗi store/LLM không được làm sập worker
            logger.exception("memory %s: cập nhật nền lỗi", profile_id)
