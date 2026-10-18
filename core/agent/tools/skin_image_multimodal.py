"""Tool mô tả tổn thương da từ ẢNH bằng model multimodal (`settings.AGENT_VISION_MODEL`)"""

from typing import Any

from langchain.tools import ToolRuntime, tool

from agent.common.vision import VisionError, describe_skin_image
from agent.context.agent_context import AgentContext
from agent.tools.skin_image_classifier import _resolve_object_key  # pyright: ignore[reportPrivateUsage]
from app.api.deps import get_file_store_service


@tool
async def analyze_skin_image_multimodal(
    object_key: str, runtime: ToolRuntime[AgentContext, Any]
) -> str:
    """Mô tả tổn thương da trong ảnh bằng mô hình đa phương thức (vd MedGemma): hình
    thái, phân bố, vài giả thuyết kèm lý do và dấu hiệu cần lưu ý. Bổ sung cho
    `classify_skin_image` (CNN chỉ cho nhãn + % tin cậy, không giải thích).

    CHỈ gọi khi tin nhắn người dùng có phần "[Ảnh đính kèm]" — copy ĐÚNG `object_key`.

    KẾT QUẢ LÀ MÔ TẢ + GIẢ THUYẾT, KHÔNG PHẢI CHẨN ĐOÁN và không phải bằng chứng lâm sàng:
    chỉ dùng bổ sung cho kết quả CNN. Hai nguồn bất đồng thì nói rõ mức bất định.

    Args:
        object_key: Object key MinIO của ảnh, lấy nguyên văn từ phần "[Ảnh đính kèm]"
            trong tin nhắn người dùng (field `object_key`).
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    object_key = _resolve_object_key(object_key, ctx.image_keys)
    image_bytes = await get_file_store_service().get_object_bytes(object_key)
    if image_bytes is None:
        return f"Không tìm thấy ảnh với object_key='{object_key}'."

    try:
        description = await describe_skin_image(image_bytes)
    except VisionError as e:
        # Lỗi mềm: agent vẫn còn kết quả CNN để làm việc tiếp.
        return f"Chưa mô tả được ảnh bằng mô hình đa phương thức ({e}). Dùng kết quả CNN."

    return (
        "Mô tả ảnh (mô hình đa phương thức, KHÔNG phải chẩn đoán y khoa):\n"
        + description
        + "\n\nChỉ là mô tả bổ sung cho kết quả CNN, chưa phải bằng chứng lâm sàng."
    )
