from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.common.clinical_codes import BODY_SITE_CHOICES
from app.context.agent_context import AgentContext
from app.prompt.v3.pre_diagnosis_prompts import REASON_COT
from app.reasoning.structured_llm_calls import invoke_structured_with_retry
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact
from app.tools.v3.build_evidence_table import render_evidence_row


class DiseaseReasoning(BaseModel):
    disease_id: str = Field(description="Mã bệnh như trong bảng (vd disease:5083)")
    summary: str = Field(default="", max_length=600)
    guideline_view: str = Field(default="", max_length=600)
    cnn_view: str = Field(default="", max_length=400)
    confidence: Literal["cao", "vừa", "thấp"] = "thấp"
    body_site: str = ""
    cites: list[str] = Field(default_factory=lambda: list[str]())


class Reasoning(BaseModel):
    """Bản ghi nội bộ: lập luận 4 bước trên bảng bằng chứng, cho bác sĩ đọc."""

    per_disease: list[DiseaseReasoning] = Field(default_factory=lambda: list[DiseaseReasoning]())
    need_more: list[str] = Field(default_factory=lambda: list[str]())


def build_reason_input(facts: list[Fact], hypotheses: list[Hypothesis], evidence: list[EvidenceRow], cnn: list[dict[str, Any]]) -> str:
    by_id = {h.disease_id: h for h in hypotheses}
    fact_lines = [f"- {f.slot}: {f.text}{' / ' + f.text_en if f.text_en else ''} ({f.assertion}, {f.source})" for f in facts]
    rows = [render_evidence_row(r, by_id[r.disease_id], with_ids=True) for r in evidence if r.disease_id in by_id]
    cnn_line = ", ".join(f"{c['label']} {c['prob']:.0%}" for c in cnn[:3]) or "(không có ảnh)"
    return "\n".join(["Dữ kiện:", *fact_lines, "", "Bảng bằng chứng:", *rows, "", f"CNN: {cnn_line}"])


async def reason_cot(ctx: AgentContext, facts: list[Fact], hypotheses: list[Hypothesis], evidence: list[EvidenceRow], cnn: list[dict[str, Any]]) -> Reasoning:
    system = REASON_COT.format(body_sites=BODY_SITE_CHOICES)
    return await invoke_structured_with_retry(ctx, Reasoning, [SystemMessage(content=system), HumanMessage(content=build_reason_input(facts, hypotheses, evidence, cnn))])
