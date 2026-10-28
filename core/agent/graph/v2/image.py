import asyncio
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime

from agent.common.vision import VisionError, describe_skin_image
from agent.context.agent_context import AgentContext, ImageResult
from agent.common.fact_extractor import merge_facts
from agent.graph.v2.evidence import add_evidence
from agent.graph.v2.state import ImageState, PreDiagState
from agent.middleware.common.tool import emit_tool_step
from agent.tools.skin_image_classifier import get_predictor
from app.api.deps import get_file_store_service, get_finalize_report_index_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

MAX_IMAGES = 3
# Tạm tắt tra ca bệnh theo nhãn CNN top-1; bật lại thì làn ảnh thêm hint `search_finalize_report_by_image`.
SEARCH_CASES_BY_LABEL = False
_FACT_CHARS = 400


async def _load_image(key: str) -> bytes | None:
    data = await get_file_store_service().get_object_bytes(key)
    if data is None:
        logger.warning("không tìm thấy ảnh %s trong kho file", key)
    return data


async def _predict(data: bytes) -> list[dict[str, Any]]:
    # torch inference (CPU) đồng bộ: chạy thread riêng để không chặn event loop của worker.
    return await asyncio.to_thread(get_predictor().predict, data, 5)


async def _describe_image(data: bytes) -> str:
    return await describe_skin_image(data)


async def _search_cases(label: str) -> list[dict[str, Any]]:
    return await get_finalize_report_index_service().search_reports(query=label, limit=5)


def _step(name: str, fn: Any) -> StructuredTool:
    # Mỗi bước nhỏ nhất gọi qua tool (không đăng ký cho LLM) để callback ghi mốc thời gian vào trace / timeline UI test, dưới đúng node chứa nó.
    return StructuredTool.from_function(coroutine=fn, name=name, description=name)


_LOAD, _PREDICT, _DESCRIBE, _CASES = (
    _step("load_image", _load_image),
    _step("cnn_predict", _predict),
    _step("vision_describe", _describe_image),
    _step("search_cases", _search_cases),
)


async def _classify(key: str) -> dict[str, Any] | None:
    data = await _LOAD.ainvoke({"key": key})
    if data is None:
        return None
    try:
        top = await _PREDICT.ainvoke({"data": data})
    except Exception as exc:  # noqa: BLE001  # CNN lỗi (thiếu checkpoint, ảnh hỏng) không làm hỏng lượt chat
        logger.warning("CNN phân loại ảnh %s lỗi: %s", key, exc)
        return None
    return {"key": key, "top": top}


async def _describe(key: str) -> dict[str, Any] | None:
    data = await _LOAD.ainvoke({"key": key})
    if data is None:
        return None
    try:
        return {"key": key, "text": await _DESCRIBE.ainvoke({"data": data})}
    except VisionError as exc:
        logger.warning("model mô tả ảnh %s lỗi: %s", key, exc)
        return None


def _keys(runtime: Runtime[AgentContext]) -> list[str]:
    return runtime.context.image_keys[:MAX_IMAGES]


async def _cases(label: str) -> dict[str, Any]:
    try:
        cases = await _CASES.ainvoke({"label": label})
    except Exception as exc:  # noqa: BLE001  # Qdrant lỗi: bỏ nhánh ca bệnh, vẫn còn CNN và mô tả
        logger.warning("tra ca bệnh theo nhãn CNN '%s' lỗi: %s", label, exc)
        return {}
    return {"label": label, "cases": cases}


# Làn ảnh là subgraph `image_flow` chạy song song với làn chữ từ đầu lượt: mỗi subgraph có superstep riêng nên không chặn nhau
# (trong một graph phẳng, node cùng bước chặn bước kế). Kết quả trao cho `label_evidence` qua `ctx.image_result`.
async def image_cnn(state: ImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    results = [r for r in await asyncio.gather(*(_classify(k) for k in _keys(runtime))) if r]
    found = await _cases(results[0]["top"][0]["disease"]) if SEARCH_CASES_BY_LABEL and results and results[0]["top"] else {}
    return {"image_cnn": results, "image_cases": found}


async def image_vision(state: ImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    if not settings.AGENT_VISION_MODEL:
        return {}
    return {"image_vision": [r for r in await asyncio.gather(*(_describe(k) for k in _keys(runtime))) if r]}


def _top_text(top: list[dict[str, Any]]) -> str:
    return "; ".join(f"{r['disease']} {r['confidence'] * 100:.0f}%" for r in top)


def _cases_text(label: str, cases: list[dict[str, Any]]) -> str:
    rows = [f"{c.get('diagnosis')}: {str(c.get('doctor_reasoning') or '')[:120]}" for c in cases]
    return f"Ca bệnh có nhãn gần '{label}': " + " | ".join(rows)


def _candidates(cnn: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    """Nhãn CNN của mọi ảnh gộp theo bệnh (lấy độ tin cậy cao nhất), top `top_k`."""
    best: dict[str, float] = {}
    for r in cnn:
        for t in r["top"]:
            best[t["disease"]] = max(best.get(t["disease"], 0.0), float(t["confidence"]))
    return [{"disease": d, "confidence": c} for d, c in sorted(best.items(), key=lambda kv: -kv[1])[:top_k]]


async def image_done(state: ImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Cuối làn ảnh: gom kết quả CNN + mô tả (nhận định riêng của làn ảnh, chưa đối chiếu với lời người bệnh) đặt vào `ctx.image_result`."""
    cnn, vision, found = state.get("image_cnn", []), state.get("image_vision", []), state.get("image_cases")
    hints: list[tuple[str, dict[str, Any], str]] = [
        ("classify_skin_image", {"object_key": r["key"]}, "Phân loại ảnh (CNN): " + _top_text(r["top"])) for r in cnn
    ]
    hints += [("analyze_skin_image_multimodal", {"object_key": r["key"]}, r["text"]) for r in vision]
    if found and found.get("cases"):
        hints.append(("search_finalize_report_by_image", {"label": found["label"]}, _cases_text(found["label"], found["cases"])))
    facts = [
        {
            "template_label": f"Mô tả ảnh {i}",
            "fact_type": "image_finding",
            "detail": "(AI mô tả, chưa xác nhận) " + r["text"][:_FACT_CHARS],
            "source_messages": [],
        }
        for i, r in enumerate(vision, 1)
    ]
    future = runtime.context.image_result
    if future is not None and not future.done():
        future.set_result({"hints": hints, "facts": facts, "candidates": _candidates(cnn), "descriptions": [r["text"] for r in vision]})
    return {}


# shortcut: bảng tên tay cho 22 lớp của CNN (tiếng Anh + tiếng Việt thường gặp), lớp mới thì thêm vào đây; tên ngoài bảng chỉ so khớp theo chuỗi.
_ALIASES: dict[str, tuple[str, ...]] = {
    "Acne": ("acne", "mụn trứng cá"),
    "Actinic_Keratosis": ("actinic keratosis", "dày sừng quang hoá", "dày sừng quang hóa", "dày sừng ánh nắng"),
    "Benign_tumors": ("benign", "u lành", "u nang", "lipoma"),
    "Bullous": ("bullous", "pemphig", "bóng nước", "bọng nước"),
    "Candidiasis": ("candida", "nấm men"),
    "DrugEruption": ("drug eruption", "phát ban do thuốc", "dị ứng thuốc", "ban đỏ do thuốc"),
    "Eczema": ("eczema", "atopic", "viêm da cơ địa", "chàm", "contact dermatitis", "viêm da tiếp xúc"),
    "Infestations_Bites": ("scabies", "ghẻ", "côn trùng", "bite", "chấy", "rận"),
    "Lichen": ("lichen", "liken"),
    "Lupus": ("lupus",),
    "Moles": ("nốt ruồi", "mole", "nevus"),
    "Psoriasis": ("psoriasis", "vảy nến"),
    "Rosacea": ("rosacea", "trứng cá đỏ"),
    "Seborrh_Keratoses": ("seborrheic keratosis", "dày sừng tiết bã", "dày sừng bã"),
    "SkinCancer": ("ung thư da", "carcinoma", "melanoma", "skin cancer"),
    "Sun_Sunlight_Damage": ("sun damage", "tổn thương do nắng", "cháy nắng", "sunlight"),
    "Tinea": ("tinea", "nấm da", "hắc lào", "lang ben"),
    "Vascular_Tumors": ("hemangioma", "u mạch", "u máu"),
    "Vasculitis": ("vasculitis", "viêm mạch"),
    "Vitiligo": ("vitiligo", "bạch biến"),
    "Warts": ("wart", "mụn cóc"),
}


def _canon(name: str) -> str:
    """Tên bệnh về mã lớp CNN nếu khớp bảng tên (Việt hoặc Anh), không thì chuỗi chữ thường."""
    low = name.lower().replace("_", " ")
    for cls, aliases in _ALIASES.items():
        if cls.lower().replace("_", " ") in low or any(a in low for a in aliases):
            return cls
    return low.strip()


def cross_check(candidates: list[dict[str, Any]], descriptions: list[str], hypotheses: list[str]) -> str | None:
    """So nhận định của làn ảnh (nhãn CNN + mô tả) với giả thuyết của làn chữ; None khi làn chữ chưa có giả thuyết nào."""
    if not hypotheses or not (candidates or descriptions):
        return None
    cand = {_canon(c["disease"]): c for c in candidates}
    text = {_canon(h): h for h in hypotheses}
    described = " ".join(descriptions).lower()
    agree = [f"{text[k]} ~ {cand[k]['disease']} {cand[k]['confidence'] * 100:.0f}%" for k in text if k in cand]
    image_only = [f"{c['disease']} {c['confidence'] * 100:.0f}%" for k, c in cand.items() if k not in text]
    text_only = []
    for k, h in text.items():
        if k in cand:
            continue
        mentioned = k in _ALIASES and any(a in described for a in _ALIASES[k])
        text_only.append(h + (" (mô tả ảnh có nhắc tới)" if mentioned else " (ảnh không ủng hộ)"))
    lines = [
        "Kiểm tra chéo ảnh và mô tả của người bệnh (chỉ là gợi ý, vẫn cần bằng chứng E#):",
        "- Trùng khớp: " + ("; ".join(agree) or "(không có)"),
        "- Chỉ ảnh gợi ý: " + ("; ".join(image_only) or "(không có)"),
        "- Chỉ mô tả của người bệnh gợi ý: " + ("; ".join(text_only) or "(không có)"),
    ]
    return "\n".join(lines)


async def join_images(state: PreDiagState, ctx: AgentContext) -> dict[str, Any]:
    """Chờ làn ảnh (nếu có), rồi trả `evidence` / `facts` đã thêm gợi ý H# và dữ kiện ảnh; chỉ làm một lần mỗi lượt."""
    future = ctx.image_result
    if future is None:
        return {}
    result = await future
    ctx.image_result = None  # xoá sau khi nhận: `image_done` còn cần thấy Future này để đặt kết quả
    evidence = list(state.get("evidence", []))
    hints = list(result["hints"])
    # Bước gộp: lần đầu hai làn gặp nhau nên so chéo ở đây; làn ảnh chưa từng thấy lời người bệnh, làn chữ chưa từng thấy ảnh.
    hypotheses = [*state.get("unsupported", []), *(h["disease"] for h in state.get("plan", []))]
    checked = cross_check(result["candidates"], result["descriptions"], hypotheses)
    if checked:
        hints.append(("cross_check", {"hypotheses": hypotheses}, checked))
    for name, args, text in hints:
        add_evidence(evidence, [{"kind": "hint", "source": name, "text": text}])
        await emit_tool_step(ctx, name, args, text)
    return {"evidence": evidence, "facts": merge_facts(state.get("facts", []), result["facts"])}
