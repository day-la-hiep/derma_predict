import asyncio
import logging
from typing import Any

from langchain_core.tools import StructuredTool

from agent.tools.skin_image.vision import VisionError, describe_skin_image
from agent.tools.similar_case_search import search_similar_cases
from agent.tools.skin_image.classifier import get_predictor
from app.deps import get_attachment_store

logger = logging.getLogger(__name__)


async def _load_image(key: str) -> bytes | None:
    data = await get_attachment_store().get_object_bytes(key)
    if data is None:
        logger.warning("không tìm thấy ảnh %s trong kho file", key)
    return data


async def _predict(data: bytes) -> list[dict[str, Any]]:
    # torch inference (CPU) đồng bộ: chạy thread riêng để không chặn event loop của worker.
    return await asyncio.to_thread(get_predictor().predict, data, 5)


async def _describe_image(data: bytes) -> str:
    return await describe_skin_image(data)


async def _search_cases(label: str) -> list[dict[str, Any]]:
    return await search_similar_cases(label, 5)


def _step(name: str, fn: Any) -> StructuredTool:
    # Mỗi bước nhỏ nhất gọi qua tool (không đăng ký cho LLM) để callback ghi mốc thời gian vào trace / timeline UI test, dưới đúng node chứa nó.
    return StructuredTool.from_function(coroutine=fn, name=name, description=name)


_LOAD, _PREDICT, _DESCRIBE, _CASES = (
    _step("load_image", _load_image),
    _step("cnn_predict", _predict),
    _step("vision_describe", _describe_image),
    _step("search_cases", _search_cases),
)


async def predict_skin_image_labels(key: str) -> dict[str, Any] | None:
    data = await _LOAD.ainvoke({"key": key})
    if data is None:
        return None
    try:
        top = await _PREDICT.ainvoke({"data": data})
    except Exception as exc:  # noqa: BLE001  # CNN lỗi (thiếu checkpoint, ảnh hỏng) không làm hỏng lượt chat
        logger.warning("CNN phân loại ảnh %s lỗi: %s", key, exc)
        return None
    return {"key": key, "top": top}


async def describe_skin_image_with_vision(key: str) -> dict[str, Any] | None:
    data = await _LOAD.ainvoke({"key": key})
    if data is None:
        return None
    try:
        return {"key": key, "text": await _DESCRIBE.ainvoke({"data": data})}
    except VisionError as exc:
        logger.warning("model mô tả ảnh %s lỗi: %s", key, exc)
        return None


async def search_similar_cases_by_cnn_label(label: str) -> dict[str, Any]:
    try:
        cases = await _CASES.ainvoke({"label": label})
    except Exception as exc:  # noqa: BLE001  # Qdrant lỗi: bỏ nhánh ca bệnh, vẫn còn CNN và mô tả
        logger.warning("tra ca bệnh theo nhãn CNN '%s' lỗi: %s", label, exc)
        return {}
    return {"label": label, "cases": cases}
