from typing import Any

from app.common.clinical_codes import normalize_body_site, normalize_code
from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.tools.v3.reason_cot import DiseaseReasoning

MISSING_KEEP = 3


def build_turn_hypotheses(ranked: list[DiseaseReasoning], hypotheses: list[Hypothesis], evidence: list[EvidenceRow]) -> list[dict[str, Any]]:
    """Giả thuyết đã kiểm chứng → dạng clinical_service đang nhận từ v2 (`disease, code, body_site, confidence, missing, evidence`), để tab bác sĩ hiển thị."""
    names = {h.disease_id: h.name for h in hypotheses}
    rows = {r.disease_id: r for r in evidence}
    out: list[dict[str, Any]] = []
    for item in ranked:
        row = rows[item.disease_id]
        notes = {n.chunk_id: n for n in row.guideline}
        name = names.get(item.disease_id, item.disease_id)
        site = normalize_body_site(item.body_site)
        evidence_items: list[dict[str, Any]] = []
        for cite in item.cites:
            if cite in notes:
                evidence_items.append({"source": "sách", "text": f"{notes[cite].fact}: {notes[cite].quote}"[:500], "ref": cite})
            else:
                kind = "khớp" if cite in row.matched else "mâu thuẫn"
                evidence_items.append({"source": "đồ thị tri thức", "text": f"{kind}: {row.names.get(cite, cite)}", "ref": cite})
        out.append({
            "disease": name, "code": normalize_code("", name).value, "body_site": site.value if site else "",
            "confidence": item.confidence, "missing": [row.names.get(m, m) for m in row.missing[:MISSING_KEEP]], "evidence": evidence_items,
        })
    return out


def build_ranking(ranked: list[DiseaseReasoning], hypotheses: list[Hypothesis]) -> list[dict[str, Any]]:
    by_id = {h.disease_id: h for h in hypotheses}
    return [
        {"disease_id": r.disease_id, "name": by_id[r.disease_id].name if r.disease_id in by_id else r.disease_id,
         "score": by_id[r.disease_id].score if r.disease_id in by_id else 0.0, "confidence": r.confidence, "cites": r.cites}
        for r in ranked
    ]
