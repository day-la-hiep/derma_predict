"""Model LLM cho agent"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config.settings import settings


def get_model(model: str | None = None) -> BaseChatModel:
    """`model` rỗng/None -> dùng `settings.AGENT_MODEL` (fallback toàn hệ thống)."""
    return _get_model_cached(model or settings.AGENT_MODEL)


@lru_cache
def _get_model_cached(model: str) -> BaseChatModel:
    if ":" not in model:
        raise ValueError(
            f'model="{model}" thiếu tiền tố provider (openrouter, openai, google_genai, deepseek, '
            f'local; vd "openrouter:{model}") — xem agent/common/llm.py.'
        )
    provider = model.split(":", 1)[0]

    if provider == "openrouter":
        # OpenRouter: API tương thích OpenAI nên dùng `ChatOpenAI` với base_url + key riêng
        # (`model_provider="openai"` để `init_chat_model` không cắt tiếp tên model có "/" hoặc ":").
        return init_chat_model(
            model.split(":", 1)[1],
            model_provider="openai",
            temperature=settings.AGENT_TEMPERATURE,
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    if provider == "openai":
        # OpenAI thật (api.openai.com); OpenRouter dùng tiền tố "openrouter:" ở trên.
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                'Provider "openai" cần OPENAI_API_KEY. Model qua OpenRouter dùng tiền tố '
                '"openrouter:" (vd "openrouter:google/gemma-4-26b-a4b-it").'
            )
        return init_chat_model(
            model.split(":", 1)[1],
            model_provider="openai",
            temperature=settings.AGENT_TEMPERATURE,
            api_key=settings.OPENAI_API_KEY,
        )

    if provider == "local":
        # "local:medgemma:4b" -> tên model "medgemma:4b" (Ollama/vLLM). `model_provider` truyền rõ nên
        # `init_chat_model` không cắt tiếp dấu ":" trong tên.
        return init_chat_model(
            model.split(":", 1)[1],
            model_provider="openai",
            temperature=settings.AGENT_TEMPERATURE,
            base_url=settings.LOCAL_LLM_BASE_URL,
            api_key=settings.LOCAL_LLM_API_KEY,
            timeout=settings.LOCAL_LLM_TIMEOUT,
        )

    if provider == "deepseek":
        # `reasoning`/`extra_body` tắt "thinking mode": model reasoning-hybrid của
        # DeepSeek (R1/V3.x trở lên) mặc định BẬT thinking, xung đột với tool_choice ép
        # cứng mà `with_structured_output(method="function_calling")` dùng (xem
        # `hybrid_retrieval/kg.py`/`critic_review`, `graph.py`) — lỗi thật đã gặp: "Thinking
        # mode does not support this tool_choice" (400). Agent này LUÔN cần tool-calling
        # đáng tin cậy nên phải tắt thinking, đổi lấy mất phần suy luận sâu của DeepSeek.
        return init_chat_model(
            model,
            temperature=settings.AGENT_TEMPERATURE,
            api_key=settings.DEEPSEEK_API_KEY,
            extra_body={"thinking": {"type": "disabled"}},
        )

    return init_chat_model(
        model,
        temperature=settings.AGENT_TEMPERATURE,
        thinking_level=settings.AGENT_THINKING_LEVEL,
        # Bắt buộc để provider TRẢ VỀ nội dung "thinking" (Gemini tự tóm tắt suy nghĩ
        # thành các đoạn ngắn) — `thinking_level` chỉ bật suy luận nội bộ, không tự trả
        # về nếu thiếu `include_thoughts`. Dùng làm dòng tóm tắt "đang làm gì" hiển thị
        # cho người dùng (event `message.thinking`, `graph.py::emit_reasoning_step`).
        include_thoughts=True,
    )
