# Debug luồng lập luận của agent, chạy graph trực tiếp (không qua API/RabbitMQ/SSE): cd core && .venv/bin/streamlit run agent/test/debug_app.py
import asyncio
import json
import logging
import queue
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.callbacks import AsyncCallbackHandler  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.common.llm import get_model  # noqa: E402
from agent.common.tracing import trace_callback  # noqa: E402
from agent.context.agent_context import AgentContext  # noqa: E402
from agent.graph.v2.nodes import MAX_MODEL_RETRIES, MAX_TOOL_ROUNDS  # noqa: E402
import agent.middleware.v1.model as v1_model  # noqa: E402
from agent.graph.chat_graph import build_chat_graph, config_for  # noqa: E402
from app.config.settings import settings  # noqa: E402

st.set_page_config(page_title="Debug lập luận agent", layout="wide")

SAVE_DIR = Path(__file__).resolve().parent / "debug_conversations"
logger = logging.getLogger("debug_app")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [debug_app] %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@st.cache_resource
def _defaults() -> dict[str, int]:
    # Chụp mức trần mặc định một lần: v1 được chỉnh bằng cách gán lại hằng số của module nên đọc lại sau đó sẽ ra giá trị đã chỉnh.
    return {
        "rounds": MAX_TOOL_ROUNDS,
        "retries": MAX_MODEL_RETRIES,
        "reasoning": v1_model.MAX_REASONING_RETRIES,
        "critic": v1_model.MAX_CRITIC_RETRIES,
        "recursion": 25,
    }


@st.cache_resource
def _loop() -> asyncio.AbstractEventLoop:
    # Client async của Qdrant/Neo4j/Redis gắn với một event loop, nên mọi lượt chạy chung một loop sống lâu thay vì asyncio.run mỗi lần.
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


@st.cache_resource
def _graph(version: str, triage: bool):
    settings.AGENT_TRIAGE_ENABLED = triage
    if version == "v2":
        from agent.graph.v2.pre_diagnosis_graph import build_pre_diagnosis_graph
    else:
        from agent.graph.v1.pre_diagnosis_graph import build_pre_diagnosis_graph
    return build_chat_graph(pre_diagnosis=build_pre_diagnosis_graph())


def _s(ms: Any) -> str:
    """Hiển thị mili-giây dưới dạng giây (dữ liệu thô vẫn lưu bằng ms)."""
    return f"{ms / 1000:.2f}s" if isinstance(ms, (int, float)) else "?"


def _text(m: Any) -> str:
    c = getattr(m, "content", m)
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, default=str)


class CallLog(AsyncCallbackHandler):
    """Ghi lại từng lần gọi LLM: node nào, system prompt, tools, tool_choice, đầu ra."""

    def __init__(self, t0: float) -> None:
        self.t0 = t0
        self.calls: list[dict[str, Any]] = []
        self.q: "queue.Queue[tuple[str, Any]] | None" = None
        self.tools: list[dict[str, Any]] = []
        self._parent: dict[str, str] = {}

    def _now(self) -> int:
        return int((time.time() - self.t0) * 1000)

    def _enclosing_tool(self, run_id: Any) -> str | None:
        """Tên tool chứa run này (đi ngược chuỗi run cha); None nếu lần gọi nằm trực tiếp trong node."""
        by_id = {t["run_id"]: t for t in self.tools}
        cur = self._parent.get(str(run_id))
        while cur:
            if cur in by_id:
                return by_id[cur]["name"]
            cur = self._parent.get(cur)
        return None

    async def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):  # type: ignore[override]
        if parent_run_id:
            self._parent[str(run_id)] = str(parent_run_id)

    async def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):  # type: ignore[override]
        if parent_run_id:
            self._parent[str(run_id)] = str(parent_run_id)
        self.tools.append(
            {
                "run_id": str(run_id),
                "name": kwargs.get("name") or (serialized or {}).get("name") or "tool",
                "t": self._now(),
                "input": str(kwargs.get("inputs") or input_str)[:2000],
                "output": "",
                "error": None,
                "in_tool": self._enclosing_tool(run_id),
            }
        )

    def _find_tool(self, run_id: Any) -> dict[str, Any] | None:
        return next((t for t in self.tools if t["run_id"] == str(run_id)), None)

    async def on_tool_end(self, output, *, run_id, **kwargs):  # type: ignore[override]
        t = self._find_tool(run_id)
        if t is not None:
            t["output"] = _text(output)[:4000]
            t["ms"] = self._now() - t["t"]

    async def on_tool_error(self, error, *, run_id, **kwargs):  # type: ignore[override]
        t = self._find_tool(run_id)
        if t is not None:
            t["error"] = f"{type(error).__name__}: {error}"
            t["ms"] = self._now() - t["t"]

    async def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, metadata=None, **kwargs):  # type: ignore[override]
        if parent_run_id:
            self._parent[str(run_id)] = str(parent_run_id)
        params = kwargs.get("invocation_params") or {}
        tools = [(t.get("function") or t).get("name", "?") for t in params.get("tools") or []]
        msgs: list[AnyMessage] = messages[0]
        self.calls.append(
            {
                "run_id": str(run_id),
                "t": int((time.time() - self.t0) * 1000),
                "node": (metadata or {}).get("langgraph_node", "?"),
                "model": params.get("model") or params.get("model_name") or "",
                "tools": tools,
                "tool_choice": params.get("tool_choice"),
                "system": "\n\n".join(_text(m) for m in msgs if isinstance(m, SystemMessage)),
                "messages": [(type(m).__name__, _text(m)[:3000]) for m in msgs if not isinstance(m, SystemMessage)],
                "output": "",
                "tool_calls": [],
                "usage": None,
                "error": None,
                "in_tool": self._enclosing_tool(run_id),
            }
        )

    def _find(self, run_id: Any) -> dict[str, Any] | None:
        return next((c for c in self.calls if c["run_id"] == str(run_id)), None)

    async def on_llm_end(self, response, *, run_id, **kwargs):  # type: ignore[override]
        call = self._find(run_id)
        if call is None:
            return
        msg = response.generations[0][0].message
        call["output"] = _text(msg)
        call["tool_calls"] = getattr(msg, "tool_calls", []) or []
        call["usage"] = getattr(msg, "usage_metadata", None)
        call["ms"] = int((time.time() - self.t0) * 1000) - call["t"]
        if self.q is not None:
            self.q.put(("llm", {"node": call["node"], "ms": call["ms"], "tools": [c["name"] for c in call["tool_calls"]], "output": call["output"][:300]}))

    async def on_llm_error(self, error, *, run_id, **kwargs):  # type: ignore[override]
        call = self._find(run_id)
        if call is not None:
            call["error"] = f"{type(error).__name__}: {error}"
            if self.q is not None:
                self.q.put(("llm", {"node": call["node"], "ms": 0, "tools": [], "output": "", "error": call["error"]}))


SIM_SYSTEM = """Bạn đóng vai BỆNH NHÂN thật đang nhắn tin với một trợ lý tư vấn da liễu, để thử nghiệm hệ thống.
Bạn mắc bệnh: {disease}
Thông tin ca bệnh của bạn:
{info}

Quy tắc:
* TUYỆT ĐỐI không nói tên bệnh trên và không dùng thuật ngữ y khoa; bạn chỉ là người bệnh bình thường, mô tả bằng lời thường ngày.
* Viết ĐÚNG MỘT tin nhắn tiếp theo của bệnh nhân, tiếng Việt tự nhiên, ngắn gọn (1-3 câu).
* Nếu chưa có tin nhắn nào: chỉ nêu lý do bạn nhắn (triệu chứng chính, vị trí), mơ hồ như người thật, chưa kể hết chi tiết.
* Nếu trợ lý vừa hỏi: trả lời đúng điều được hỏi dựa trên thông tin ca bệnh; điều không có trong thông tin thì nói "mình không rõ" hoặc "không có", không bịa thêm.
* Không tiết lộ những chi tiết trợ lý chưa hỏi (trừ khi nó tự nhiên đi kèm câu trả lời).
Chỉ trả về nội dung tin nhắn, không giải thích, không đặt trong dấu ngoặc kép."""

PRESET_CASES: dict[str, tuple[str, str]] = {
    "Viêm da tiếp xúc dị ứng": ("Viêm da tiếp xúc dị ứng", "Nữ 28 tuổi. Nổi mẩn đỏ, ngứa ở hai cẳng tay 3 ngày nay, sau khi đổi xà phòng/nước giặt mới. Ngứa tăng về đêm, có vài mụn nước nhỏ, da hơi phù nề. Không sốt, không đau, không lan nhanh. Không dị ứng thuốc. Chưa dùng thuốc gì."),
    "Mày đay cấp": ("Mày đay cấp", "Nam 35 tuổi. Nổi sẩn phù đỏ, ngứa khắp thân mình từ hôm qua sau khi ăn hải sản; từng mảng tự mất sau vài giờ rồi nổi chỗ khác. Không khó thở, không sưng môi hay mặt, không sốt. Trước đây từng bị dị ứng thức ăn nhẹ."),
    "Vảy nến mảng": ("Vảy nến thể mảng", "Nam 42 tuổi. Mảng da đỏ, có vảy trắng bạc dày ở khuỷu tay và đầu gối, kéo dài vài tháng, ngứa nhẹ, nặng hơn khi căng thẳng. Có vài mảng ở da đầu. Không đau khớp, không sốt. Chưa điều trị."),
    "Nấm da thân": ("Nấm da thân", "Nữ 22 tuổi. Mảng da hình tròn, viền đỏ có vảy, giữa nhạt màu, ở bụng và đùi, ngứa, 2 tuần nay và to dần. Hay ra mồ hôi, tập gym thường xuyên, nuôi mèo. Không sốt."),
    "Zona (cờ đỏ)": ("Zona thần kinh (herpes zoster)", "Nam 60 tuổi. Đau rát một bên ngực trái 2 ngày nay, sau đó nổi mụn nước thành chùm trên nền da đỏ thành dải, không vượt qua giữa người. Hơi sốt nhẹ, mệt. Có tiểu đường."),
}


async def _simulate(model: str, disease: str, info: str, history: list[dict[str, Any]]) -> str:
    transcript = "\n".join(f"{'Bệnh nhân' if m['role'] == 'user' else 'Trợ lý'}: {m['content'][:1500]}" for m in history[-10:]) or "(chưa có tin nhắn nào)"
    system = SIM_SYSTEM.format(disease=disease.strip() or "(một bệnh da liễu thường gặp, tự chọn và giữ nhất quán)", info=info.strip() or "(tự nghĩ ra thông tin hợp lý và giữ nhất quán)")
    reply = await get_model(model).ainvoke(
        [SystemMessage(content=system), HumanMessage(content=f"Đoạn hội thoại:\n{transcript}\n\nViết tin nhắn tiếp theo của bệnh nhân.")]
    )
    return _text(reply).strip().strip('"').strip()


def _summarize(update: Any) -> dict[str, Any]:
    if not isinstance(update, dict):
        return {"value": repr(update)[:300]}
    out: dict[str, Any] = {}
    for k, v in update.items():
        if k == "messages":
            out[k] = [
                {
                    "type": type(m).__name__,
                    "text": _text(m)[:2000],
                    **({"tool_calls": [f"{c['name']}({json.dumps(c['args'], ensure_ascii=False)[:200]})" for c in m.tool_calls]} if isinstance(m, AIMessage) and m.tool_calls else {}),
                    **({"tool": m.name} if isinstance(m, ToolMessage) else {}),
                }
                for m in v
            ]
        else:
            out[k] = v
    return out


async def _drive(graph: Any, payload: Any, config: RunnableConfig, ctx: AgentContext, log: CallLog, q: "queue.Queue[tuple[str, Any]]") -> None:
    t0 = log.t0
    # Input của một node = state tích luỹ trước khi áp dụng update của nó (theo từng graph con); lần đầu chỉ có tin nhắn đầu vào.
    initial = _summarize({"messages": payload["messages"]}) if isinstance(payload, dict) else {}
    acc: dict[str, dict[str, Any]] = {}
    try:
        async for ns, mode, chunk in graph.astream(payload, config=config, context=ctx, stream_mode=["updates", "custom"], subgraphs=True):
            ms = int((time.time() - t0) * 1000)
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    q.put(("token", chunk.get("text", "")))
                continue
            for node, update in chunk.items():
                if node == "__interrupt__":
                    q.put(("interrupt", update[0].value if update else {}))
                    continue
                ns_key = "/".join(p.split(":")[0] for p in ns)
                state = acc.setdefault(ns_key, json.loads(json.dumps(initial, default=str)))
                summary = _summarize(update)
                q.put(("node", {"t": ms, "ns": ns_key, "node": node, "input": json.loads(json.dumps(state, default=str)), "update": summary}))
                for k, v in summary.items():
                    if k == "messages":
                        state.setdefault("messages", []).extend(v)
                    else:
                        state[k] = v
        q.put(("done", None))
    except Exception:  # noqa: BLE001 — hiển thị traceback lên UI
        q.put(("error", traceback.format_exc()))


def _answer_of(events: list[dict[str, Any]]) -> str:
    for e in reversed(events):
        if e["node"] in ("pre_diagnosis", "triage"):
            for m in reversed(e["update"].get("messages", [])):
                if m["type"] == "AIMessage" and m["text"]:
                    return m["text"]
    return ""


def _preview(e: dict[str, Any]) -> str:
    """Một dòng xem nhanh kết quả của node khi đang stream."""
    u = e["update"]
    parts: list[str] = []
    for m in u.get("messages", []):
        if m.get("tool_calls"):
            parts.append("gọi " + ", ".join(m["tool_calls"])[:300])
        elif m["type"] == "ToolMessage":
            parts.append(f"kết quả `{m.get('tool', '?')}`: {m['text'][:160]!r}")
        elif m["text"]:
            parts.append(f"AI: {m['text'][:200]!r}")
    if "plan" in u:
        parts.append("giả thuyết: " + (", ".join(f"{h['disease'][:30]} ({h['confidence']}, {','.join(h['cites']) or '—'})" for h in u["plan"]) or "(không có)"))
    if u.get("unsupported"):
        parts.append("chưa có bằng chứng: " + ", ".join(x[:30] for x in u["unsupported"]))
    if "evidence" in u:
        ev = u["evidence"]
        parts.append(f"bằng chứng: {sum(1 for x in ev if x['kind'] == 'evidence')} evidence / {sum(1 for x in ev if x['kind'] == 'hint')} hint (status={u.get('evidence_status')})")
    if "next" in u:
        parts.append(f"next={u['next']}, queries={u.get('queries')}")
    if "queries" in u and "next" not in u:
        parts.append(f"queries={u['queries']}")
    if "rounds" in u:
        parts.append(f"vòng={u['rounds']}")
    return " · ".join(parts)[:700]


def _autosave() -> None:
    # Mỗi thread một file, ghi đè sau mỗi lượt nên lỡ tắt app hay lỗi giữa chừng vẫn còn đoạn chat.
    history = st.session_state["history"]
    thread = st.session_state["thread"]
    title = next((m["content"] for m in history if m["role"] == "user"), "")[:50]
    payload = {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "thread": thread, "title": title, "history": history}
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        (SAVE_DIR / f"auto_{thread}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        logger.warning("Không tự lưu được hội thoại: %s", exc)


def _node_calls(d: dict[str, Any], i: int) -> list[dict[str, Any]]:
    e = d["events"][i]
    prev = d["events"][i - 1]["t"] if i else -1
    return [c for c in d["calls"] if c["node"] == e["node"] and prev < c["t"] <= e["t"]]


def _context_text(d: dict[str, Any], i: int) -> str:
    """Bối cảnh node nhận: cấu hình lượt + (với node gọi LLM) system prompt / tools / tin nhắn thật sự gửi đi."""
    e = d["events"][i]
    lines = [f"## Cấu hình lượt\n{json.dumps(d['meta'], ensure_ascii=False, indent=2, default=str)}"]
    requested = next((m["tool_calls"] for m in reversed(e.get("input", {}).get("messages", [])) if m.get("tool_calls")), None)
    if e["node"] == "tools" and requested:
        lines.append("## Tool được yêu cầu\n" + "\n".join(requested))
    for n, c in enumerate(_node_calls(d, i), 1):
        lines.append(f"## Lần gọi LLM {n} (node {c['node']}, {_s(c.get('ms'))})")
        lines.append(f"model: {c['model']}\ntools: {', '.join(c['tools']) or '(không)'}\ntool_choice: {c['tool_choice']}")
        lines.append("--- system prompt ---\n" + (c["system"] or "(không có)"))
        lines.append("--- tin nhắn gửi kèm ---\n" + "\n".join(f"[{k}] {t}" for k, t in c["messages"]))
        lines.append("--- đầu ra ---\n" + (c["output"] or "(rỗng)"))
        if c["tool_calls"]:
            lines.append("--- tool_calls ---\n" + json.dumps(c["tool_calls"], ensure_ascii=False, indent=2, default=str))
        if c["error"]:
            lines.append("--- lỗi ---\n" + c["error"])
    return "\n\n".join(lines)


def _timeline_items(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Mọi thứ có mốc thời gian: node (suy từ lúc node trước xong), lần gọi LLM, lần chạy tool."""
    items: list[dict[str, Any]] = []
    last_end: dict[str, int] = {}
    for i, e in enumerate(d["events"]):
        start = last_end.get(e["ns"], 0)
        last_end[e["ns"]] = e["t"]
        items.append({"id": f"node-{i}", "kind": "node", "lane": f"node · {e['node']}", "start": start, "end": e["t"], "label": e["node"], "ref": i})
    for i, c in enumerate(d["calls"]):
        end = c["t"] + c.get("ms", 1)
        lane = f"LLM · {c['in_tool']} (nội bộ)" if c.get("in_tool") else f"LLM · {c['node']}"
        tool_names = ", ".join(x["name"] for x in c["tool_calls"])
        items.append({"id": f"llm-{i}", "kind": "llm", "lane": lane, "start": c["t"], "end": end, "label": f"{c['model'].split('/')[-1]} → {tool_names or 'văn bản'}", "ref": i})
    for i, t in enumerate(d.get("tools", [])):
        items.append({"id": f"tool-{i}", "kind": "tool", "lane": f"tool · {t['name']}", "start": t["t"], "end": t["t"] + t.get("ms", 1), "label": t["name"], "ref": i})
    return items


def _llm_detail(c: dict[str, Any]) -> None:
    if c.get("error"):
        st.error(c["error"])
    where = f" · nội bộ trong tool `{c['in_tool']}`" if c.get("in_tool") else ""
    st.markdown(f"**Model:** `{c['model']}` · **Tools gửi đi:** {', '.join(c['tools']) or '(không)'} · **tool_choice:** `{c['tool_choice']}`{where}")
    st.markdown("**System prompt** (đúng như model nhận):")
    st.code(c["system"] or "(không có)", language="markdown", wrap_lines=True)
    st.markdown("**Tin nhắn gửi kèm:**")
    st.code("\n".join(f"[{k}] {t}" for k, t in c["messages"]) or "(không có)", language="markdown", wrap_lines=True)
    st.markdown("**Đầu ra:**")
    st.code(c["output"] or "(rỗng)", language="markdown", wrap_lines=True)
    if c["tool_calls"]:
        st.json(c["tool_calls"])
    if c["usage"]:
        st.caption(f"token: {c['usage']}")


def _node_detail(d: dict[str, Any], i: int) -> None:
    e = d["events"][i]
    for label, text, lang in (
        ("Input (state trước node)", json.dumps(e.get("input", {}), ensure_ascii=False, indent=2, default=str), "json"),
        ("Output (update của node)", json.dumps(e["update"], ensure_ascii=False, indent=2, default=str), "json"),
        ("Context (cấu hình + prompt/tools node nhận)", _context_text(d, i), "markdown"),
    ):
        st.markdown(f"**{label}**")
        st.code(text, language=lang, wrap_lines=True)


def _tool_detail(t: dict[str, Any]) -> None:
    where = f" · nội bộ trong tool `{t['in_tool']}`" if t.get("in_tool") else ""
    st.markdown(f"**Tool:** `{t['name']}` · {_s(t.get('ms'))}{where}")
    if t["error"]:
        st.error(t["error"])
    st.markdown("**Input**")
    st.code(t["input"], language="json", wrap_lines=True)
    st.markdown("**Output**")
    st.code(t["output"] or "(chưa có / rỗng)", language="json", wrap_lines=True)


def _render_timeline(d: dict[str, Any], uid: str) -> None:
    items = _timeline_items(d)
    if not items:
        st.caption("Chưa có mốc thời gian nào.")
        return
    lanes = [lane for lane, _ in sorted({(it["lane"], it["start"]) for it in items}, key=lambda x: x[1]) ]
    order = list(dict.fromkeys(lanes))
    df = pd.DataFrame(
        [
            {
                **it,
                "start_s": round(it["start"] / 1000, 3),
                "end_s": round(it["end"] / 1000, 3),
                "draw_end_s": round(max(it["end"], it["start"] + 8) / 1000, 3),
                "dur_s": round((it["end"] - it["start"]) / 1000, 2),
            }
            for it in items
        ]
    )
    pick = alt.selection_point(name="pick", fields=["id"])
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadius=2)
        .encode(
            x=alt.X("start_s:Q", title="giây kể từ lúc bắt đầu lượt"),
            x2="draw_end_s:Q",
            y=alt.Y("lane:N", sort=order, title=None),
            color=alt.Color("kind:N", scale=alt.Scale(domain=["node", "llm", "tool"], range=["#9ca3af", "#3b82f6", "#16a34a"]), legend=alt.Legend(title=None)),
            opacity=alt.condition(pick, alt.value(1.0), alt.value(0.55)),
            tooltip=[
                alt.Tooltip("lane", title="làn"),
                alt.Tooltip("label", title="nhãn"),
                alt.Tooltip("start_s", title="bắt đầu (s)"),
                alt.Tooltip("end_s", title="kết thúc (s)"),
                alt.Tooltip("dur_s", title="thời lượng (s)"),
            ],
        )
        .add_params(pick)
        .properties(height=max(120, 28 * len(order)))
    )
    event = st.altair_chart(chart, on_select="rerun", key=f"tl-{uid}", width="stretch")
    st.caption("Bấm vào một thanh để xem chi tiết. Xám = node (suy từ lúc node trước kết thúc), xanh dương = lần gọi LLM, xanh lá = tool.")

    selected = None
    sel = (event.selection or {}).get("pick") if event is not None else None
    if sel:
        selected = sel[0].get("id")
    by_label = {f"{_s(it['start'])}–{_s(it['end'])} · {it['lane']} · {it['label']}": it["id"] for it in sorted(items, key=lambda x: (x["start"], x["lane"]))}
    labels = ["(chọn từ danh sách)", *by_label]
    default = next((i for i, (k, v) in enumerate(by_label.items(), 1) if v == selected), 0)
    choice = st.selectbox("Hoặc chọn từ danh sách", labels, index=default, key=f"tl-sel-{uid}-{selected}")
    target = selected or by_label.get(choice)
    if not target:
        return
    kind, idx = target.split("-")
    st.divider()
    if kind == "node":
        _node_detail(d, int(idx))
    elif kind == "llm":
        _llm_detail(d["calls"][int(idx)])
    else:
        _tool_detail(d["tools"][int(idx)])


def _render_debug(d: dict[str, Any], uid: str = "x") -> None:
    t_time, t_llm, t_reason, t_state = st.tabs(["Timeline", "Lần gọi LLM", "Bước lập luận / tool", "State sau mỗi node"])
    with t_time:
        _render_timeline(d, uid)
        with st.expander("Bảng node"):
            st.dataframe(
                [{"giây": round(e["t"] / 1000, 2), "graph": e["ns"] or "chat", "node": e["node"], "cập nhật": ", ".join(e["update"].keys())} for e in d["events"]],
                width="stretch",
            )
    with t_llm:
        if not d["calls"]:
            st.caption("Không có lần gọi LLM nào được ghi.")
        for i, c in enumerate(d["calls"], 1):
            tc = ", ".join(f"{x['name']}" for x in c["tool_calls"]) or "—"
            head = f"#{i} node `{c['node']}`{' › ' + c['in_tool'] if c.get('in_tool') else ''} · t={_s(c['t'])} · {_s(c.get('ms'))} · tool_choice={c['tool_choice']} · gọi: {tc}"
            with st.expander(head, expanded=False):
                _llm_detail(c)
    with t_reason:
        if not d["steps"]:
            st.caption("Chưa có bước nào (triage trả lời thẳng hoặc chưa tới bước tool).")
        for s in d["steps"]:
            with st.expander(s["title"], expanded=s["title"].startswith("Gọi tool: Lập luận") or "lập luận" in s["title"].lower()):
                if s.get("input"):
                    st.json(s["input"])
                st.text(s["content"])
    with t_state:
        st.caption("Mỗi khối có nút copy ở góc phải khi rê chuột vào.")
        with st.expander("Toàn bộ lượt (JSON, để copy một lần)"):
            st.code(
                json.dumps({"meta": d["meta"], "events": d["events"], "llm_calls": d["calls"], "tool_runs": d.get("tools", []), "steps": d["steps"]}, ensure_ascii=False, indent=2, default=str),
                language="json",
                wrap_lines=True,
            )
        for i, e in enumerate(d["events"]):
            with st.expander(f"{_s(e['t'])} · {e['ns'] or 'chat'} · {e['node']}"):
                for label, text, lang in (
                    ("Input (state trước node)", json.dumps(e.get("input", {}), ensure_ascii=False, indent=2, default=str), "json"),
                    ("Output (update của node)", json.dumps(e["update"], ensure_ascii=False, indent=2, default=str), "json"),
                    ("Context (cấu hình + prompt/tools node nhận)", _context_text(d, i), "markdown"),
                ):
                    st.markdown(f"**{label}**")
                    st.code(text, language=lang, wrap_lines=True)


# ----- sidebar: danh sách hội thoại -----
st.session_state.setdefault("history", [])
st.session_state.setdefault("thread", f"dbg-{uuid.uuid4()}")


def _conversation_list() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not SAVE_DIR.exists():
        return items
    for p in sorted(SAVE_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Không đọc được hội thoại %s: %s", p.name, exc)
            continue
        title = data.get("title") or next((m["content"] for m in data.get("history", []) if m["role"] == "user"), "")[:50]
        items.append({"stem": p.stem, "title": title or p.stem, "saved_at": data.get("saved_at", ""), "thread": data.get("thread"), "history": data.get("history", [])})
    return items


with st.sidebar:
    st.header("Hội thoại")
    if st.button("➕ Cuộc trò chuyện mới", width="stretch"):
        for k in ("history", "thread", "pending", "auto_left"):
            st.session_state.pop(k, None)
        st.rerun()
    current = f"auto_{st.session_state['thread']}"
    for c in _conversation_list():
        if st.button(f"{c['title']}\n{c['saved_at']}", key=f"open-{c['stem']}", type="primary" if c["stem"] == current else "secondary", width="stretch"):
            st.session_state["history"] = c["history"]
            # Bộ nhớ (checkpoint) của agent có thể đã mất; chat tiếp trên thread cũ vẫn ghi vào cùng file.
            st.session_state["thread"] = c["thread"] or f"dbg-{uuid.uuid4()}"
            for k in ("pending", "auto_left"):
                st.session_state.pop(k, None)
            st.rerun()

# Khung chat/cấu hình cao theo chiều cao cửa sổ (container(height=) chỉ nhận px cố định) và bỏ bớt khoảng trống mặc định của Streamlit.
st.markdown(
    """
    <style>
    .block-container {max-width: 100%; padding: 3.2rem 1.5rem 0 1.5rem;}
    header[data-testid="stHeader"]::before {content: "Debug luồng lập luận của agent"; position: absolute; left: 1.5rem; top: 50%; transform: translateY(-50%); font-size: 1.1rem; font-weight: 600;}
    [data-testid="stColumn"]:has(.st-key-chat_box) > [data-testid="stVerticalBlock"] {height: calc(100vh - 5rem); gap: 0.5rem;}
    [data-testid="stLayoutWrapper"]:has(> .st-key-chat_box) {flex: 1 1 0; min-height: 0;}
    [data-testid="stLayoutWrapper"]:has(> .st-key-input_box) {flex: 0 0 auto;}
    .st-key-chat_box {height: 100%; overflow-y: auto;}
    [data-testid="stColumn"]:has(.st-key-cfg_panel) > [data-testid="stVerticalBlock"] {height: calc(100vh - 5rem); gap: 0.5rem;}
    [data-testid="stLayoutWrapper"]:has(> .st-key-cfg_panel) {flex: 1 1 0; min-height: 0;}
    .st-key-cfg_panel {height: 100%; overflow-y: auto;}
    [data-testid="stMain"] {overflow: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)
main_col, cfg_col = st.columns([5, 2], gap="medium")
cfg_panel = cfg_col.container(border=True, key="cfg_panel")
chat_box = main_col.container(border=True, key="chat_box")
input_box = main_col.container(key="input_box")
with cfg_panel:
    tab_cfg, tab_sim = st.tabs(["Cấu hình", "Bệnh nhân giả lập"])

with tab_cfg:
    st.subheader("Cấu hình")
    version = st.radio("Graph", ["v1", "v2"], index=0 if settings.AGENT_GRAPH_VERSION == "v1" else 1, horizontal=True)
    choices = settings.AGENT_MODEL_CHOICES
    ids = list(choices)
    model_id = st.selectbox("Model", ids, index=ids.index(settings.AGENT_DEFAULT_MODEL_ID) if settings.AGENT_DEFAULT_MODEL_ID in ids else 0)
    triage_on = st.checkbox("Bật triage (lọc intent)", value=False, help="Tắt để mọi câu đều vào graph tiền chẩn đoán, dễ debug luồng lập luận.")
    user_id = st.text_input("user_id (memory)", "user-1")

with tab_cfg:
    D = _defaults()
    st.subheader("Mức trần")
    caps: dict[str, int] = {}
    if version == "v2":
        caps["max_tool_rounds"] = st.slider("Số vòng tra cứu tối đa", 1, 8, D["rounds"], key="cap_rounds", help="Mỗi vòng = choose_tools → tools → reflect. Hết vòng thì reflect ép sang answer.")
        caps["max_model_retries"] = st.slider("Retry khi model không gọi hàm", 0, 5, D["retries"], key="cap_retries", help="Áp dụng cho plan, reflect (structured output) và choose_tools. Hết lượt: plan/reflect báo lỗi, choose_tools chuyển sang reflect.")
    else:
        caps["reasoning_retries"] = st.slider("Retry ép/nhắc lập luận", 0, 5, D["reasoning"], key="cap_reasoning", help="MAX_REASONING_RETRIES của force_reasoning / enforce_initial_reasoning. Gán thẳng vào module nên áp dụng cho cả tiến trình Streamlit.")
        caps["critic_retries"] = st.slider("Số lần critic được yêu cầu viết lại", 0, 3, D["critic"], key="cap_critic", help="MAX_CRITIC_RETRIES: critic là chốt kiểm duyệt duy nhất ở cuối; 0 = tắt critic, 1 = được yêu cầu viết lại một lần.")
    caps["recursion_limit"] = st.number_input("recursion_limit (LangGraph)", 5, 200, D["recursion"], key="cap_recursion", help="Số superstep tối đa của một lượt; vượt thì GraphRecursionError. Đặt thấp để thử hành vi khi chạm trần cứng.")

    def _reset_caps() -> None:
        for key, name in (("cap_rounds", "rounds"), ("cap_retries", "retries"), ("cap_reasoning", "reasoning"), ("cap_critic", "critic"), ("cap_recursion", "recursion")):
            st.session_state[key] = D[name]

    st.button("Đặt lại mức trần mặc định", on_click=_reset_caps, width="stretch")
    st.divider()
    st.caption(f"Graph: {version} · model: `{choices[model_id]}`")


def _drain(live_state: dict[str, Any]) -> None:
    while True:
        try:
            kind, data = live_state["q"].get_nowait()
        except queue.Empty:
            return
        if kind == "node":
            live_state["events"].append(data)
        elif kind == "token":
            live_state["streamed"] += data


# Bất kỳ tương tác nào (kể cả nút Dừng) làm Streamlit chạy lại script và bỏ dở vòng chờ của lượt trước: huỷ tác vụ nền và lưu phần đã có vào lịch sử.
stale = st.session_state.pop("live", None)
if stale is not None:
    finished = stale["future"].done()
    if not finished:
        stale["future"].cancel()
        st.session_state["auto_left"] = 0
    _drain(stale)
    partial = stale["streamed"] or _answer_of(stale["events"])
    note = "" if finished else "\n\n_(Đã dừng trước khi graph chạy xong)_"
    st.session_state["history"].append(
        {
            "role": "assistant",
            "content": (partial or ("" if finished else "(Đã dừng, chưa có câu trả lời)")) + note,
            "debug": {"events": stale["events"], "calls": stale["log"].calls, "steps": list(stale["ctx"].reasoning_steps), "meta": stale["meta"], "tools": stale["log"].tools},
        }
    )
    logger.warning("lượt bị dừng/bỏ dở, lưu phần đã có")
    _autosave()

def _use_preset() -> None:
    disease, info = PRESET_CASES.get(st.session_state.get("case_preset", ""), ("", ""))
    if disease:
        st.session_state["case_disease"], st.session_state["case_info"] = disease, info


def _sim_reply(text_model: str, disease: str, info: str, history: list[dict[str, Any]]) -> str:
    try:
        return asyncio.run_coroutine_threadsafe(_simulate(choices[text_model], disease, info, history), _loop()).result(timeout=120)
    except Exception as exc:  # noqa: BLE001 — hiển thị lỗi lên UI
        st.error(f"Không sinh được câu trả lời giả lập: {type(exc).__name__}: {exc}")
        return ""


with tab_sim:
    with st.expander("🤖 Gắn một ca bệnh, LLM tự hỏi đáp với agent", expanded=True):
        st.selectbox("Ca mẫu", ["(tự nhập)", *PRESET_CASES], key="case_preset", on_change=_use_preset)
        case_disease = st.text_input("Bệnh thật (agent không thấy)", key="case_disease", placeholder="vd: Viêm da tiếp xúc dị ứng")
        case_info = st.text_area("Thông tin ca bệnh (bệnh nhân giả lập chỉ nói ra khi được hỏi)", key="case_info", height=130, placeholder="tuổi, giới, triệu chứng, vị trí, thời gian, tiền sử, thuốc đang dùng, cờ đỏ...")
        sim_model = st.selectbox("Model đóng vai bệnh nhân", ids, index=ids.index(model_id), key="sim_model")
        sim_turns = st.number_input("Số tin nhắn của bệnh nhân khi chạy tự động", 1, 10, 3, key="sim_turns", help="Gồm cả tin mở đầu. Sau mỗi câu trả lời của agent, bệnh nhân giả lập trả lời tiếp cho tới khi đủ số tin hoặc bạn bấm Dừng.")
        if st.button("▶ Chạy mô phỏng cả hội thoại (cuộc trò chuyện mới)", key="sim_run", type="primary"):
            with st.spinner("Bệnh nhân giả lập đang viết tin mở đầu..."):
                opening = _sim_reply(sim_model, case_disease, case_info, [])
            if opening:
                for k in ("history", "thread", "pending"):
                    st.session_state.pop(k, None)
                st.session_state["queued_prompt"] = opening
                st.session_state["auto_left"] = int(sim_turns) - 1
                st.rerun()
        st.caption("Hoặc làm từng bước thủ công:")
        if st.button("Sinh một câu trả lời từ hội thoại hiện tại", key="sim_gen"):
            with st.spinner("Đang sinh..."):
                generated = _sim_reply(sim_model, case_disease, case_info, st.session_state["history"])
            if generated:
                st.session_state["sim_text"] = generated
        st.text_area("Câu đã sinh (sửa được trước khi gửi)", key="sim_text")
        if st.button("Gửi câu này cho agent", key="sim_send") and st.session_state.get("sim_text", "").strip():
            st.session_state["auto_left"] = 0
            st.session_state["queued_prompt"] = st.session_state["sim_text"].strip()

# Một nút duy nhất ở ô nhập: "Gửi" khi rảnh, "Ngắt" khi đang chạy (bấm = Streamlit chạy lại script, nhánh stale ở trên sẽ huỷ lượt).
prompt: str | None = st.session_state.pop("queued_prompt", None)
with input_box:
    if prompt is None:
        with st.form("send", clear_on_submit=True, border=False):
            c_text, c_btn = st.columns([6, 1], vertical_alignment="bottom")
            typed = c_text.text_input("Tin nhắn", placeholder="Nhập câu hỏi cho agent...", label_visibility="collapsed")
            sent = c_btn.form_submit_button("Gửi ➤", type="primary", width="stretch")
        if sent and typed.strip():
            st.session_state["queued_prompt"] = typed.strip()
            st.rerun()
    else:
        c_text, c_btn = st.columns([6, 1], vertical_alignment="bottom")
        c_text.text_input("Tin nhắn", value=prompt, disabled=True, label_visibility="collapsed")
        c_btn.button("⏹ Ngắt", key="stop", type="primary", width="stretch")

with chat_box:
    for idx, m in enumerate(st.session_state["history"]):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("debug"):
                with st.expander("Debug lượt này", expanded=idx == len(st.session_state["history"]) - 1):
                    _render_debug(m["debug"], f"h{idx}")

    pending = st.session_state.get("pending")
    if pending:
        st.info(f"Agent đang hỏi lại: {pending.get('question', '')} {pending.get('options') or ''}")
    if prompt:
        st.session_state["history"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        graph = _graph(version, triage_on)
        ctx = AgentContext(
            user_id=user_id,
            conversation_id="",
            message_id=f"dbg-{uuid.uuid4().hex[:8]}",
            model=choices[model_id],
            max_tool_rounds=caps.get("max_tool_rounds"),
            max_model_retries=caps.get("max_model_retries"),
        )
        if version == "v1":
            v1_model.MAX_REASONING_RETRIES = caps["reasoning_retries"]
            v1_model.MAX_CRITIC_RETRIES = caps["critic_retries"]
        t0 = time.time()
        logger.info("lượt mới [%s, %s]: %s", version, choices[model_id], prompt[:120])
        log = CallLog(t0)
        config: RunnableConfig = {**config_for(st.session_state["thread"]), "callbacks": [trace_callback, log], "recursion_limit": int(caps["recursion_limit"])}
        payload: Any = Command(resume=prompt) if pending else {"messages": [HumanMessage(content=prompt)]}
        st.session_state.pop("pending", None)

        q: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        log.q = q
        future = asyncio.run_coroutine_threadsafe(_drive(graph, payload, config, ctx, log, q), _loop())
        meta = {"graph": version, "model": choices[model_id], "triage": triage_on, "user_id": user_id, "caps": caps, "message_id": ctx.message_id, "thread": st.session_state["thread"]}
        live_state: dict[str, Any] = {"q": q, "future": future, "events": [], "streamed": "", "log": log, "ctx": ctx, "meta": meta}
        st.session_state["live"] = live_state
        events: list[dict[str, Any]] = live_state["events"]

        lines: list[str] = []
        error = None
        interrupt = None
        with st.chat_message("assistant"):
            # Đồng hồ nằm ngoài `st.status`: cập nhật label của status mỗi 0,5 giây làm khung bị thu lại dù người dùng đang mở để đọc.
            clock = st.empty()
            status = st.status("Đang chạy...", expanded=True)
            progress = status.empty()
            out = st.empty()
            while True:
                try:
                    kind, data = q.get(timeout=0.5)
                except queue.Empty:
                    # Gọi st.* đều đặn (cập nhật đồng hồ) để Streamlit ngắt được vòng chờ này khi người dùng bấm Dừng.
                    clock.caption(f"⏱ Đang chạy... {int(time.time() - t0)}s")
                    continue
                if kind == "node":
                    events.append(data)
                    logger.info("node %s › %s (%s) %s", data["ns"] or "chat", data["node"], _s(data["t"]), _preview(data)[:150])
                    lines.append(f"- `{_s(data['t'])}` {data['ns'] or 'chat'} › **{data['node']}**: {_preview(data) or '(không có nội dung)'}")
                    progress.markdown("\n".join(lines))
                elif kind == "llm":
                    logger.info("  llm %s %s → %s%s", data["node"], _s(data["ms"]), ", ".join(data["tools"]) or "văn bản", f" LỖI {data['error']}" if data.get("error") else "")
                    err = f" ✖ {data['error']}" if data.get("error") else ""
                    called = f"gọi {', '.join(data['tools'])}" if data["tools"] else f"văn bản: {data['output'][:160]!r}"
                    lines.append(f"  - ↳ LLM (`{data['node']}`, {_s(data['ms'])}): {called}{err}")
                    progress.markdown("\n".join(lines))
                elif kind == "token":
                    live_state["streamed"] += data
                    out.markdown(live_state["streamed"] + "▌")
                elif kind == "interrupt":
                    interrupt = data
                elif kind == "error":
                    error = data
                    logger.error("Lỗi khi chạy graph:\n%s", data)
                    break
                elif kind == "done":
                    break
            st.session_state.pop("live", None)
            streamed = live_state["streamed"]
            clock.caption(f"⏱ Xong trong {_s(int((time.time() - t0) * 1000))}")
            status.update(label="Lỗi khi chạy" if error else "Đã chạy xong", state="error" if error else "complete", expanded=True)
            answer = streamed or _answer_of(events)
            if error:
                st.error("Lỗi khi chạy graph")
                st.code(error)
            elif interrupt is not None:
                st.session_state["pending"] = interrupt if isinstance(interrupt, dict) else {"question": str(interrupt)}
                answer = f"(agent hỏi lại) {st.session_state['pending'].get('question', '')}"
                out.markdown(answer)
            else:
                out.markdown(answer or "(không có câu trả lời)")
            debug = {"events": events, "calls": log.calls, "steps": list(ctx.reasoning_steps), "meta": live_state["meta"], "tools": log.tools}
            with st.expander("Debug lượt này", expanded=True):
                _render_debug(debug, f"n{len(st.session_state['history'])}")
        st.session_state["history"].append({"role": "assistant", "content": answer or (f"Lỗi khi chạy graph:\n```\n{error}\n```" if error else ""), "debug": debug})
        logger.info("xong lượt trong %s, %d LLM call, %d tool", _s(int((time.time() - t0) * 1000)), len(log.calls), len(log.tools))
        _autosave()

        left = st.session_state.get("auto_left", 0)
        if left > 0 and not error and interrupt is None:
            with st.spinner("Bệnh nhân giả lập đang trả lời..."):
                nxt = _sim_reply(sim_model, case_disease, case_info, st.session_state["history"])
            if nxt:
                st.session_state["auto_left"] = left - 1
                st.session_state["queued_prompt"] = nxt
                st.rerun()
            st.session_state["auto_left"] = 0
        elif left > 0:
            st.session_state["auto_left"] = 0
        # Chạy lại để thay nút Ngắt bằng ô nhập và cập nhật danh sách hội thoại bên trái.
        st.rerun()