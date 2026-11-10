"""Xuất hợp đồng từ `core/` (đặc tả cho service Spring): chạy trong `core/`: `PYTHONPATH=. .venv/bin/python ../contracts/export_contracts.py`."""

import json
from pathlib import Path

from agent.dto.schemas import AgentResponseMessage, TurnAttachment, TurnRequest
from main import app

OUT = Path(__file__).resolve().parent


def write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


write_json("openapi.core.json", app.openapi())
write_json(
    "messages.schema.json",
    {m.__name__: m.model_json_schema() for m in (TurnRequest, TurnAttachment, AgentResponseMessage)},
)
