import logging

from langgraph.store.base import BaseStore

from agent.tools.patient_memory import MAX_INJECTED, list_memories

logger = logging.getLogger(__name__)


async def load_memory(store: BaseStore | None, profile_id: str) -> str:
    """Memory dài hạn của hồ sơ (tối đa `MAX_INJECTED` bản mới nhất, một truy vấn, không embedding); không có hoặc lỗi thì trả chuỗi rỗng."""
    if store is None or not profile_id:
        return ""
    try:
        memories = await list_memories(store, profile_id, limit=MAX_INJECTED)
    except Exception as exc:  # noqa: BLE001
        # Bộ nhớ dài hạn không bắt buộc cho một lượt trả lời; nếu DB lỗi thì bỏ qua thay vì làm hỏng cả lượt hội thoại.
        logger.warning("không đọc được memory dài hạn: %s", exc)
        return ""
    return "\n".join(f"- {content}" for _, content in memories)


# memory chỉ còn thông tin giao tiếp; tách tên khối khỏi "Hồ sơ lâm sàng" để model không lấy làm căn cứ y khoa
MEMORY_HEADER = "Về người dùng (chỉ để giao tiếp cho phù hợp, KHÔNG phải dữ kiện y khoa):"


def inject_memory(base: str, memory_text: str) -> str:
    return f"{base}\n\n{MEMORY_HEADER}\n{memory_text}" if memory_text else base
