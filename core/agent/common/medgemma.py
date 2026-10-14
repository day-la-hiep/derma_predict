"""Client MedGemma chạy trên endpoint Vertex AI Model Garden (chat completions kiểu OpenAI)"""

import asyncio
import base64
from io import BytesIO

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from PIL import Image

from app.config.settings import settings

_MAX_SIDE = 1024
_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

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

_credentials: Credentials | None = None


class MedGemmaError(Exception):
    pass


def _endpoint_url() -> str:
    if settings.MEDGEMMA_BASE_URL:
        return settings.MEDGEMMA_BASE_URL
    if not (
        settings.MEDGEMMA_PROJECT
        and settings.MEDGEMMA_LOCATION
        and settings.MEDGEMMA_ENDPOINT_ID
    ):
        raise MedGemmaError(
            "Thiếu cấu hình MEDGEMMA_PROJECT / MEDGEMMA_LOCATION / MEDGEMMA_ENDPOINT_ID."
        )
    loc = settings.MEDGEMMA_LOCATION
    return (
        f"https://{loc}-aiplatform.googleapis.com/v1beta1/projects/{settings.MEDGEMMA_PROJECT}"
        f"/locations/{loc}/endpoints/{settings.MEDGEMMA_ENDPOINT_ID}/chat/completions"
    )


def _access_token() -> str:
    # refresh là I/O đồng bộ nên hàm này chỉ được gọi qua `asyncio.to_thread`.
    global _credentials
    creds = _credentials
    if creds is None:
        creds, _ = google.auth.default(scopes=_SCOPES)  # pyright: ignore[reportUnknownMemberType]
        _credentials = creds
    if not creds.valid:
        creds.refresh(Request())  # pyright: ignore[reportUnknownMemberType]
    return str(creds.token)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]


def _to_data_uri(image_bytes: bytes) -> str:
    # Chuẩn hoá về JPEG ≤1024px: giảm payload và tránh định dạng endpoint không nhận (webp).
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def describe_skin_image(image_bytes: bytes) -> str:
    data_uri = await asyncio.to_thread(_to_data_uri, image_bytes)
    # Server local (Ollama/vLLM) không cần token Google.
    headers: dict[str, str] = {}
    if settings.MEDGEMMA_USE_GOOGLE_AUTH:
        token = await asyncio.to_thread(_access_token)
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "model": settings.MEDGEMMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": "Hãy mô tả tổn thương da trong ảnh."},
                ],
            },
        ],
        "max_tokens": 700,
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.MEDGEMMA_TIMEOUT) as client:
            resp = await client.post(
                _endpoint_url(),
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise MedGemmaError(f"Gọi MedGemma thất bại: {e}") from e
    return str(content).strip()
