import logging
from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.middleware.tool_step_events import emit_tool_step
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.check_stop import should_stop
from app.tools.v3.red_flag_rules import check_red_flags, get_drug_flags, get_urgency
from app.tools.v3.select_discriminator import select_discriminator

logger = logging.getLogger(__name__)


async def check(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    hyps = [Hypothesis.model_validate(x) for x in state.get("hypotheses", [])]
    rows = [EvidenceRow.model_validate(x) for x in state.get("evidence", [])]
    recent_drugs = state.get("recent_drugs", [])
    flags = check_red_flags(facts, hyps, recent_drugs)
    try:
        flags += await get_drug_flags(facts, recent_drugs, hyps)
    except Exception as exc:  # noqa: BLE001  # ghi chú thuốc chỉ là phụ, luật cứng ở trên vẫn chạy
        logger.warning("check: không lấy được ghi chú thuốc: %s", exc)
    urgency = get_urgency(flags)

    question = await select_discriminator(facts, state.get("ambiguous", []), hyps, rows, state.get("asked", []))
    stop, reason = should_stop(hyps, rows, state.get("rounds", 0), question is not None)
    decision = "conclude" if stop else "ask"
    # cấp cứu: dặn đi khám ngay, không giữ người bệnh lại để hỏi thêm
    if urgency == "urgent":
        decision, reason = "conclude", "có dấu hiệu nguy hiểm, khuyên đi khám ngay"
    lines = [f"Quyết định: {'hỏi thêm' if decision == 'ask' else 'kết luận'} — {reason}", f"Mức khẩn cấp: {urgency}"]
    lines += [f"⚠ {f['name']}: {f['reason']}" for f in flags]
    if decision == "ask" and question:
        lines.append(f"Câu hỏi tiếp: {question['text']} ({question['kind']})")
    await emit_tool_step(ctx, "check", {"decision": decision}, "\n".join(lines))
    return {"decision": decision, "urgency": urgency, "red_flags": [f"{f['name']}: {f['reason']}" for f in flags], "question": question or {}}


def route_after_check(state: PreDiagnosisState) -> str:
    return "ask" if state.get("decision") == "ask" else "reason"
