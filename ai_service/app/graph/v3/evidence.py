import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.middleware.tool_step_events import emit_tool_step
from app.state.v3.diagnosis import EvidenceRow, GuidelineNote, Hypothesis
from app.state.v3.facts import Fact
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.annotate_guideline import MAX_DISEASES, annotate_guideline
from app.tools.v3.build_evidence_table import build_evidence_table, render_evidence_row

logger = logging.getLogger(__name__)

FUSE_SHARE = 0.7


async def _annotate(ctx: AgentContext, hyp: Hypothesis, facts: list[Fact], chunks: list[dict[str, Any]]) -> list[GuidelineNote]:
    try:
        return await annotate_guideline(ctx, hyp.name, facts, chunks)
    except Exception as exc:  # noqa: BLE001  # LLM lỗi: bệnh này chỉ còn bằng chứng đồ thị
        logger.warning("build_evidence: không đối chiếu được guideline cho %s: %s", hyp.disease_id, exc)
        return []


def rerank_by_evidence(hyps: list[Hypothesis], rows: list[EvidenceRow]) -> list[Hypothesis]:
    """Điểm cuối = 0.7 điểm gộp nguồn + 0.3 điểm bảng bằng chứng (chuẩn hoá theo bệnh cao nhất, âm tính là 0)."""
    by_id = {r.disease_id: r.score for r in rows}
    top = max((max(s, 0.0) for s in by_id.values()), default=0.0)
    rescored = [
        h.model_copy(update={"score": round(FUSE_SHARE * h.score + (1 - FUSE_SHARE) * (max(by_id.get(h.disease_id, 0.0), 0.0) / top if top else 0.0), 4)})
        for h in hyps
    ]
    return sorted(rescored, key=lambda h: h.score, reverse=True)


async def build_evidence(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    facts = [Fact.model_validate(x) for x in state.get("facts", [])]
    hyps = [Hypothesis.model_validate(x) for x in state.get("hypotheses", [])]
    rows = build_evidence_table(facts, state.get("profiles", {}), hyps, state.get("asked", []), datetime.now(timezone.utc))

    # chỉ chunk chưa đánh giá; ghi chú cũ giữ lại từ evidence của lượt trước
    annotated = set(state.get("annotated", []))
    old_notes = {r["disease_id"]: r.get("guideline", []) for r in state.get("evidence", [])}
    clinical = [f for f in facts if f.source != "history" and f.slot not in ("location", "duration")]
    targets = [(h, [c for c in state.get("chunks", {}).get(h.disease_id, []) if c["chunk_id"] not in annotated]) for h in hyps[:MAX_DISEASES]]
    results = await asyncio.gather(*(_annotate(ctx, h, clinical, cs) for h, cs in targets))
    new_notes = {h.disease_id: notes for (h, _), notes in zip(targets, results, strict=True)}
    rows = [
        r.model_copy(update={"guideline": [GuidelineNote.model_validate(n) for n in old_notes.get(r.disease_id, [])] + new_notes.get(r.disease_id, [])})
        for r in rows
    ]
    annotated |= {c["chunk_id"] for _, cs in targets for c in cs}

    ranked = rerank_by_evidence(hyps, rows)
    order = {h.disease_id: i for i, h in enumerate(ranked)}
    rows.sort(key=lambda r: order.get(r.disease_id, len(order)))
    by_id = {h.disease_id: h for h in ranked}
    if rows:
        await emit_tool_step(ctx, "build_evidence", {"diseases": len(rows)}, "\n\n".join(render_evidence_row(r, by_id[r.disease_id]) for r in rows))
    return {"evidence": [r.model_dump() for r in rows], "hypotheses": [h.model_dump() for h in ranked], "annotated": sorted(annotated)}
