import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.graph.v3.conclude import reply
from app.middleware.tool_step_events import emit_tool_step
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact, merge_facts
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.image_analysis import vlm_verify
from app.tools.v3.phrase_question import build_ask_prompt
from app.tools.v3.select_discriminator import select_discriminator

logger = logging.getLogger(__name__)

_VISUAL_KINDS = ("discriminate", "missing")
IMAGE_CONFIDENCE = 0.6


async def ask(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    question: dict[str, Any] = dict(state.get("question") or {})
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    asked = list(state.get("asked", []))
    out: dict[str, Any] = {}

    # dấu hiệu nhìn được thì hỏi ảnh trước (tối đa 1 lần mỗi lượt); ảnh trả lời rõ thì chọn câu hỏi khác cho người bệnh
    if question.get("kind") in _VISUAL_KINDS and ctx.image_keys:
        try:
            seen = await vlm_verify(ctx.image_keys[0], question["text"])
        except Exception as exc:  # noqa: BLE001  # model ảnh lỗi: hỏi thẳng người bệnh
            logger.warning("ask: vlm_verify lỗi: %s", exc)
            seen = "unclear"
        if seen in ("yes", "no"):
            fact = Fact(slot="morphology", text=question["text"], text_en=question["text"], node_id=question.get("node_id"), node_name=question["text"],
                        source="image", assertion="present" if seen == "yes" else "absent", confidence=IMAGE_CONFIDENCE,
                        time=datetime.now(timezone.utc), provenance=[ctx.image_keys[0]])
            facts = merge_facts(facts, [fact])
            asked.append(question.get("node_id") or question["text"])
            await emit_tool_step(ctx, "vlm_verify", {"phenotype": question["text"]}, f"Ảnh: {'có' if seen == 'yes' else 'không có'} {question['text']}")
            hyps = [Hypothesis.model_validate(x) for x in state.get("hypotheses", [])]
            rows = [EvidenceRow.model_validate(x) for x in state.get("evidence", [])]
            question = await select_discriminator(facts, state.get("ambiguous", []), hyps, rows, asked) or {}
            out["facts"] = [f.model_dump(mode="json") for f in facts]

    out |= await reply(state, ctx, build_ask_prompt(question or None, state.get("image_issues", [])))
    # ghi lại để lượt sau không hỏi lại đúng câu này
    if question.get("node_id"):
        asked.append(question["node_id"])
    return {**out, "rounds": state.get("rounds", 0) + 1, "asked": asked, "question": question}
