from collections.abc import Callable
from typing import Any

from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]

from app.context.agent_context import AgentContext
from app.graph.v2.pre_diagnosis_graph import build_pre_diagnosis_graph as build_v2
from app.graph.v3.pre_diagnosis_graph import build_pre_diagnosis_graph as build_v3
from app.state.v2.pre_diagnosis_state import DIAG_KEYS as V2_DIAG_KEYS
from app.state.v3.pre_diagnosis_state import DIAG_KEYS as V3_DIAG_KEYS

Builder = Callable[[], CompiledStateGraph[Any, AgentContext, Any, Any]]

_VERSIONS: dict[str, tuple[Builder, tuple[str, ...]]] = {
    "v2": (build_v2, V2_DIAG_KEYS),
    "v3": (build_v3, V3_DIAG_KEYS),
}


def get_pre_diagnosis(version: str) -> tuple[Builder, tuple[str, ...]]:
    if version not in _VERSIONS:
        raise ValueError(f"AGENT_PRE_DIAGNOSIS_VERSION={version!r} không hợp lệ, chọn một trong {sorted(_VERSIONS)}")
    return _VERSIONS[version]
