import logging

from app.state.v3.diagnosis import Claim, EvidenceRow
from app.tools.v3.reason_cot import DiseaseReasoning, Reasoning

logger = logging.getLogger(__name__)


def get_valid_cites(row: EvidenceRow) -> set[str]:
    return {*row.matched, *row.contradicted, *(n.chunk_id for n in row.guideline)}


def verify_claims(reasoning: Reasoning, evidence: list[EvidenceRow]) -> tuple[list[DiseaseReasoning], list[Claim]]:
    """Ý nào trích mã không có trong bảng bằng chứng của chính bệnh đó → "chưa kiểm chứng"; bệnh không còn ý kiểm chứng nào bị loại khỏi xếp hạng."""
    rows = {r.disease_id: r for r in evidence}
    kept: list[DiseaseReasoning] = []
    claims: list[Claim] = []
    for item in reasoning.per_disease:
        row = rows.get(item.disease_id)
        if row is None:
            logger.warning("verify_claims: bỏ %s vì không có trong bảng bằng chứng", item.disease_id)
            continue
        valid = get_valid_cites(row)
        cites = [c for c in item.cites if c in valid]
        if len(cites) < len(item.cites):
            logger.warning("verify_claims: %s trích mã không có trong bảng: %s", item.disease_id, sorted(set(item.cites) - valid))
        status = "verified" if cites else "unverified"
        for text in (item.summary, item.guideline_view, item.cnn_view):
            if text.strip():
                claims.append(Claim(text=f"[{item.disease_id}] {text.strip()}", cites=cites, status=status))
        if cites:
            kept.append(item.model_copy(update={"cites": cites}))
        else:
            logger.warning("verify_claims: loại %s khỏi xếp hạng vì không có ý nào kiểm chứng được", item.disease_id)
    return kept, claims
