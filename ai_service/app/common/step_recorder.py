import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

logger = logging.getLogger(__name__)

_OUTPUT_MAX_CHARS = 2000
_SKIP_NODES = {"__start__", "__end__"}


class StepRecorder(AsyncCallbackHandler):
    """Ghi kết quả từng node ra jsonl để chấm lại từng bước sau này; mỗi lượt chạy một instance."""

    run_inline = True

    def __init__(self, log_dir: str, conversation_id: str) -> None:
        self._path = Path(log_dir) / f"{conversation_id}.jsonl"
        self._conversation_id = conversation_id
        self._nodes: dict[UUID, tuple[str, float, list[str]]] = {}
        # Lượt LLM gom theo tên node đang chạy (metadata `langgraph_node` của lần gọi model).
        self._llm_node: dict[UUID, str] = {}
        self._llm_stats: dict[str, dict[str, int]] = {}

    async def on_chain_start(self, serialized: dict[str, Any] | None, inputs: Any, *, run_id: UUID, name: str | None = None,
                             metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        node = (metadata or {}).get("langgraph_node")
        if node and name == node and node not in _SKIP_NODES:
            keys = sorted(inputs) if isinstance(inputs, dict) else []
            self._nodes[run_id] = (node, time.perf_counter(), keys)

    async def on_chat_model_start(self, serialized: dict[str, Any] | None, messages: list[list[Any]], *, run_id: UUID,
                                  metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        node = (metadata or {}).get("langgraph_node")
        if node:
            self._llm_node[run_id] = node

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        node = self._llm_node.pop(run_id, None)
        if node is None:
            return
        stats = self._llm_stats.setdefault(node, {"llm_calls": 0, "tokens": 0})
        stats["llm_calls"] += 1
        gen = response.generations[0][0] if response.generations and response.generations[0] else None
        message = gen.message if isinstance(gen, ChatGeneration) else None
        if isinstance(message, AIMessage) and message.usage_metadata:
            stats["tokens"] += message.usage_metadata.get("total_tokens", 0)

    async def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._write(run_id, outputs, None)

    async def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._write(run_id, None, f"{type(error).__name__}: {error}")

    def _write(self, run_id: UUID, outputs: Any, error: str | None) -> None:
        started = self._nodes.pop(run_id, None)
        if started is None:
            return
        node, start, input_keys = started
        stats = self._llm_stats.pop(node, {"llm_calls": 0, "tokens": 0})
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "conversation_id": self._conversation_id,
            "node": node,
            "seconds": round(time.perf_counter() - start, 3),
            **stats,
            "input_keys": input_keys,
            "output_keys": sorted(outputs) if isinstance(outputs, dict) else [],
            "output": json.dumps(outputs, ensure_ascii=False, default=str)[:_OUTPUT_MAX_CHARS],
            "error": error,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            # Ghi log bước chỉ phục vụ đánh giá, không được làm hỏng lượt chat.
            logger.warning("không ghi được step log %s: %s", self._path, exc)
