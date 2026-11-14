import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from app.common.messages import message_text
from app.context.agent_context import AgentContext
from app.middleware.tool_step_events import emit_tool_step
from app.state.v3.facts import Fact, get_fact_key, merge_facts
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.extract_slots import Slot, extract_slots
from app.deps import get_knowledge_client
from app.tools.v3.image_analysis import classify_images, describe_image
from app.tools.v3.link_entities import Link, link_entities
from app.tools.v3.load_history import load_history

logger = logging.getLogger(__name__)

IMAGE_CONFIDENCE = 0.6
# Slot mà ảnh và lời kể cùng tả một thuộc tính của tổn thương: node khác nhau = mâu thuẫn cần hỏi lại.
CONFLICT_SLOTS = ("color", "morphology")


async def _safe(name: str, coro: Any, default: Any) -> Any:
    # Một nhánh của khối 0 lỗi (VLM, CNN, LLM) thì bỏ nhánh đó, các nhánh còn lại vẫn cho dữ kiện.
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("intake: nhánh %s lỗi: %s", name, exc)
        return default


def build_facts(slots: list[Slot], links: list[Link], message_ids: list[str], image_keys: list[str], now: datetime) -> list[Fact]:
    facts: list[Fact] = []
    for slot, link in zip(slots, links, strict=True):
        refs = message_ids if slot.source == "text" else image_keys
        provenance = [refs[slot.ref - 1]] if 1 <= slot.ref <= len(refs) and refs[slot.ref - 1] else []
        base = IMAGE_CONFIDENCE if slot.source == "image" else 1.0
        facts.append(Fact(
            slot=slot.slot, text=slot.text.strip(), text_en=slot.text_en.strip(), node_id=link.node_id, node_name=link.node_name,
            source=slot.source, assertion=slot.assertion, confidence=base * (link.confidence if link.node_id else 1.0), time=now,
            provenance=provenance,
        ))
    return facts


def get_conflict_keys(facts: list[Fact]) -> set[tuple[str, str]]:
    """Khoá fact mâu thuẫn giữa ảnh và lời kể; tính TRƯỚC khi gộp vì gộp giữ một fact mỗi khoá."""
    keys: set[tuple[str, str]] = set()
    by_key: dict[tuple[str, str], set[str]] = {}
    for f in facts:
        if f.source in ("text", "image") and f.assertion in ("present", "absent"):
            by_key.setdefault(get_fact_key(f), set()).add(f"{f.source}:{f.assertion}")
    # cùng một dấu hiệu mà một bên có, một bên không (vd người bệnh nói không có vảy, ảnh thấy vảy)
    keys |= {k for k, v in by_key.items() if {"text:absent", "image:present"} <= v or {"text:present", "image:absent"} <= v}
    # cùng slot màu / hình thái mà ảnh và lời kể ra node khác nhau
    for slot in CONFLICT_SLOTS:
        linked = [f for f in facts if f.slot == slot and f.node_id and f.assertion == "present"]
        text_nodes = {f.node_id for f in linked if f.source == "text"}
        image_nodes = {f.node_id for f in linked if f.source == "image"}
        if text_nodes and image_nodes and text_nodes != image_nodes:
            keys |= {get_fact_key(f) for f in linked if f.source in ("text", "image") and f.node_id not in text_nodes & image_nodes}
    return keys


def mark_conflicts(facts: list[Fact], keys: set[tuple[str, str]]) -> list[Fact]:
    return [f.model_copy(update={"conflict": True}) if get_fact_key(f) in keys else f for f in facts]


def render_facts(facts: list[Fact]) -> str:
    def line(f: Fact) -> str:
        node = f" → {f.node_name} ({f.node_id})" if f.node_id else " → (chưa khớp node)"
        flags = "".join([" [mâu thuẫn ảnh/lời kể]" if f.conflict else "", f" [{f.assertion}]" if f.assertion != "present" else ""])
        return f"- {f.slot}: {f.text}{node} · {f.source}{flags}"

    return "\n".join(line(f) for f in facts) or "(không có dữ kiện mới)"


async def _load_history(patient_id: str) -> list[dict[str, Any]]:
    return (await get_knowledge_client().get_patient_facts(patient_id))["facts"] if patient_id else []


async def _describe_all(keys: list[str]) -> tuple[list[Slot], list[str]]:
    results = await asyncio.gather(*(_safe("vision", describe_image(k, i), ([], None)) for i, k in enumerate(keys, 1)))
    slots = [s for found, _ in results for s in found]
    issues = [f"ảnh {i}: {issue}" for i, (_, issue) in enumerate(results, 1) if issue]
    return slots, issues


async def intake(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    now = datetime.now(timezone.utc)
    messages = state["messages"]
    upto = state.get("facts_upto", 0)
    if upto > len(messages):
        logger.warning("facts_upto=%d lớn hơn số tin nhắn %d, trích lại từ đầu", upto, len(messages))
        upto = 0
    fresh = [m for m in messages[upto:] if isinstance(m, HumanMessage) and message_text(m).strip()]
    known = [Fact.model_validate(x) for x in state.get("facts", [])]
    keys = ctx.image_keys
    first_turn = "facts_upto" not in state
    known_text = [f"{f.slot}: {f.text} ({f.assertion})" for f in known if f.source != "history"]

    # nhóm A song song: chữ ‖ mô tả ảnh ‖ CNN ‖ lịch sử (chỉ lượt đầu của hội thoại)
    text_slots, (image_slots, image_issues), cnn, graph_facts = await asyncio.gather(
        _safe("extract_slots", extract_slots(ctx, [message_text(m) for m in fresh], known_text), []),
        _describe_all(keys) if keys else asyncio.sleep(0, ([], [])),
        _safe("cnn", classify_images(keys), []) if keys else asyncio.sleep(0, []),
        _safe("history", _load_history(ctx.patient_profile_id), []) if first_turn else asyncio.sleep(0, []),
    )
    # nhóm B: link mọi slot (chữ + ảnh) trong một lượt
    slots: list[Slot] = [*text_slots, *image_slots]
    links: list[Link] = await _safe("link_entities", link_entities(ctx, slots), [Link(None, None, 0.0)] * len(slots))

    new = build_facts(slots, links, [m.id or "" for m in fresh], keys, now)
    history, history_diseases, recent_drugs = load_history(graph_facts, now)
    # lịch sử trước để lời kể của lượt này (source text) đè lên khi trùng khoá
    merged = mark_conflicts(merge_facts(merge_facts(history, known), new), get_conflict_keys([*known, *new]))
    ambiguous = [
        {"slot": s.slot, "text": s.text, "node_id": link.node_id, "node_name": link.node_name, "confidence": link.confidence}
        for s, link in zip(slots, links, strict=True) if link.ambiguous
    ]
    if new or cnn or image_issues:
        cnn_line = ", ".join(f"{c['label']} {c['prob']:.0%}" for c in cnn[:3])
        extra = [f"CNN: {cnn_line}"] if cnn_line else []
        await emit_tool_step(ctx, "intake", {"new": len(new), "images": len(keys)}, "\n".join([render_facts(new), *extra, *image_issues]))
    out: dict[str, Any] = {
        "facts": [f.model_dump(mode="json") for f in merged],
        "facts_upto": len(messages),
        "ambiguous": list({(a["slot"], a["text"]): a for a in [*state.get("ambiguous", []), *ambiguous]}.values()),
        "image_issues": image_issues,
    }
    if first_turn:
        out |= {"history_diseases": history_diseases, "recent_drugs": recent_drugs}
    if cnn:
        out["cnn_scores"] = cnn
    return out
