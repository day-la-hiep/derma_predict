import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from app.common.messages import get_dialogue_history
from app.context.agent_context import AgentContext
from app.middleware.tool_step_events import emit_tool_step
from app.prompt.v3.pre_diagnosis_prompts import ANSWER
from app.reasoning.structured_llm_calls import get_model_for_turn
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.reason_cot import Reasoning, reason_cot
from app.tools.v3.verify_claims import verify_claims
from app.tools.v3.write_report import build_ranking, build_turn_hypotheses

logger = logging.getLogger(__name__)

_URGENCY_TEXT = {"urgent": "KHẨN CẤP — cần đi khám / cấp cứu ngay", "soon": "nên đi khám sớm trong vài ngày", "routine": "có thể đặt lịch khám da liễu"}


async def reply(state: PreDiagnosisState, ctx: AgentContext, system: str) -> dict[str, Any]:
    ai = await get_model_for_turn(ctx).ainvoke([SystemMessage(content=system), *get_dialogue_history(state["messages"])])
    return {"messages": [ai]}


def render_reasoning(ranking: list[dict[str, Any]], claims: list[dict[str, Any]], need_more: list[str]) -> str:
    lines = [f"{i}. {r['name']} ({r['disease_id']}) — độ tin cậy {r['confidence']}" for i, r in enumerate(ranking, 1)] or ["(không còn giả thuyết nào có bằng chứng kiểm chứng được)"]
    lines += [f"{'✓' if c['status'] == 'verified' else '?'} {c['text']} {c['cites']}" for c in claims]
    if need_more:
        lines.append("Cần thêm: " + "; ".join(need_more))
    return "\n".join(lines)


async def reason(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Khối 6 phần cho bác sĩ: CoT có khung → kiểm trích dẫn → giả thuyết gửi clinical (tab bác sĩ)."""
    ctx = runtime.context
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    hyps = [Hypothesis.model_validate(x) for x in state.get("hypotheses", [])]
    rows = [EvidenceRow.model_validate(x) for x in state.get("evidence", [])]
    try:
        reasoning = await reason_cot(ctx, facts, hyps, rows, state.get("cnn_scores", [])) if rows else Reasoning()
    except Exception as exc:  # noqa: BLE001  # model hết lượt thử: vẫn trả lời người bệnh (lời dặn an toàn), chỉ thiếu phần cho bác sĩ
        logger.warning("reason: không lập luận được, bỏ phần cho bác sĩ: %s", exc)
        reasoning = Reasoning()
    ranked, claims = verify_claims(reasoning, rows)
    ctx.turn_hypotheses = build_turn_hypotheses(ranked, hyps, rows)
    ranking = build_ranking(ranked, hyps)
    claim_dicts = [c.model_dump() for c in claims]
    await emit_tool_step(ctx, "reason", {"diseases": len(ranking)}, render_reasoning(ranking, claim_dicts, reasoning.need_more))
    return {"ranking": ranking, "claims": claim_dicts}


def build_answer_context(state: PreDiagnosisState) -> str:
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    urgency = state.get("urgency", "routine")
    lines = [f"Mức khẩn cấp: {_URGENCY_TEXT.get(urgency, urgency)}"]
    lines += [f"Dấu hiệu nguy hiểm: {f}" for f in state.get("red_flags", [])]
    told = "; ".join(f"{f.text} ({f.assertion})" for f in facts if f.source != "history")
    lines.append(f"Người bệnh đã kể: {told or '(chưa rõ)'}")
    if not state.get("ranking"):
        lines.append("Chưa đủ thông tin để gợi ý: khuyên người bệnh đến bác sĩ da liễu khám trực tiếp.")
    return "\n".join(lines)


async def conclude(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    # tên bệnh không đưa vào ngữ cảnh: người bệnh chỉ nhận lời dặn và mức khẩn cấp, phần giả thuyết dành cho bác sĩ
    return await reply(state, runtime.context, ANSWER.format(context=build_answer_context(state)))
