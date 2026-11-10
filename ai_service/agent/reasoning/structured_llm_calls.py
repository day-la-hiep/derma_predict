import logging
from typing import Any, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage
from pydantic import BaseModel

from agent.common.llm import get_model
from agent.context.agent_context import AgentContext

logger = logging.getLogger(__name__)

# Số lần gọi lại tối đa khi model viết văn bản thay vì gọi hàm (gemma qua OpenRouter hay bỏ qua tool_choice).
MAX_MODEL_RETRIES = 2
T = TypeVar("T", bound=BaseModel)


def get_model_retries(ctx: AgentContext) -> int:
    return MAX_MODEL_RETRIES if ctx.max_model_retries is None else ctx.max_model_retries


def get_model_for_turn(ctx: AgentContext) -> BaseChatModel:
    return get_model(ctx.model or None)


def build_task_reminder(name: str | None = None, error: object = None) -> HumanMessage:
    """Tin nhắn cuối nhắc nhiệm vụ: nếu tin cuối là lời người bệnh thì model trả lời họ (chào hỏi, đồng cảm) thay vì gọi hàm."""
    what = f"gọi hàm {name}" if name else "gọi các tool tra cứu phù hợp"
    hint = f" Lần trước chưa đạt: {str(error)[:300]}" if error else ""
    return HumanMessage(content=f"[Nhiệm vụ của hệ thống] Thực hiện nhiệm vụ nêu trong chỉ dẫn ở trên bằng cách {what}. KHÔNG chào hỏi, KHÔNG viết văn bản.{hint}")


async def invoke_structured_with_retry(ctx: AgentContext, schema: type[T], messages: list[AnyMessage]) -> T:
    structured = get_model_for_turn(ctx).with_structured_output(schema, method="function_calling", include_raw=True)
    error: object = None
    attempts = get_model_retries(ctx) + 1
    for attempt in range(attempts):
        result = cast("dict[str, Any]", await structured.ainvoke([*messages, build_task_reminder(schema.__name__, error)]))
        parsed = result.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        raw = result.get("raw")
        error = result.get("parsing_error")
        logger.warning(
            "lần %d/%d: model không trả %s (lỗi parse: %s; đầu ra: %.120s)",
            attempt + 1,
            attempts,
            schema.__name__,
            result.get("parsing_error"),
            str(getattr(raw, "content", "")).replace("\n", " "),
        )
    raise RuntimeError(f"model không trả {schema.__name__} sau {attempts} lần thử")
