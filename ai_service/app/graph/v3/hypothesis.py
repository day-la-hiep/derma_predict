import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.middleware.tool_step_events import emit_tool_step
from app.state.v3.diagnosis import Hypothesis
from app.state.v3.facts import Fact, get_fact_weight
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.fuse_scores import fuse_scores
from app.tools.v3.guideline_search import search_by_symptom
from app.tools.v3.kg_rank_diseases import kg_rank_diseases
from app.tools.v3.propose_more import propose_more

logger = logging.getLogger(__name__)


async def _safe(name: str, coro: Any) -> list[dict[str, Any]]:
    # Một nguồn giả thuyết lỗi thì các nguồn còn lại vẫn xếp hạng được.
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("hypothesize: nguồn %s lỗi: %s", name, exc)
        return []


async def _empty() -> list[dict[str, Any]]:
    return []


def get_history_signals(history: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Chẩn đoán cũ chỉ tăng ưu tiên, giảm theo thời gian như fact lịch sử."""
    out: list[dict[str, Any]] = []
    for item in history:
        if not item.get("disease_id"):
            continue
        moment = datetime.fromisoformat(item["time"]) if item.get("time") else now
        weight = get_fact_weight(Fact(slot="disease", text=item.get("name", ""), source="history", time=moment), now)
        out.append({"disease_id": item["disease_id"], "name": item.get("name") or item["disease_id"], "score": weight})
    return out


def get_cnn_signals(cnn: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # nhãn chưa map sang node bệnh thì không vào xếp hạng, vẫn hiện ở bước intake
    return [{"disease_id": c["disease_id"], "name": c["label"], "score": c["prob"]} for c in cnn if c.get("disease_id")]


def render_hypotheses(hyps: list[Hypothesis]) -> str:
    return "\n".join(
        f"{i}. {h.name} ({h.disease_id}) {h.score:.2f} — " + ", ".join(f"{k} {v:.2f}" for k, v in h.signals.items())
        for i, h in enumerate(hyps, 1)
    ) or "(chưa có giả thuyết: chưa có dữ kiện khớp đồ thị, chưa có ảnh)"


async def hypothesize(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    now = datetime.now(timezone.utc)
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    kg, rag = await asyncio.gather(_safe("kg", kg_rank_diseases(facts)), _safe("rag", search_by_symptom(facts)))
    signals = {"kg": kg, "cnn": get_cnn_signals(state.get("cnn_scores", [])), "history": get_history_signals(state.get("history_diseases", []), now), "rag": rag}
    first = fuse_scores(signals)
    # propose_more chỉ ở lượt đầu có dữ kiện: các lượt sau danh sách đã ổn định, thêm một lượt LLM chỉ làm chậm
    proposed = await _safe("propose_more", propose_more(ctx, facts, [h.name for h in first])) if not state.get("hypotheses") and facts else await _empty()
    hyps = fuse_scores(signals, proposed)
    await emit_tool_step(ctx, "hypothesize", {"sources": {k: len(v) for k, v in signals.items()}, "proposed": len(proposed)}, render_hypotheses(hyps))
    return {"hypotheses": [h.model_dump() for h in hyps]}
