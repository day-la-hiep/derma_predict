import asyncio
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from agent.context.agent_context import AgentContext
from agent.graph.v2 import image
from langchain.messages import AIMessage, HumanMessage

from agent.graph.v2.pre_diagnosis_graph import _after_choose, _after_memory, build_pre_diagnosis_graph


class _Store:
    async def get_object_bytes(self, key: str) -> bytes | None:
        return None if key == "missing" else b"img"


class _Predictor:
    def predict(self, data: bytes, k: int) -> list[dict[str, Any]]:
        return [{"disease": "Eczema", "confidence": 0.8}]


class _Index:
    async def search_reports(self, query: str, limit: int) -> list[dict[str, Any]]:
        return [{"diagnosis": "Eczema", "doctor_reasoning": "ngứa, khô da"}]


def _rt(keys: list[str]) -> Any:
    return SimpleNamespace(context=AgentContext(user_id="u", conversation_id="c", image_keys=keys))


def _patches(vision: str = "vision"):
    return (
        patch.object(image, "get_file_store_service", lambda: _Store()),
        patch.object(image, "get_predictor", lambda: _Predictor()),
        patch.object(image, "get_finalize_report_index_service", lambda: _Index()),
        patch.object(image, "describe_skin_image", AsyncMock(return_value="Mảng đỏ, có vảy")),
        patch.object(image, "emit_tool_step", AsyncMock()),
        patch.object(image.settings, "AGENT_VISION_MODEL", vision),
    )


async def _run_lane(rt: Any) -> dict[str, Any]:
    state: dict[str, Any] = {"messages": []}
    state.update(await image.image_cnn(cast(Any, state), rt))
    state.update(await image.image_vision(cast(Any, state), rt))
    await image.image_done(cast(Any, state), rt)
    return state


class ImageLaneTest(unittest.IsolatedAsyncioTestCase):
    async def test_join_builds_hints_and_facts_then_clears(self) -> None:
        rt = _rt(["a", "missing"])
        rt.context.image_result = asyncio.get_running_loop().create_future()
        p = _patches()
        with p[0], p[1], p[2], p[3], p[4], p[5]:
            state = await _run_lane(rt)
            out = await image.join_images(cast(Any, state), rt.context)
            again = await image.join_images(cast(Any, {**state, **out}), rt.context)
        self.assertEqual([e["id"] for e in out["evidence"]], ["H1", "H2"])  # tra ca bệnh đang tắt
        self.assertTrue(all(e["kind"] == "hint" for e in out["evidence"]))
        self.assertEqual(out["facts"][0]["fact_type"], "image_finding")
        self.assertEqual(again, {})  # vòng sau không gộp lại

    async def test_join_waits_for_lane(self) -> None:
        rt = _rt(["a"])
        rt.context.image_result = asyncio.get_running_loop().create_future()
        p = _patches()
        with p[0], p[1], p[2], p[3], p[4], p[5]:
            join = asyncio.create_task(image.join_images(cast(Any, {"messages": []}), rt.context))
            await asyncio.sleep(0.05)
            self.assertFalse(join.done())  # làn ảnh chưa xong thì label_evidence chờ
            await _run_lane(rt)
            out = await asyncio.wait_for(join, 1)
        self.assertEqual(len(out["evidence"]), 2)  # tra ca bệnh đang tắt

    async def test_vision_disabled_and_image_missing(self) -> None:
        rt = _rt(["missing"])
        rt.context.image_result = asyncio.get_running_loop().create_future()
        p = _patches(vision="")
        with p[0], p[1], p[2], p[3], p[4], p[5]:
            state = await _run_lane(rt)
            out = await image.join_images(cast(Any, state), rt.context)
        self.assertEqual(out["evidence"], [])
        self.assertEqual(out["facts"], [])

    async def test_no_image_lane_no_wait(self) -> None:
        self.assertEqual(await image.join_images({"messages": []}, _rt([]).context), {})


class CrossCheckTest(unittest.TestCase):
    cand = [{"disease": "Psoriasis", "confidence": 0.6}, {"disease": "Eczema", "confidence": 0.2}, {"disease": "Tinea", "confidence": 0.1}]

    def test_agree_image_only_text_only(self) -> None:
        text = image.cross_check(self.cand, ["Mảng đỏ, vảy bạc"], ["Vảy nến (Psoriasis)", "Viêm da tiếp xúc (Contact dermatitis)", "Lupus ban đỏ"])
        assert text is not None
        self.assertIn("Trùng khớp: Vảy nến (Psoriasis) ~ Psoriasis 60%", text)
        self.assertIn("Chỉ ảnh gợi ý: Tinea 10%", text)  # Eczema bị "Contact dermatitis" khớp theo bảng tên nên là trùng, Tinea chỉ ảnh có
        self.assertIn("Lupus ban đỏ (ảnh không ủng hộ)", text)

    def test_seborrheic_dermatitis_is_not_eczema(self) -> None:
        text = image.cross_check([{"disease": "Eczema", "confidence": 0.5}], [], ["Viêm da tiết bã (Seborrheic dermatitis)"])
        assert text is not None
        self.assertIn("Trùng khớp: (không có)", text)  # alias không được quá lỏng: cùng chữ "dermatitis" chưa phải cùng bệnh

    def test_nothing_to_compare(self) -> None:
        self.assertIsNone(image.cross_check(self.cand, [], []))  # làn chữ chưa có giả thuyết
        self.assertIsNone(image.cross_check([], [], ["Vảy nến"]))  # làn ảnh không có kết quả

    def test_description_mentions_text_hypothesis(self) -> None:
        text = image.cross_check([{"disease": "Eczema", "confidence": 0.5}], ["có vảy trắng như vảy nến"], ["Vảy nến"])
        assert text is not None
        self.assertIn("Vảy nến (mô tả ảnh có nhắc tới)", text)

    def test_candidates_merge_images_by_best_confidence(self) -> None:
        cnn = [{"key": "a", "top": [{"disease": "Eczema", "confidence": 0.3}]}, {"key": "b", "top": [{"disease": "Eczema", "confidence": 0.7}, {"disease": "Tinea", "confidence": 0.2}]}]
        self.assertEqual(image._candidates(cnn), [{"disease": "Eczema", "confidence": 0.7}, {"disease": "Tinea", "confidence": 0.2}])


class JoinCrossCheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_join_adds_cross_check_hint_from_text_hypotheses(self) -> None:
        rt = _rt(["a"])
        rt.context.image_result = asyncio.get_running_loop().create_future()
        p = _patches()
        with p[0], p[1], p[2], p[3], p[4], p[5]:
            state = await _run_lane(rt)
            out = await image.join_images(cast(Any, {**state, "unsupported": ["Eczema (Atopic dermatitis)"]}), rt.context)
        sources = [e["source"] for e in out["evidence"]]
        self.assertEqual(sources[-1], "cross_check")
        self.assertIn("Trùng khớp: Eczema (Atopic dermatitis) ~ Eczema", out["evidence"][-1]["text"])


class IsolationTest(unittest.TestCase):
    def test_image_state_has_no_text_keys(self) -> None:
        from agent.graph.v2.state import ImageState

        self.assertEqual(set(ImageState.__annotations__), {"image_cnn", "image_cases", "image_vision"})  # không messages / facts


class GraphTest(unittest.TestCase):
    def test_routing(self) -> None:
        self.assertEqual(_after_memory(cast(Any, {}), _rt([])), ["text_flow"])
        self.assertEqual(_after_memory(cast(Any, {}), _rt(["a"])), ["text_flow", "image_flow"])
        call = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
        self.assertEqual(_after_choose(cast(Any, {"messages": [call]})), "tools")
        self.assertEqual(_after_choose(cast(Any, {"messages": [HumanMessage(content="x")]})), "label_evidence")

    def test_two_independent_lanes(self) -> None:
        root = build_pre_diagnosis_graph().get_graph()
        edges = {(e.source, e.target) for e in root.edges}
        # hai làn cùng rẽ từ load_memory và chỉ gặp nhau ở END của graph cha (không có cạnh chéo giữa hai làn)
        self.assertIn(("load_memory", "text_flow"), edges)
        self.assertIn(("load_memory", "image_flow"), edges)
        self.assertIn(("text_flow", "__end__"), edges)
        self.assertIn(("image_flow", "__end__"), edges)
        self.assertFalse({e for e in edges if "text_flow" in e and "image_flow" in e})


if __name__ == "__main__":
    unittest.main()
