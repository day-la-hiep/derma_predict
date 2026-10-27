import json
import logging
from typing import Any, TypeVar, cast

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel

from agent.common.evidence import message_text
from agent.common.fact_extractor import extract_facts, facts_text, merge_facts
from agent.common.llm import get_model
from agent.context.agent_context import AgentContext
from agent.graph.v2.evidence import ground_hypotheses, label_evidence
from agent.graph.v2.schemas import PlanInput, ReflectInput, render_plan, render_reflect
from agent.graph.v2.state import PreDiagState
from agent.middleware.common.model import inject_memory, load_memory
from agent.middleware.common.tool import emit_tool_step
from agent.prompt.v2 import ANSWER_FOUND, ANSWER_NONE, CHOOSE_SYSTEM, PLAN_SYSTEM, REFLECT_SYSTEM
from agent.tools.reasoning import TOOL_NAME as REASONING_TOOL

logger = logging.getLogger(__name__)

# Số lần gọi lại tối đa khi model viết văn bản thay vì gọi hàm (gemma qua OpenRouter hay bỏ qua tool_choice).
MAX_MODEL_RETRIES = 2
# Số vòng tra cứu tối đa mỗi lượt; hết thì `reflect` ép sang `answer` (không có trần thì model nhỏ cứ chọn tra cứu tiếp, mỗi vòng 30-60 giây).
MAX_TOOL_ROUNDS = 3

T = TypeVar("T", bound=BaseModel)


def _retries(ctx: AgentContext) -> int:
    return MAX_MODEL_RETRIES if ctx.max_model_retries is None else ctx.max_model_retries


def _rounds_cap(ctx: AgentContext) -> int:
    return MAX_TOOL_ROUNDS if ctx.max_tool_rounds is None else ctx.max_tool_rounds


def _model(ctx: AgentContext) -> BaseChatModel:
    return get_model(ctx.model or None)


def _task(name: str | None = None, error: object = None) -> HumanMessage:
    """Tin nhắn cuối nhắc nhiệm vụ: nếu tin cuối là lời người bệnh thì model trả lời họ (chào hỏi, đồng cảm) thay vì gọi hàm."""
    what = f"gọi hàm {name}" if name else "gọi các tool tra cứu phù hợp"
    hint = f" Lần trước chưa đạt: {str(error)[:300]}" if error else ""
    return HumanMessage(content=f"[Nhiệm vụ của hệ thống] Thực hiện nhiệm vụ nêu trong chỉ dẫn ở trên bằng cách {what}. KHÔNG chào hỏi, KHÔNG viết văn bản.{hint}")


async def _structured(ctx: AgentContext, schema: type[T], messages: list[AnyMessage]) -> T:
    structured = _model(ctx).with_structured_output(schema, method="function_calling", include_raw=True)
    error: object = None
    attempts = _retries(ctx) + 1
    for attempt in range(attempts):
        result = cast("dict[str, Any]", await structured.ainvoke([*messages, _task(schema.__name__, error)]))
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


def _history(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Chỉ lời người dùng và câu trả lời dạng chữ của các lượt trước; kết quả tool của lượt này đi vào prompt qua `evidence`."""
    return [
        m
        for m in messages
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and not m.tool_calls and m.text.strip())
    ]


def _call_key(name: str, args: Any) -> str:
    """Khoá chuẩn hoá của một lệnh gọi tool (khử trùng và hiển thị)."""
    return f"{name}({json.dumps(args, sort_keys=True, ensure_ascii=False)})"


def _digest(evidence: list[dict[str, Any]], limit: int = 12, chars: int = 220) -> str:
    rows = [f"[{e['id']}] ({e['kind']}, {e['source']}) {e['text'][:chars]}" for e in evidence[:limit]]
    if len(evidence) > limit:
        rows.append(f"... và {len(evidence) - limit} mục nữa")
    return "\n".join(rows) or "(chưa có)"


def _plan_text(plan: list[dict[str, Any]], unsupported: list[str]) -> str:
    lines = [f"- {h['disease']} ({h['confidence']}, nguồn: {', '.join(h['cites'])})" for h in plan]
    lines += [f"- {d} (chưa có bằng chứng hợp lệ)" for d in unsupported]
    return "\n".join(lines) or "(chưa có giả thuyết)"


def _evidence_text(evidence: list[dict[str, Any]], only: set[str] | None = None) -> str:
    rows = [f"[{e['id']}] ({e['kind']}, {e['source']}) {e['text']}" for e in evidence if only is None or e["id"] in only]
    return "\n".join(rows) or "(chưa có)"


async def load_memory_node(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    # Node đầu của lượt: đọc memory một lần rồi để trong context; plan / choose_tools / reflect / answer chỉ nối chuỗi này vào prompt.
    ctx = runtime.context
    ctx.memory_text = await load_memory(runtime.store, ctx.patient_profile_id)
    return {}


async def extract_facts_node(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    messages = state["messages"]
    known = state.get("facts", [])
    upto = state.get("facts_upto", 0)
    if upto > len(messages):
        logger.warning("facts_upto=%d lớn hơn số tin nhắn %d, trích lại từ đầu", upto, len(messages))
        upto = 0
    fresh = _history(messages[upto:])
    transcript = [("PATIENT" if isinstance(m, HumanMessage) else "AI", str(m.text)) for m in fresh]
    new = await extract_facts(known, transcript, ctx.model or None)
    # Chỉ số trong lượt này vô nghĩa ở lượt sau: đổi sang id tin nhắn.
    for f in new:
        f["source_messages"] = [fresh[i - 1].id for i in f["source_messages"] if fresh[i - 1].id]
    merged = merge_facts(known, new)
    if new:
        await emit_tool_step(ctx, "extract_facts", {"new": len(new)}, facts_text(merged))
    return {"facts": merged, "facts_upto": len(messages)}


async def plan(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    evidence = state.get("evidence", [])
    context = (
        f"Dữ kiện lâm sàng đã biết:\n{facts_text(state.get('facts', []))}\n\n"
        f"Giả thuyết đã có căn cứ từ các lượt trước:\n{_plan_text(state.get('plan', []), [])}\n\n"
        f"Đã tra cứu (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
        f"Bằng chứng đã thu được:\n{_digest(evidence)}"
    )
    system = inject_memory(PLAN_SYSTEM.format(context=context), ctx.memory_text)
    result = await _structured(ctx, PlanInput, [SystemMessage(content=system), *_history(state["messages"])])
    await emit_tool_step(ctx, REASONING_TOOL, {"stage": "initial"}, render_plan(result))
    grounded = {h["disease"] for h in state.get("plan", [])}
    return {
        "unsupported": [h.disease for h in result.hypotheses if h.disease not in grounded],
        "queries": result.queries,
        "rounds": 0,
    }


def choose_tools_node(tools: list[Any]):
    async def choose_tools(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
        ctx = runtime.context
        context = (
            f"Giả thuyết hiện tại:\n{_plan_text(state.get('plan', []), state.get('unsupported', []))}\n\n"
            f"Truy vấn dự định: {'; '.join(state.get('queries', []))}\n"
            f"Đã gọi (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
            f"Kết quả đã thu được (chỉ tra điều CÒN THIẾU, không tra lại điều đã có):\n{_digest(state.get('evidence', []))}"
        )
        system = inject_memory(CHOOSE_SYSTEM.format(context=context), ctx.memory_text)
        model = _model(ctx).bind_tools(tools, tool_choice="any")
        base = [SystemMessage(content=system), *_history(state["messages"])]
        ai = AIMessage(content="")
        attempts = _retries(ctx) + 1
        for attempt in range(attempts):
            result = await model.ainvoke([*base, _task(error="lần trước chưa gọi tool nào" if attempt else None)])
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
            key = _call_key(c["name"], c["args"])
            if key in done:
                logger.warning("bỏ lệnh trùng với lệnh đã gọi: %s", key[:160])
                continue
            done.add(key)
            fresh.append(c)
        if ai.tool_calls and not fresh:
            logger.warning("mọi lệnh đều trùng lệnh đã gọi, bỏ qua tra cứu vòng này")
        if len(fresh) != len(ai.tool_calls):
            ai = ai.model_copy(update={"tool_calls": fresh})
        calls = [_call_key(c["name"], c["args"]) for c in fresh]
        # AIMessage chữ không kèm tool_calls không được vào lịch sử (sẽ bị `_history` tính nhầm là câu trả lời của trợ lý).
        return {
            "messages": [ai] if ai.tool_calls else [],
            "done_calls": [*state.get("done_calls", []), *calls],
            "rounds": state.get("rounds", 0) + 1,
        }

    return choose_tools


async def label_evidence_node(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    messages = state["messages"]
    last_ai = max((i for i, m in enumerate(messages) if isinstance(m, AIMessage) and m.tool_calls), default=None)
    if last_ai is None:
        return {}
    ai = messages[last_ai]
    assert isinstance(ai, AIMessage)
    args_by_id = {c["id"]: c["args"] for c in ai.tool_calls}
    evidence = list(state.get("evidence", []))
    call_results = list(state.get("call_results", []))
    # Cùng một đoạn (cùng loại, nguồn, đầu nội dung) trả về ở nhiều lệnh / nhiều vòng chỉ giữ một mục với mã cũ.
    seen = {(e["kind"], e["source"], e["text"][:300]) for e in evidence}
    for m in messages[last_ai + 1 :]:
        if not isinstance(m, ToolMessage):
            continue
        name = m.name or ""
        args = args_by_id.get(m.tool_call_id)
        await emit_tool_step(runtime.context, name, args, m.content)
        items = label_evidence(name, message_text(m))
        new = 0
        for item in items:
            key = (item["kind"], item["source"], item["text"][:300])
            if key in seen:
                continue
            seen.add(key)
            new += 1
            prefix = "E" if item["kind"] == "evidence" else "H"
            n = sum(1 for e in evidence if e["id"].startswith(prefix)) + 1
            evidence.append({"id": f"{prefix}{n}", **item})
        call_results.append(f"{_call_key(name, args)} → {len(items)} mục, {new} mới")
    found = any(e["kind"] == "evidence" for e in evidence)
    return {"evidence": evidence, "evidence_status": "found" if found else "none", "call_results": call_results}


async def reflect(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    evidence = state.get("evidence", [])
    rounds = state.get("rounds", 0)
    cap = _rounds_cap(ctx)
    exhausted = rounds >= cap
    budget = "Đã HẾT lượt tra cứu: next phải là \"answer\"." if exhausted else f"Đã tra cứu {rounds}/{cap} vòng."
    context = (
        f"evidence_status: {state.get('evidence_status', 'none')}\n"
        f"{budget}\n"
        f"Giả thuyết hiện tại:\n{_plan_text(state.get('plan', []), state.get('unsupported', []))}\n"
        f"Đã gọi (kèm kết quả): {'; '.join(state.get('call_results', [])) or '(chưa)'}\n\n"
        f"Bằng chứng và gợi ý truy xuất được:\n{_evidence_text(evidence)}"
    )
    system = inject_memory(REFLECT_SYSTEM.format(context=context), ctx.memory_text)
    result = await _structured(ctx, ReflectInput, [SystemMessage(content=system), *_history(state["messages"])])
    plan_, unsupported, notes = ground_hypotheses(result.hypotheses, evidence)
    next_action = result.next
    if exhausted and next_action == "retrieve":
        next_action = "answer"
        notes.append(f"Đã hết {cap} vòng tra cứu nên chuyển sang trả lời")
        logger.warning("hết %d vòng tra cứu, ép sang answer", cap)
    await emit_tool_step(ctx, REASONING_TOOL, {"stage": "after_evidence"}, render_reflect(result, plan_, notes, next_action))
    return {"plan": plan_, "unsupported": unsupported, "queries": result.queries, "next": next_action}


async def answer(state: PreDiagState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    plan_ = state.get("plan", [])
    if plan_:
        cited = {c for h in plan_ for c in h["cites"]}
        context = f"Giả thuyết:\n{_plan_text(plan_, [])}\n\nBằng chứng:\n{_evidence_text(state.get('evidence', []), cited)}"
        base = ANSWER_FOUND.format(context=context)
    else:
        base = ANSWER_NONE.format(context="")
    system = inject_memory(base, ctx.memory_text)
    ai = await _model(ctx).ainvoke([SystemMessage(content=system), *_history(state["messages"])])
    return {"messages": [ai]}
