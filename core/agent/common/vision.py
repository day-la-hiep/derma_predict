"""Mô tả ảnh da bằng model multimodal cấu hình ở `settings.AGENT_VISION_MODEL`"""

import asyncio
import base64
from io import BytesIO

from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image

from agent.common.llm import get_model
from app.config.settings import settings

_MAX_SIDE = 1024

_SYSTEM_PROMPT = (
    "Bạn là trợ lý mô tả ảnh da liễu hỗ trợ tiền chẩn đoán. Chỉ mô tả những gì NHÌN THẤY được "
    "trong ảnh, không khẳng định chẩn đoán. Trả lời bằng tiếng Việt, ngắn gọn, đúng 4 mục:\n"
    "1. Hình thái: loại tổn thương, màu sắc, ranh giới, bề mặt, kích thước tương đối.\n"
    "2. Phân bố: số lượng, vị trí, cách sắp xếp trong ảnh.\n"
    "3. Giả thuyết: tối đa 3 bệnh có thể gặp, mỗi bệnh kèm lý do dựa trên dấu hiệu trong ảnh.\n"
    "4. Dấu hiệu cần lưu ý: dấu hiệu cảnh báo nếu có, và điều ảnh không cho biết được "
    "(ảnh mờ, thiếu sáng, thiếu bối cảnh...).\n"
    "Nếu ảnh không phải da hoặc quá mờ để nhận định, nói rõ điều đó."
)


class VisionError(Exception):
    pass


def _to_data_uri(image_bytes: bytes) -> str:
    # Chuẩn hoá về JPEG ≤1024px: giảm payload và tránh định dạng server không nhận (webp).
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def describe_skin_image(image_bytes: bytes) -> str:
    if not settings.AGENT_VISION_MODEL:
        raise VisionError("AGENT_VISION_MODEL chưa được cấu hình.")
    data_uri = await asyncio.to_thread(_to_data_uri, image_bytes)
    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": "Hãy mô tả tổn thương da trong ảnh."},
            ]
        ),
    ]
    try:
        reply = await asyncio.wait_for(
            get_model(settings.AGENT_VISION_MODEL).ainvoke(messages),
            timeout=settings.AGENT_VISION_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 — mọi lỗi provider đều quy về lỗi mềm cho tool
        raise VisionError(f"Gọi model mô tả ảnh thất bại: {e}") from e
    return reply.text.strip()
