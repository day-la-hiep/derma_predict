import asyncio
import logging
from typing import Any

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from agent.common.messages import get_dialogue_history, message_text
from agent.reasoning.retrieval_evidence import add_retrieval_evidence, get_tool_call_key, ground_hypotheses_in_evidence, label_tool_evidence
from agent.reasoning.patient_fact_extractor import LONG_TERM_TYPES, extract_facts, fact_key, facts_text, merge_facts
from agent.reasoning.structured_llm_calls import build_task_reminder, get_model_for_turn, get_model_retries, invoke_structured_with_retry
from agent.context.agent_context import AgentContext
from agent.graph.skin_image_nodes import join_images
from agent.graph.pre_diagnosis_schemas import PlanInput, ReflectInput
from agent.state.pre_diagnosis_state import PreDiagnosisState
from agent.middleware.patient_memory_prompt import inject_memory, load_memory
from agent.middleware.tool_step_events import REASONING_TOOL, emit_tool_start, emit_tool_step
from agent.prompt.pre_diagnosis_prompts import (
    ANSWER_FOUND,
    ANSWER_NONE,
    CHOOSE_SYSTEM,
    FINALIZE_REPORT_LINE,
    PLAN_SYSTEM,
    REFLECT_SYSTEM,
    format_clinical_block,
    format_evidence_digest,
    format_evidence,
    format_plan,
    render_initial_plan,
    render_reflection,
)

logger = logging.getLogger(__name__)

# Số vòng tra cứu tối đa mỗi lượt; hết thì `reflect` ép sang `answer` (không có trần thì model nhỏ cứ chọn tra cứu tiếp, mỗi vòng 30-60 giây).
MAX_TOOL_ROUNDS = 3

def _rounds_cap(ctx: AgentContext) -> int:
    return MAX_TOOL_ROUNDS if ctx.max_tool_rounds is None else ctx.max_tool_rounds


async def load_memory_node(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    # Node đầu của lượt: đọc memory một lần rồi để trong context; plan / choose_tools / reflect / answer chỉ nối chuỗi này vào prompt.
    ctx = runtime.context
    ctx.memory_text = await load_memory(runtime.store, ctx.patient_profile_id)
    ctx.image_result = asyncio.get_running_loop().create_future() if ctx.image_keys else None
    return {}


async def extract_facts_node(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    messages = state["messages"]
    # bảng là nguồn chính: giá trị trong DB (vd bác sĩ vừa xác nhận) đè giá trị cũ trong checkpoint
    known = merge_facts(state.get("facts", []), ctx.known_facts)
    upto = state.get("facts_upto", 0)
    if upto > len(messages):
        logger.warning("facts_upto=%d lớn hơn số tin nhắn %d, trích lại từ đầu", upto, len(messages))
        upto = 0
    fresh = get_dialogue_history(messages[upto:])
    transcript = [("PATIENT" if isinstance(m, HumanMessage) else "AI", str(m.text)) for m in fresh]
    new = await extract_facts(known, transcript, ctx.model or None)
    # Chỉ số trong lượt này vô nghĩa ở lượt sau: đổi sang id tin nhắn.
    for f in new:
        f["source_messages"] = [fresh[i - 1].id for i in f["source_messages"] if fresh[i - 1].id]
    merged = merge_facts(known, new)
    if new:
        await emit_tool_step(ctx, "extract_facts", {"new": len(new)}, facts_text(merged))
    # gửi Core: fact mới / đổi trong lượt + fact theo đợt còn chưa rõ vùng (chưa lưu được, Core gắn khi hội thoại đã có đợt)
    saved = {fact_key(f) for f in ctx.known_facts}
    pending = [
        f for f in merged
        if f.get("fact_type") not in LONG_TERM_TYPES and not f.get("body_site") and fact_key(f) not in saved
    ]
    ctx.turn_facts = list({fact_key(f): f for f in [*new, *pending]}.values())
    return {"facts": merged, "facts_upto": len(messages)}


async def plan(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    evidence = state.get("evidence", [])
    # extract_facts và nhánh ảnh chạy song song nên chỉ tới đây mới gộp được dữ kiện từ ảnh vào `facts`.
    facts = merge_facts(state.get("facts", []), state.get("image_facts", []))
    context = (
        f"{format_clinical_block(facts)}\n\n"
        f"Giả thuyết đã có căn cứ từ các lượt trước:\n{format_plan(state.get('plan', []), [])}\n\n"
        f"Đã tra cứu (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
        f"Bằng chứng đã thu được:\n{format_evidence_digest(evidence)}"
    )
    system = inject_memory(PLAN_SYSTEM.format(context=context), ctx.memory_text)
    await emit_tool_start(ctx, REASONING_TOOL, {"stage": "initial"})
    result = await invoke_structured_with_retry(ctx, PlanInput, [SystemMessage(content=system), *get_dialogue_history(state["messages"])])
    await emit_tool_step(ctx, REASONING_TOOL, {"stage": "initial"}, render_initial_plan(result))
    grounded = {h["disease"] for h in state.get("plan", [])}
    return {
        "unsupported": [h.disease for h in result.hypotheses if h.disease not in grounded],
        "queries": result.queries,
        "rounds": 0,
    }


def choose_tools_node(tools: list[Any]):
    async def choose_tools(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
        ctx = runtime.context
        context = (
            f"Giả thuyết hiện tại:\n{format_plan(state.get('plan', []), state.get('unsupported', []))}\n\n"
            f"Truy vấn dự định: {'; '.join(state.get('queries', []))}\n"
            f"Đã gọi (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
            f"Kết quả đã thu được (chỉ tra điều CÒN THIẾU, không tra lại điều đã có):\n{format_evidence_digest(state.get('evidence', []))}"
        )
        finalize_report = FINALIZE_REPORT_LINE if any(getattr(t, "name", "") == "search_finalize_report" for t in tools) else ""
        system = inject_memory(CHOOSE_SYSTEM.format(context=context, finalize_report=finalize_report), ctx.memory_text)
        model = get_model_for_turn(ctx).bind_tools(tools, tool_choice="any")
        base = [SystemMessage(content=system), *get_dialogue_history(state["messages"])]
        ai = AIMessage(content="")
        attempts = get_model_retries(ctx) + 1
        for attempt in range(attempts):
            result = await model.ainvoke([*base, build_task_reminder(error="lần trước chưa gọi tool nào" if attempt else None)])
            assert isinstance(result, AIMessage)
            ai = result
            if ai.tool_calls:
                break
            logger.warning("lần %d/%d: model không chọn tool nào dù tool_choice=any", attempt + 1, attempts)
        else:
            logger.warning("model không chọn tool nào sau %d lần thử, chuyển sang reflect", attempts)
        # Bỏ lệnh trùng với lệnh đã gọi (kể cả trùng trong cùng một lượt): gọi lại y hệt chỉ trả kết quả cũ.
        done = set(state.get("done_calls", []))
        fresh: list[Any] = []
        for c in ai.tool_calls:
            key = get_tool_call_key(c["name"], c["args"])
            if key in done:
                logger.warning("bỏ lệnh trùng với lệnh đã gọi: %s", key[:160])
                continue
            done.add(key)
            fresh.append(c)
        if ai.tool_calls and not fresh:
            logger.warning("mọi lệnh đều trùng lệnh đã gọi, bỏ qua tra cứu vòng này")
        if len(fresh) != len(ai.tool_calls):
            ai = ai.model_copy(update={"tool_calls": fresh})
        for c in fresh:
            await emit_tool_start(ctx, c["name"], c["args"])
        calls = [get_tool_call_key(c["name"], c["args"]) for c in fresh]
        # AIMessage chữ không kèm tool_calls không được vào lịch sử (sẽ bị `_history` tính nhầm là câu trả lời của trợ lý).
        return {
            "messages": [ai] if ai.tool_calls else [],
            "done_calls": [*state.get("done_calls", []), *calls],
            "rounds": state.get("rounds", 0) + 1,
            "new_calls": len(fresh),
        }

    return choose_tools


async def label_evidence_node(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    # Điểm hội tụ của lượt: gộp kết quả node ảnh (đã xong ở các bước trước) cùng kết quả tool trước khi `reflect`.
    joined = await join_images(state, runtime.context)
    evidence = list(joined.get("evidence", state.get("evidence", [])))
    out: dict[str, Any] = {k: v for k, v in joined.items() if k != "evidence"}
    messages = state["messages"]
    last_ai = max((i for i, m in enumerate(messages) if isinstance(m, AIMessage) and m.tool_calls), default=None)
    call_results = list(state.get("call_results", []))
    # `new_calls` = 0 khi `choose_tools` không chọn lệnh mới: kết quả tool trong messages là của vòng trước, đã gắn nhãn rồi.
    if last_ai is not None and state.get("new_calls"):
        ai = messages[last_ai]
        assert isinstance(ai, AIMessage)
        args_by_id = {c["id"]: c["args"] for c in ai.tool_calls}
        for m in messages[last_ai + 1 :]:
            if not isinstance(m, ToolMessage):
                continue
            name = m.name or ""
            args = args_by_id.get(m.tool_call_id)
            await emit_tool_step(runtime.context, name, args, m.content)
            items = label_tool_evidence(name, message_text(m))
            new = add_retrieval_evidence(evidence, items)
            call_results.append(f"{get_tool_call_key(name, args)} → {len(items)} mục, {new} mới")
    found = any(e["kind"] == "evidence" for e in evidence)
    return {**out, "evidence": evidence, "evidence_status": "found" if found else "none", "call_results": call_results}


async def reflect(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    evidence = state.get("evidence", [])
    rounds = state.get("rounds", 0)
    cap = _rounds_cap(ctx)
    exhausted = rounds >= cap
    budget = "Đã HẾT lượt tra cứu: next phải là \"answer\"." if exhausted else f"Đã tra cứu {rounds}/{cap} vòng."
    context = (
        f"{format_clinical_block(state.get('facts', []))}\n\n"
        f"evidence_status: {state.get('evidence_status', 'none')}\n"
        f"{budget}\n"
        f"Giả thuyết hiện tại:\n{format_plan(state.get('plan', []), state.get('unsupported', []))}\n"
        f"Đã gọi (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
        f"Bằng chứng và gợi ý truy xuất được:\n{format_evidence(evidence)}"
    )
    system = inject_memory(REFLECT_SYSTEM.format(context=context), ctx.memory_text)
    await emit_tool_start(ctx, REASONING_TOOL, {"stage": "after_evidence"})
    result = await invoke_structured_with_retry(ctx, ReflectInput, [SystemMessage(content=system), *get_dialogue_history(state["messages"])])
    plan_, unsupported, notes = ground_hypotheses_in_evidence(result.hypotheses, evidence)
    texts = {e["id"]: e for e in evidence}
    # mã E# chỉ có nghĩa trong lượt: lưu nội dung bằng chứng; lần reflect cuối của lượt là bản gửi về Core
    ctx.turn_hypotheses = [
        {
            **{k: h[k] for k in ("disease", "code", "body_site", "confidence", "missing")},
            "evidence": [{"source": texts[c]["source"], "text": texts[c]["text"][:500]} for c in h["cites"] if c in texts],
        }
        for h in plan_
    ]
    next_action = result.next
    if exhausted and next_action == "retrieve":
        next_action = "answer"
        notes.append(f"Đã hết {cap} vòng tra cứu nên chuyển sang trả lời")
        logger.warning("hết %d vòng tra cứu, ép sang answer", cap)
    await emit_tool_step(ctx, REASONING_TOOL, {"stage": "after_evidence"}, render_reflection(result, plan_, notes, next_action))
    return {"plan": plan_, "unsupported": unsupported, "queries": result.queries, "next": next_action}


async def answer(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    plan_ = state.get("plan", [])
    if plan_:
        cited = {c for h in plan_ for c in h["cites"]}
        context = (
            f"{format_clinical_block(state.get('facts', []))}\n\n"
            f"Giả thuyết:\n{format_plan(plan_, [])}\n\nBằng chứng:\n{format_evidence(state.get('evidence', []), cited)}"
        )
        base = ANSWER_FOUND.format(context=context)
    else:
        base = ANSWER_NONE.format(context=format_clinical_block(state.get("facts", [])))
    system = inject_memory(base, ctx.memory_text)
    ai = await get_model_for_turn(ctx).ainvoke([SystemMessage(content=system), *get_dialogue_history(state["messages"])])
    return {"messages": [ai]}
