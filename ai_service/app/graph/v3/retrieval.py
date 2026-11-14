import asyncio
import logging
from typing import Any

from langgraph.runtime import Runtime

from app.context.agent_context import AgentContext
from app.deps import get_knowledge_client
from app.state.v3.diagnosis import Hypothesis
from app.state.v3.pre_diagnosis_state import PreDiagnosisState
from app.tools.v3.guideline_search import search_by_disease
from app.tools.v3.ids import split_node_id

logger = logging.getLogger(__name__)

MAX_CACHED = 10


async def _chunks_for(hyp: Hypothesis) -> list[dict[str, Any]]:
    try:
        return await search_by_disease(hyp.disease_id, hyp.name)
    except Exception as exc:  # noqa: BLE001  # một bệnh lỗi thì bệnh khác vẫn có tài liệu
        logger.warning("retrieve: không lấy được guideline cho %s: %s", hyp.disease_id, exc)
        return []


async def retrieve(state: PreDiagnosisState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    hyps = [Hypothesis.model_validate(x) for x in state.get("hypotheses", [])]
    keep = {h.disease_id for h in hyps}
    # cache theo bệnh; bệnh rơi khỏi top thì bỏ cho diag khỏi phình
    profiles = {k: v for k, v in state.get("profiles", {}).items() if k in keep}
    chunks = {k: v for k, v in state.get("chunks", {}).items() if k in keep}
    need_profile = [h for h in hyps if h.disease_id not in profiles]
    need_chunks = [h for h in hyps if h.disease_id not in chunks]
    if need_profile:
        try:
            raw = await get_knowledge_client().get_disease_profiles([split_node_id(h.disease_id)[1] for h in need_profile])
            profiles |= {f"disease:{k}": v for k, v in raw.items()}
        except Exception as exc:  # noqa: BLE001  # không có hồ sơ thì bảng bằng chứng rỗng cho bệnh đó, vẫn còn guideline
            logger.warning("retrieve: không lấy được hồ sơ bệnh: %s", exc)
    for hyp, found in zip(need_chunks, await asyncio.gather(*(_chunks_for(h) for h in need_chunks)), strict=True):
        chunks[hyp.disease_id] = found
    # bệnh chỉ đến từ RAG chưa có tên: lấy tên trong hồ sơ
    named = [h.model_copy(update={"name": profiles[h.disease_id].get("name") or h.name}) if h.name == h.disease_id and h.disease_id in profiles else h for h in hyps]
    return {"profiles": dict(list(profiles.items())[:MAX_CACHED]), "chunks": dict(list(chunks.items())[:MAX_CACHED]),
            "hypotheses": [h.model_dump() for h in named]}
