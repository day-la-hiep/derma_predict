"""Model LLM (OpenRouter)"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config.settings import settings


@lru_cache
def get_model(model: str | None = None) -> BaseChatModel:
    """`model` dạng "openrouter:<tên>"; rỗng -> `settings.AGENT_MODEL`."""
    provider, _, name = (model or settings.AGENT_MODEL).partition(":")
    if provider != "openrouter" or not name:
        raise ValueError(f'model="{model}" phải có dạng "openrouter:<tên model>", vd "openrouter:google/gemma-4-26b-a4b-it".')
    # OpenRouter tương thích OpenAI; `model_provider="openai"` để `init_chat_model` không cắt tên model có "/" hoặc ":"
    return init_chat_model(
        name,
        model_provider="openai",
        temperature=settings.AGENT_TEMPERATURE,
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )
