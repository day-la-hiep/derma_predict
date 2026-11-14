import asyncio
import json
import logging
from functools import cache
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.common.llm import get_model
from app.config.settings import settings
from app.deps import get_attachment_store
from app.prompt.v3.pre_diagnosis_prompts import DESCRIBE_IMAGE, VLM_VERIFY
from app.tools.skin_image.analysis import predict_skin_image_labels
from app.tools.skin_image.vision import _to_data_uri  # pyright: ignore[reportPrivateUsage]
from app.tools.v3.extract_slots import Slot, Slots

logger = logging.getLogger(__name__)

_CNN_MAP_PATH = Path(__file__).resolve().parents[3] / "data" / "v3" / "cnn_to_disease.json"
_IMAGE_SLOTS = ("morphology", "color", "scale", "location", "distribution")


@cache
def load_cnn_map() -> dict[str, str | None]:
    return {k: v for k, v in json.loads(_CNN_MAP_PATH.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def merge_cnn_predictions(results: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Nhiều ảnh: mỗi nhãn lấy xác suất cao nhất; gắn disease_id theo bảng map (None nếu chưa map)."""
    best: dict[str, float] = {}
    for result in results:
        for item in (result or {}).get("top", []):
            best[item["disease"]] = max(best.get(item["disease"], 0.0), float(item["confidence"]))
    mapping = load_cnn_map()
    return [
        {"label": label, "prob": round(prob, 4), "disease_id": mapping.get(label)}
        for label, prob in sorted(best.items(), key=lambda x: x[1], reverse=True)
    ]


async def classify_images(keys: list[str]) -> list[dict[str, Any]]:
    return merge_cnn_predictions(list(await asyncio.gather(*(predict_skin_image_labels(k) for k in keys))))


def parse_image_slots(text: str) -> tuple[list[Slot], str]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"không thấy JSON trong đầu ra: {text[:120]}")
    raw = json.loads(text[start : end + 1])
    items = Slots.model_validate({"items": raw.get("items") or []}).items
    return [s for s in items if s.slot in _IMAGE_SLOTS and s.assertion in ("present", "absent")], str(raw.get("quality") or "ok")


async def describe_image(key: str, index: int) -> tuple[list[Slot], str | None]:
    """Slot nhìn thấy trong ảnh (source=image, ref=index) và lý do bỏ ảnh nếu có."""
    data = await get_attachment_store().get_object_bytes(key)
    if data is None:
        return [], "không tải được ảnh"
    # shortcut: tạm bỏ lọc chất lượng ảnh bằng code (ngưỡng chưa đo trên ảnh thật); chỉ dựa vào model ảnh tự báo "quality: poor".
    if not settings.AGENT_VISION_MODEL:
        return [], None
    uri = await asyncio.to_thread(_to_data_uri, data)
    messages = [SystemMessage(DESCRIBE_IMAGE), HumanMessage(content=[{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": "Mô tả tổn thương trong ảnh."}])]
    reply = await asyncio.wait_for(get_model(settings.AGENT_VISION_MODEL).ainvoke(messages), timeout=settings.AGENT_VISION_TIMEOUT)
    try:
        slots, quality = parse_image_slots(reply.text)
    except (ValueError, ValidationError) as exc:
        logger.warning("mô tả ảnh %s không đúng JSON: %s", key, exc)
        return [], None
    if quality == "poor":
        return [], "model ảnh báo ảnh không nhận định được"
    return [s.model_copy(update={"source": "image", "ref": index}) for s in slots], None


async def vlm_verify(key: str, phenotype: str) -> str:
    """Câu hỏi đóng trên ảnh: yes / no / unclear (unclear cả khi không có model ảnh, ảnh hỏng hay trả lời lạ)."""
    if not settings.AGENT_VISION_MODEL:
        return "unclear"
    data = await get_attachment_store().get_object_bytes(key)
    if data is None:
        return "unclear"
    uri = await asyncio.to_thread(_to_data_uri, data)
    messages = [SystemMessage(VLM_VERIFY), HumanMessage(content=[{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": f"Ảnh có dấu hiệu: {phenotype}?"}])]
    reply = await asyncio.wait_for(get_model(settings.AGENT_VISION_MODEL).ainvoke(messages), timeout=settings.AGENT_VISION_TIMEOUT)
    word = reply.text.strip().lower().split()[0].strip(".,!\"'") if reply.text.strip() else ""
    return word if word in ("yes", "no") else "unclear"
