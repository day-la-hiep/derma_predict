import asyncio
import logging
from typing import Any

from langgraph.runtime import Runtime

from app.reasoning.retrieval_evidence import add_retrieval_evidence
from app.tools.skin_image.cross_check import merge_cnn_candidates, format_similar_cases_hint, cross_check_image_against_hypotheses, format_cnn_top_labels
from app.context.agent_context import AgentContext
from app.state.pre_diagnosis_state import SkinImageState, PreDiagnosisState
from app.middleware.tool_step_events import emit_tool_step
from app.tools.skin_image.analysis import predict_skin_image_labels, describe_skin_image_with_vision, search_similar_cases_by_cnn_label
from app.config.settings import settings

logger = logging.getLogger(__name__)

MAX_IMAGES = 3
# Tạm tắt tra ca bệnh theo nhãn CNN top-1; bật lại thì làn ảnh thêm hint `search_finalize_report_by_image`.
SEARCH_CASES_BY_LABEL = False


def _keys(runtime: Runtime[AgentContext]) -> list[str]:
    return runtime.context.image_keys[:MAX_IMAGES]


# Làn ảnh là subgraph `image_flow` chạy song song với làn chữ từ đầu lượt: mỗi subgraph có superstep riêng nên không chặn nhau
# (trong một graph phẳng, node cùng bước chặn bước kế). Kết quả trao cho `label_evidence` qua `ctx.image_result`.
async def image_cnn(state: SkinImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    results = [r for r in await asyncio.gather(*(predict_skin_image_labels(k) for k in _keys(runtime))) if r]
    found = await search_similar_cases_by_cnn_label(results[0]["top"][0]["disease"]) if SEARCH_CASES_BY_LABEL and results and results[0]["top"] else {}
    return {"image_cnn": results, "image_cases": found}


async def image_vision(state: SkinImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    if not settings.AGENT_VISION_MODEL:
        return {}
    return {"image_vision": [r for r in await asyncio.gather(*(describe_skin_image_with_vision(k) for k in _keys(runtime))) if r]}


async def image_done(state: SkinImageState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Cuối làn ảnh: gom kết quả CNN + mô tả (nhận định riêng của làn ảnh, chưa đối chiếu với lời người bệnh) đặt vào `ctx.image_result`."""
    cnn, vision, found = state.get("image_cnn", []), state.get("image_vision", []), state.get("image_cases")
    hints: list[tuple[str, dict[str, Any], str]] = [
        ("classify_skin_image", {"object_key": r["key"]}, "Phân loại ảnh (CNN): " + format_cnn_top_labels(r["top"])) for r in cnn
    ]
    hints += [("analyze_skin_image_multimodal", {"object_key": r["key"]}, r["text"]) for r in vision]
    if found and found.get("cases"):
        hints.append(("search_finalize_report_by_image", {"label": found["label"]}, format_similar_cases_hint(found["label"], found["cases"])))
    # kết quả CNN theo ảnh gửi về Core (đợt bệnh), không còn thành fact image_finding
    runtime.context.turn_images = [
        {"storage_key": r["key"], "top_k": [{"label": t["disease"], "score": float(t["confidence"])} for t in r["top"]]}
        for r in cnn
    ]
    future = runtime.context.image_result
    if future is not None and not future.done():
        future.set_result({"hints": hints, "candidates": merge_cnn_candidates(cnn), "descriptions": [r["text"] for r in vision]})
    return {}


async def join_images(state: PreDiagnosisState, ctx: AgentContext) -> dict[str, Any]:
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
    checked = cross_check_image_against_hypotheses(result["candidates"], result["descriptions"], hypotheses)
    if checked:
        hints.append(("cross_check", {"hypotheses": hypotheses}, checked))
    for name, args, text in hints:
        add_retrieval_evidence(evidence, [{"kind": "hint", "source": name, "text": text}])
        await emit_tool_step(ctx, name, args, text)
    return {"evidence": evidence}
