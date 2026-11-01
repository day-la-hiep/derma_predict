import json
import logging
from typing import Any

from agent.common.evidence import JSON_RESULT_TOOLS
from agent.graph.v2.schemas import ReflectHypothesis

logger = logging.getLogger(__name__)

_MAX_TEXT = 600
# Kết quả phân loại ảnh / ca bệnh theo ảnh chỉ là gợi ý (giống graph v1: không tính là bằng chứng).
_HINT_TOOLS = {"classify_skin_image", "analyze_skin_image_multimodal", "search_finalize_report_by_image"}


def _clip(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:_MAX_TEXT]


def _source(item: dict[str, Any], fallback: str) -> str:
    parts = [str(item[k]) for k in ("title", "section") if item.get(k)]
    return ", ".join(parts) or fallback


def label_evidence(tool: str, content: str) -> list[dict[str, str]]:
    """Tách kết quả một tool thành các mục `{kind, source, text}`; `kind` do tên tool và nội dung quyết định, không do model."""
    if tool in JSON_RESULT_TOOLS:
        try:
            results = json.loads(content).get("results") or []
        except (ValueError, AttributeError) as exc:
            logger.warning("kết quả tool %s không phải JSON hợp lệ: %s", tool, exc)
            return []
        items: list[dict[str, str]] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            body = {k: v for k, v in r.items() if k not in ("rank", "score", "source")}
            kind = "evidence" if r.get("source") == "book" else "hint"
            items.append({"kind": kind, "source": _source(r, str(r.get("source", tool))), "text": _clip(body)})
        return items
    if tool == "search_finalize_report":
        try:
            data = json.loads(content)
        except ValueError as exc:
            logger.warning("kết quả tool %s không phải JSON hợp lệ: %s", tool, exc)
            return []
        if not data.get("evidence_found"):
            return []
        return [
            {"kind": "evidence", "source": "ca bệnh thực tế", "text": _clip({k: v for k, v in c.items() if k != "images"})}
            for c in data.get("cases") or []
            if isinstance(c, dict)
        ]
    if tool == "query_document_graph":
        try:
            triples = json.loads(content).get("triples") or []
        except (ValueError, AttributeError) as exc:
            logger.warning("kết quả tool %s không phải JSON hợp lệ: %s", tool, exc)
            return []
        items = []
        for t in triples:
            # Cạnh không có câu trích gốc thì không có gì để trích dẫn, nên không tính là bằng chứng.
            if not isinstance(t, dict) or not str(t.get("evidence") or "").strip():
                continue
            pages = ", ".join(str(p) for p in t.get("pages") or [])
            relation = t.get("display") or t.get("relation")
            text = f"{t.get('subject')} –{relation}→ {t.get('object')}: “{str(t['evidence']).strip()}”"
            items.append({"kind": "evidence", "source": "đồ thị sách" + (f", trang {pages}" if pages else ""), "text": _clip(text)})
        return items
    if tool in _HINT_TOOLS:
        return [{"kind": "hint", "source": tool, "text": _clip(content)}]
    return []


def add_evidence(evidence: list[dict[str, Any]], items: list[dict[str, str]]) -> int:
    """Thêm các mục chưa có (cùng loại, nguồn, đầu nội dung thì giữ mã cũ) vào `evidence` kèm mã E#/H#; trả số mục mới."""
    seen = {(e["kind"], e["source"], e["text"][:300]) for e in evidence}
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
    return new


def ground_hypotheses(
    hypotheses: list[ReflectHypothesis], evidence: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Giữ giả thuyết có ít nhất một mã bằng chứng hợp lệ (tồn tại và kind=evidence); trả `(plan, unsupported, notes)`."""
    kinds = {e["id"]: e["kind"] for e in evidence}
    plan: list[dict[str, Any]] = []
    unsupported: list[str] = []
    notes: list[str] = []
    for h in hypotheses:
        valid = [c for c in h.cites if kinds.get(c) == "evidence"]
        invalid = [c for c in h.cites if c not in valid]
        if invalid:
            reason = "không tồn tại hoặc chỉ là gợi ý"
            notes.append(f"{h.disease}: bỏ trích dẫn {', '.join(invalid)} ({reason})")
            logger.warning("giả thuyết %s trích dẫn không hợp lệ %s", h.disease, invalid)
        if not valid:
            notes.append(f"{h.disease}: không có bằng chứng hợp lệ nên bỏ khỏi kế hoạch")
            logger.warning("giả thuyết %s bị bỏ vì không có bằng chứng hợp lệ", h.disease)
            unsupported.append(h.disease)
            continue
        plan.append({"disease": h.disease, "confidence": h.confidence, "cites": valid, "missing": h.missing})
    return plan, unsupported, notes
