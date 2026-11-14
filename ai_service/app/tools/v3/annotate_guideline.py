import asyncio
import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.context.agent_context import AgentContext
from app.prompt.v3.pre_diagnosis_prompts import ANNOTATE_GUIDELINE
from app.reasoning.structured_llm_calls import invoke_structured_with_retry
from app.state.v3.diagnosis import GuidelineNote
from app.state.v3.facts import Fact

logger = logging.getLogger(__name__)

MAX_DISEASES = 5
CHUNK_CHARS = 1500
# Gọi song song nhiều bệnh qua OpenRouter dễ bị giới hạn tốc độ.
_CONCURRENCY = asyncio.Semaphore(3)


class AnnotationItem(BaseModel):
    fact_index: int
    stance: Literal["support", "refute", "irrelevant"]
    chunk_id: str
    quote: str = Field(default="", max_length=400)


class Annotations(BaseModel):
    """Bản ghi nội bộ: đoạn sách ủng hộ / phản bác dữ kiện với bệnh đang xét."""

    items: list[AnnotationItem] = Field(default_factory=lambda: list[AnnotationItem]())


def _squash(text: str) -> str:
    return " ".join(text.split()).lower()


def validate_annotations(items: list[AnnotationItem], facts: list[Fact], chunks: list[dict[str, Any]]) -> list[GuidelineNote]:
    """Bỏ mục có chunk_id lạ, fact_index sai hoặc quote không có nguyên văn trong đoạn (model bịa); không lưu mục irrelevant."""
    texts = {str(c["chunk_id"]): _squash(str(c.get("text") or "")) for c in chunks}
    notes: list[GuidelineNote] = []
    for item in items:
        if item.stance == "irrelevant":
            continue
        reason = (
            "chunk_id lạ" if item.chunk_id not in texts
            else "fact_index sai" if not 1 <= item.fact_index <= len(facts)
            else "quote không có trong đoạn" if not item.quote.strip() or _squash(item.quote) not in texts[item.chunk_id]
            else None
        )
        if reason:
            logger.warning("annotate_guideline: bỏ mục (%s): %s", reason, item.model_dump())
            continue
        fact = facts[item.fact_index - 1]
        notes.append(GuidelineNote(fact=fact.node_name or fact.text, stance=item.stance, chunk_id=item.chunk_id, quote=item.quote.strip()[:160]))
    return notes


async def annotate_guideline(ctx: AgentContext, disease_name: str, facts: list[Fact], chunks: list[dict[str, Any]]) -> list[GuidelineNote]:
    if not chunks or not facts:
        return []
    body = "\n".join([
        f"Bệnh đang xét: {disease_name}", "", "Dữ kiện:",
        *(f"{i}. {f.node_name or f.text_en or f.text} ({f.assertion})" for i, f in enumerate(facts, 1)),
        "", "Đoạn sách:", *(f"[{c['chunk_id']}] {str(c.get('text') or '')[:CHUNK_CHARS]}" for c in chunks),
    ])
    async with _CONCURRENCY:
        result = await invoke_structured_with_retry(ctx, Annotations, [SystemMessage(content=ANNOTATE_GUIDELINE), HumanMessage(content=body)])
    return validate_annotations(result.items, facts, chunks)
