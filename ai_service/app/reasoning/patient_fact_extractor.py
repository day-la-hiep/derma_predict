import hashlib
import json
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.common.llm import get_model
from app.common.vietnamese_text import tokenize

logger = logging.getLogger(__name__)

MAX_FACTS = 30
_MAX_ATTEMPTS = 2
DETAIL_MAX_CHARS = 300

# 5 nhóm dữ kiện (gộp từ mẫu khám 14 nhóm cũ): tên hiển thị cho prompt của agent
CATEGORY_TITLES = {1: "triệu chứng", 2: "tổn thương", 3: "đặc điểm", 4: "yếu tố tác động", 5: "tiền sử / thuốc"}
# Scope `body`: dữ kiện thuộc người bệnh (sốt, xét nghiệm), không gắn tổn thương
BODY_SCOPE = "body"
# Nhóm 3 chỉ giữ một giá trị tại một thời điểm cho mỗi tên thuộc tính (giá trị mới thay giá trị cũ)
SINGLE_VALUED_CATEGORIES = (3,)
_ATTRIBUTE_ALIASES = {"vị trí": "location", "vi tri": "location", "phân bố": "distribution", "sắp xếp": "arrangement", "diễn biến": "course"}
_OBJECT_TYPES = ("effect/phenotype", "disease", "drug", "exposure", "dermo")
_SCOPES = ("skin", "mucosa", "nail", "hair", "organ", BODY_SCOPE)
_EFFECTS = ("trigger", "aggravate", "relieve")
# Nhóm luôn là triệu chứng/hình thái: model hay bỏ trống `object_type` ở đây, mà thiếu thì fact không khớp được nút đồ thị
_DEFAULT_OBJECT_TYPE = {1: "effect/phenotype", 2: "effect/phenotype"}
# `fact_type` cũ của dữ liệu đã lưu trong checkpoint → nhóm
_LEGACY_CATEGORY = {"symptom": 1, "lesion": 2, "history": 5, "medication": 5, "allergy": 5, "other": 3}

FACT_SYSTEM = """Bạn là bộ phận trích DỮ KIỆN LÂM SÀNG nội bộ của hệ thống tư vấn da liễu. Người dùng không đọc đầu ra này: chỉ gọi hàm, KHÔNG chào hỏi, KHÔNG viết văn bản.

Từ đoạn hội thoại, nêu các dữ kiện MỚI hoặc ĐÃ THAY ĐỔI so với "Dữ kiện đã biết".
* Chỉ dựa vào lời người bệnh ([PATIENT]) hoặc ảnh người bệnh gửi. Dòng [AI] chỉ để hiểu ngữ cảnh (vd câu hỏi AI vừa hỏi), KHÔNG phải nguồn dữ kiện.
* Tuyệt đối không suy diễn, không thêm triệu chứng, tiền sử, mức độ mà người bệnh không nói.
* Dữ kiện đã biết mà không đổi thì KHÔNG nhắc lại. Dữ kiện bị người bệnh đính chính hoặc thay đổi thì trả lại ĐÚNG NGUYÊN VĂN nhãn đã biết (cùng `lesion`), `detail` là giá trị đầy đủ MỚI thay giá trị cũ (không nối thêm).
* Cùng ý với một dữ kiện đã biết thì dùng lại nguyên văn nhãn đó, không đặt nhãn mới (vd đã có "ngứa" thì không viết "ngứa da").
* Mỗi dữ kiện có `category` (số 1-5):
  1 triệu chứng (ngứa, đau, rát; toàn thân như sốt, mệt, đau khớp) · 2 tổn thương: hình thái (dát, sẩn, mụn nước, mảng, nốt, ban đỏ) với `kind` là primary; tổn thương thứ phát (vảy, vảy tiết, trợt, loét, sẹo, lichen hoá) với `kind` là secondary
  3 đặc điểm, mỗi tên chỉ một giá trị: `name` là tên đặc điểm, `template_label` là giá trị. `name` là `location` (vị trí, ghi đúng lời người bệnh) · `distribution` (đối xứng, rải rác, vùng hở) · `arrangement` (hình vòng, đường thẳng, chùm) · `course` (diễn biến: nhanh/chậm, từng đợt, tái phát, nặng lên/đỡ đi) · hoặc tên tự do (màu, kích thước, ranh giới, bề mặt, số lượng, tên xét nghiệm người bệnh kể lại)
  4 yếu tố tác động: `effect` là trigger | aggravate | relieve nếu là thứ làm tổn thương xuất hiện / nặng / đỡ (nắng, thức ăn, stress, thời tiết); để `effect` trống nếu là phơi nhiễm hoặc nguy cơ (nghề nghiệp, hoá chất / mỹ phẩm / chất tẩy, thú nuôi, nơi ở ẩm thấp, mang thai / cho con bú, cơ địa)
  5 tiền sử, thuốc đang dùng, dị ứng: `object_type` là disease hoặc drug; `of` là self | family; với thuốc `kind` là taking | allergy
* `scope`: skin | mucosa | nail | hair | organ cho tổn thương ở da, niêm mạc, móng, tóc, cơ quan khác; `body` cho dữ kiện của cả người bệnh, không thuộc tổn thương nào (sốt, mệt, kết quả xét nghiệm).
* `object_type` (để khớp với đồ thị tri thức): effect/phenotype cho nhóm 1 và 2; disease cho bệnh; drug cho thuốc; exposure cho hoá chất tiếp xúc; còn lại để trống.
* `present`: false khi người bệnh nói rõ KHÔNG có ("không ngứa", "không sốt"), kèm nhãn không phủ định ("ngứa", "sốt"). `resolved`: true khi người bệnh nói đã hết / khỏi.
* `onset_text`: chép nguyên cụm thời gian người bệnh nói về lúc bắt đầu ("từ tuần trước", "khoảng 3 ngày"); không tự tính ngày; không nói thì để trống.
* `lesion`: dữ kiện nhóm 1, 2, 3 và nhóm 4 có `effect` thuộc về một tổn thương (trừ khi `scope` là `body`). Nếu thuộc tổn thương đã biết thì ghi id của nó (cho ở "Tổn thương đã biết"). Nếu là tổn thương mới thì ghi một mã tạm bất kỳ (vd "moi-1") và dùng LẠI cùng mã đó cho mọi dữ kiện của tổn thương ấy trong lần trả lời này, kèm `site_text` là vị trí đúng lời người bệnh. Người bệnh tả nhiều vùng khác nhau thì mỗi vùng một tổn thương. Nhóm 5, nhóm 4 không có `effect` và dữ kiện `scope` là `body` thuộc về người bệnh, để `lesion` trống.
* Nhãn `template_label` ngắn (tối đa 8 từ); `detail` giữ đúng lời người bệnh về mức độ, thời điểm trong ngày... (tối đa 25 từ).
* Không có dữ kiện lâm sàng nào mới (chào hỏi, hỏi chung) thì trả danh sách rỗng.
* `source_messages`: số thứ tự `[#i]` của các tin [PATIENT] làm căn cứ; không bịa số."""


class ExtractedFact(BaseModel):
    template_label: str = Field(description="Tên ngắn của dữ kiện (tối đa 8 từ) theo lời người bệnh, vd 'ngứa', 'mụn nước', 'penicillin'")
    category: int = Field(description="Nhóm 1-5 như hướng dẫn")
    detail: str = Field(default="", description="Chi tiết đúng như người bệnh mô tả: mức độ, thời điểm trong ngày (tối đa 25 từ)")
    present: bool = True
    resolved: bool = False
    # chuỗi thay vì Literal: sai thì chuẩn hoá về mặc định thay vì bắt gọi lại
    object_type: str = ""
    name: str = ""
    kind: str = ""
    effect: str = ""
    of: str = ""
    lesion: str = ""
    site_text: str = ""
    scope: str = "skin"
    onset_text: str = ""
    source_messages: list[int] = Field(default_factory=list)


class ExtractedFacts(BaseModel):
    """Bản ghi NỘI BỘ của hệ thống, người dùng không đọc: chỉ điền các trường, không chào hỏi."""

    facts: list[ExtractedFact] = Field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(str(text).lower().split())


def get_category(fact: dict[str, Any]) -> int:
    """Nhóm của fact; fact lưu từ trước khi có nhóm (hoặc theo mẫu 14 nhóm cũ) thì suy từ `fact_type`."""
    category = fact.get("category")
    if isinstance(category, int) and 1 <= category <= 5:
        return category
    return _LEGACY_CATEGORY.get(str(fact.get("fact_type", "")), 3)


def derive_fact_type(category: int, object_type: str, kind: str, effect: str = "", on_body: bool = False) -> str:
    """Loại fact cũ (symptom, lesion, ...) để phần còn lại của agent và dữ liệu cũ dùng được."""
    if category == 1:
        return "symptom"
    if category == 2 or (category == 3 and not on_body):
        return "lesion"
    if category == 5:
        if object_type == "drug":
            return "allergy" if kind == "allergy" else "medication"
        return "history"
    if category == 4 and not effect:
        return "history"
    return "other"


def validate_facts_evidence(raw_facts: list[dict[str, Any]], messages_content: list[str]) -> list[dict[str, Any]]:
    """Lọc chỉ số tin nhắn sai, chuẩn hoá các trường và cảnh báo khi fact không trùng từ khoá nào với tin nguồn đã trích dẫn."""
    valid_facts: list[dict[str, Any]] = []
    total_messages = len(messages_content)

    for rf in raw_facts:
        f_label = str(rf.get("template_label", "")).strip()
        f_detail = str(rf.get("detail", "")).strip()
        category = rf.get("category")
        if not f_label or not isinstance(category, int) or not 1 <= category <= 5:
            logger.warning("bỏ dữ kiện '%s': nhóm '%s' không hợp lệ", f_label, category)
            continue
        source_indices = rf.get("source_messages") or []

        valid_indices: list[int] = []
        for idx in source_indices:
            if isinstance(idx, int) and 1 <= idx <= total_messages:
                valid_indices.append(idx)

        if valid_indices:
            source_text = " ".join(messages_content[i - 1] for i in valid_indices)
            source_tokens = tokenize(source_text)
            fact_tokens = tokenize(f"{f_label} {f_detail}")
            if fact_tokens and source_tokens and len(fact_tokens & source_tokens) == 0:
                logger.warning(
                    "Fact '%s' không khớp từ khóa với tin nhắn nguồn [#%s]",
                    f_label,
                    valid_indices,
                )

        object_type = str(rf.get("object_type", "")).strip()
        kind = str(rf.get("kind", "")).strip()
        rf["template_label"] = f_label
        rf["source_messages"] = valid_indices
        rf["detail"] = f_detail[:DETAIL_MAX_CHARS]
        rf["object_type"] = object_type if object_type in _OBJECT_TYPES else _DEFAULT_OBJECT_TYPE.get(category, "")
        name = _normalize(rf.get("name", ""))
        rf["name"] = _ATTRIBUTE_ALIASES.get(name, name) if category == 3 else name
        rf["scope"] = rf.get("scope") if rf.get("scope") in _SCOPES else "skin"
        rf["present"] = bool(rf.get("present", True))
        rf["resolved"] = bool(rf.get("resolved", False))
        rf["onset_text"] = str(rf.get("onset_text", "")).strip()
        rf["effect"] = rf.get("effect") if category == 4 and rf.get("effect") in _EFFECTS else ""
        if category == 2:
            rf["kind"] = "secondary" if kind == "secondary" else "primary"
        if category == 5:  # giá trị mặc định khớp cạnh trong graph để cùng khoá với fact đã lưu
            drug = rf["object_type"] == "drug"
            rf["of"] = "" if drug else ("family" if rf.get("of") == "family" else "self")  # `of` chỉ có ở tiền sử bệnh, không có ở thuốc
            rf["kind"] = ("allergy" if kind == "allergy" else "taking") if drug else ""
        rf["fact_type"] = derive_fact_type(category, rf["object_type"], rf.get("kind", kind), rf["effect"], rf["scope"] == BODY_SCOPE)
        rf["kg_node_id"] = None
        rf["link_method"] = "none"
        valid_facts.append(rf)

    return valid_facts


def has_lesion_subject(fact: dict[str, Any]) -> bool:
    """Fact có chủ thể là một tổn thương: nhóm 1-3 (trừ scope `body`) và yếu tố tác động có `effect`."""
    if fact.get("scope") == BODY_SCOPE:
        return False
    category = get_category(fact)
    return category in (1, 2, 3) or (category == 4 and bool(fact.get("effect")))


def assign_lesions(facts: list[dict[str, Any]], known_lesions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gắn id tổn thương cho fact cần chủ thể là tổn thương: id đã biết giữ nguyên, mã tạm đổi thành id mới (cùng mã = cùng tổn thương)."""
    known_ids = {str(les["id"]) for les in known_lesions}
    created: dict[str, str] = {}  # khoá chuẩn hoá của mã tạm / vị trí → id mới
    site_of: dict[str, str] = {}  # id mới → mô tả vị trí đầu tiên
    for f in facts:
        if not has_lesion_subject(f):
            f["lesion"] = ""
            continue
        ref = str(f.get("lesion", "")).strip()
        if ref in known_ids:
            continue
        site = str(f["template_label"]).strip() if get_category(f) == 3 and f.get("name") == "location" else str(f.get("site_text", "")).strip()
        key = _normalize(ref) or _normalize(site) or (str(known_lesions[-1]["id"]) if known_lesions else "mac-dinh")
        if key in known_ids:  # không có mã nhưng chỉ có một tổn thương gần nhất để gắn tạm
            f["lesion"] = key
            continue
        lesion_id = created.setdefault(key, uuid.uuid4().hex)
        if site and lesion_id not in site_of:
            site_of[lesion_id] = site
        f["lesion"] = lesion_id
    for f in facts:
        if f.get("lesion") in site_of:
            f["site_text"] = site_of[f["lesion"]]
    return facts


def fact_key(fact: dict[str, Any]) -> tuple[str, str, str]:
    """Khoá gộp: đặc điểm (nhóm 3) khoá theo tên nên giá trị mới thay giá trị cũ; tiền sử / thuốc kèm `of`, `kind`; còn lại khoá theo nhãn."""
    category = get_category(fact)
    if category in SINGLE_VALUED_CATEGORIES:
        part = _normalize(fact.get("name", ""))
    elif category == 5:
        part = f"{_normalize(fact.get('template_label', ''))}|{fact.get('of') or ''}|{fact.get('kind') or ''}"
    else:
        part = _normalize(fact.get("template_label", ""))
    return (str(category), str(fact.get("lesion") or ""), part)


def merge_facts(known: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gộp theo `fact_key`: fact mới ghi đè fact cũ cùng khoá; giữ tối đa `MAX_FACTS` mục mới nhất."""
    merged = {fact_key(f): f for f in known}
    for f in new:
        key = fact_key(f)
        merged.pop(key, None)
        merged[key] = f
    return list(merged.values())[-MAX_FACTS:]


def get_facts_fingerprint(facts: list[dict[str, Any]]) -> str:
    """Dấu vết ngắn của bộ fact: đổi khi thêm, sửa giá trị, đổi có/không hoặc đã hết; dùng để tool phụ thuộc fact không bị coi là "lệnh trùng"."""
    state = sorted((fact_key(f), str(f.get("detail", "")), bool(f.get("present", True)), bool(f.get("resolved", False))) for f in facts)
    return hashlib.sha1(json.dumps(state, ensure_ascii=False, default=str).encode()).hexdigest()[:8]


def facts_text(facts: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for f in facts:
        category = get_category(f)
        tags = CATEGORY_TITLES[category] + (f": {f['name']}" if f.get("name") and category == 3 else "")
        if f.get("site_text"):
            tags += f" @{f['site_text']}"
        label = f["template_label"] if f.get("present", True) else f"KHÔNG CÓ {f['template_label']}"
        label += " (đã hết)" if f.get("resolved") else ""
        onset = f" (khởi phát: {f['onset_text']})" if f.get("onset_text") else ""
        lines.append(f"- [{tags}] {label}: {f.get('detail', '')}{onset}")
    return "\n".join(lines) or "(chưa có)"


def build_fact_from_graph(graph_fact: dict[str, Any], lesions: list[dict[str, Any]]) -> dict[str, Any]:
    """Fact `GET /internal/patient-facts/{id}` → dạng fact nội bộ của agent (cùng khoá với fact trích từ chat để gộp đúng)."""
    category = graph_fact.get("category") or 3
    site = {str(les["id"]): les for les in lesions}.get(str(graph_fact.get("lesion_id") or ""), {})
    source = graph_fact.get("source_message_id")
    return {
        "template_label": graph_fact["label"],
        "fact_type": derive_fact_type(category, graph_fact.get("object_type") or "", graph_fact.get("kind") or "", graph_fact.get("effect") or "", not graph_fact.get("lesion_id")),
        "detail": graph_fact.get("detail") or "",
        "source_messages": [source] if source else [],
        "category": category,
        "present": graph_fact.get("present") is not False,
        "resolved": False,
        "object_type": graph_fact.get("object_type") or "",
        "name": graph_fact.get("name") or "",
        "kind": graph_fact.get("kind") or "",
        "effect": graph_fact.get("effect") or "",
        "of": graph_fact.get("of") or "",
        "lesion": graph_fact.get("lesion_id") or "",
        "site_text": site.get("site_text") or "",
        "scope": BODY_SCOPE if not graph_fact.get("lesion_id") and category in (1, 3) else site.get("scope") or "skin",
        "onset_text": graph_fact.get("onset_text") or "",
        "kg_node_id": graph_fact.get("kg_node_id"),
        "link_method": graph_fact.get("link_method") or "none",
    }


def build_graph_fact(fact: dict[str, Any]) -> dict[str, Any]:
    """Fact nội bộ → phần tử `facts` của `POST /internal/patient-facts/apply`."""
    sources = fact.get("source_messages") or []
    return {
        "category": get_category(fact),
        "label": fact["template_label"],
        "detail": fact.get("detail") or "",
        "name": fact.get("name") or "",
        "object_type": fact.get("object_type") or "",
        "kg_node_id": fact.get("kg_node_id"),
        "link_method": fact.get("link_method") or "none",
        "present": fact.get("present", True),
        "resolved": fact.get("resolved", False),
        "kind": fact.get("kind") or "",
        "effect": fact.get("effect") or "",
        "of": fact.get("of") or "",
        "lesion_id": fact.get("lesion") or None,
        "site_text": fact.get("site_text") or "",
        "scope": fact.get("scope") or "skin",
        "onset_text": fact.get("onset_text") or "",
        "source_message_id": sources[0] if sources else None,
    }


def lesions_text(lesions: list[dict[str, Any]]) -> str:
    return "\n".join(f"- [{les['id']}] {les.get('site_text') or '(chưa rõ vị trí)'}" for les in lesions) or "(chưa có)"


async def extract_facts(
    known: list[dict[str, Any]], transcript: list[tuple[str, str]], model: str | None = None, lesions: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """`transcript` là các cặp (người nói: "PATIENT" | "AI", nội dung) mới kể từ lần trích trước; trả fact mới/đổi, đã kiểm tra nguồn, [] khi lỗi."""
    if not any(who == "PATIENT" for who, _ in transcript):
        return []
    known_lesions = lesions or []
    lines = "\n".join(f"[#{i}][{who}]: {text}" for i, (who, text) in enumerate(transcript, 1))
    messages = [
        SystemMessage(content=FACT_SYSTEM),
        HumanMessage(
            content=f"Tổn thương đã biết:\n{lesions_text(known_lesions)}\n\nDữ kiện đã biết:\n{facts_text(known)}\n\n"
            f"Đoạn hội thoại mới:\n{lines}\n\nGọi hàm ExtractedFacts."
        ),
    ]
    structured = get_model(model).with_structured_output(ExtractedFacts, method="function_calling")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = await structured.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001  # model trả sai schema / lỗi mạng: không làm hỏng lượt chat
            logger.warning("lần %d/%d: không trích được dữ kiện: %s", attempt + 1, _MAX_ATTEMPTS, exc)
            continue
        if isinstance(result, ExtractedFacts):
            raw = [f.model_dump() for f in result.facts]
            valid = validate_facts_evidence(raw, [text for _, text in transcript])
            return assign_lesions(valid, known_lesions)
        logger.warning("lần %d/%d: model không trả ExtractedFacts (nhận %s)", attempt + 1, _MAX_ATTEMPTS, type(result).__name__)
    logger.warning("bỏ qua bước trích dữ kiện lượt này, giữ nguyên %d dữ kiện đã biết", len(known))
    return []
