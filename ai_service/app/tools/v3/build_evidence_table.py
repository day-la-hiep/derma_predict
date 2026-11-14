import re
from datetime import datetime
from typing import Any

from app.state.v3.diagnosis import EvidenceRow, Hypothesis
from app.state.v3.facts import Fact, get_fact_weight

MISSING_KEEP = 5
# shortcut: fact chưa có node PrimeKG thì khớp chữ với tên phenotype, trọng số giảm một nửa; bỏ khi linking đủ tốt.
TEXT_MATCH_FACTOR = 0.5
_NON_WORD = re.compile(r"[^\w\s]")


def _norm(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def _text_match(fact: Fact, phenotype_name: str) -> bool:
    a, b = _norm(fact.text_en), _norm(phenotype_name)
    return bool(a) and bool(b) and (a in b or b in a)


def build_evidence_table(facts: list[Fact], profiles: dict[str, Any], hypotheses: list[Hypothesis], asked: list[str], now: datetime) -> list[EvidenceRow]:
    """Mỗi bệnh: phenotype khớp / thiếu (chưa hỏi) / mâu thuẫn và fact không giải thích được; điểm = Σ trọng số khớp − Σ trọng số mâu thuẫn."""
    present = [f for f in facts if f.assertion == "present" and f.slot not in ("location", "duration", "drug", "disease")]
    absent = [f for f in facts if f.assertion == "absent"]
    asked_set = set(asked)
    explained: set[int] = set()
    rows: list[EvidenceRow] = []
    for hyp in hypotheses:
        profile = profiles.get(hyp.disease_id) or {}
        positive = {f"effect/phenotype:{p['id']}": p for p in profile.get("positive", [])}
        negative = {f"effect/phenotype:{p['id']}": p for p in profile.get("negative", [])}
        names = {k: str(p["name"]) for k, p in {**positive, **negative}.items()}
        matched: list[str] = []
        contradicted: list[str] = []
        score = 0.0
        for idx, fact in enumerate(present):
            hit = fact.node_id if fact.node_id in positive else next((k for k, p in positive.items() if not fact.node_id and _text_match(fact, p["name"])), None)
            if hit and hit not in matched:
                factor = 1.0 if hit == fact.node_id else TEXT_MATCH_FACTOR
                matched.append(hit)
                score += float(positive[hit]["weight"]) * get_fact_weight(fact, now) * factor
                explained.add(idx)
            if fact.node_id in negative and fact.node_id not in contradicted:
                contradicted.append(fact.node_id)
                score -= float(negative[fact.node_id]["weight"])
        for fact in absent:
            if fact.node_id in positive and fact.node_id not in contradicted:
                contradicted.append(fact.node_id)
                score -= float(positive[fact.node_id]["weight"])
        known = {f.node_id for f in facts if f.node_id}
        missing = sorted((k for k in positive if k not in matched and k not in known and k not in asked_set),
                         key=lambda k: float(positive[k]["weight"]), reverse=True)[:MISSING_KEEP]
        rows.append(EvidenceRow(disease_id=hyp.disease_id, matched=matched, missing=missing, contradicted=contradicted, score=round(score, 3), names=names))
    unexplained = [present[i].node_name or present[i].text for i in range(len(present)) if i not in explained]
    return [row.model_copy(update={"unexplained": unexplained}) for row in rows]


def render_evidence_row(row: EvidenceRow, hyp: Hypothesis, with_ids: bool = False) -> str:
    """`with_ids`: kèm mã trong ngoặc vuông để LLM trích dẫn được (prompt khối 6)."""
    def names(ids: list[str]) -> str:
        return ", ".join(f"{row.names.get(i, i)} [{i}]" if with_ids else row.names.get(i, i) for i in ids) or "—"

    signals = " | ".join(f"{k.upper()} {v:.2f}" for k, v in hyp.signals.items())
    lines = [
        f"[{hyp.name} | {hyp.disease_id}{' | ' + signals if signals else ''}]",
        f" Khớp: {names(row.matched)}",
        f" Thiếu: {names(row.missing)}",
        f" Mâu thuẫn: {names(row.contradicted)}",
        f" Không giải thích được: {', '.join(row.unexplained) or '—'}",
    ]
    for note in row.guideline:
        lines.append(f" Sách [{note.chunk_id}] {'ủng hộ' if note.stance == 'support' else 'phản bác'} '{note.fact}': \"{note.quote}\"")
    return "\n".join(lines)
