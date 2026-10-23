from typing import Any, Literal

from pydantic import BaseModel


class SignalInput(BaseModel):
    kind: Literal["offer", "answer", "candidate", "media"]  # media = bên kia bật/tắt mic, camera
    payload: dict[str, Any]


class StartCallInput(BaseModel):
    mode: Literal["audio", "video"] = "audio"  # chỉ để bên nhận biết bên gọi có bật camera; không lưu DB


class EndCallInput(BaseModel):
    reason: Literal["missed"] | None = None  # bên gọi tự huỷ vì hết giờ không ai bắt máy
