import unittest

from agent.test.timeline import fmt_ms, lane, spans, tree_rows, tree_text


def _debug() -> dict:
    ev = lambda t, ns, node: {"t": t, "ns": ns, "node": node, "update": {}}  # noqa: E731
    return {
        "events": [
            ev(10, "pre_diagnosis", "load_memory"),
            ev(100, "pre_diagnosis/image_flow", "image_cnn"),
            ev(900, "pre_diagnosis/image_flow", "image_vision"),
            ev(900, "pre_diagnosis/image_flow", "image_done"),
            ev(900, "pre_diagnosis", "image_flow"),
            ev(300, "pre_diagnosis/text_flow", "extract_facts"),
            ev(700, "pre_diagnosis/text_flow", "plan"),
            ev(1200, "pre_diagnosis/text_flow", "tools"),
            ev(1200, "pre_diagnosis", "text_flow"),
            ev(1200, "", "pre_diagnosis"),
        ],
        "calls": [{"node": "plan", "t": 310, "ms": 380, "model": "x/gemma", "in_tool": None}],
        "tools": [{"name": "hybrid_retrieval", "t": 710, "ms": 480}],
        "starts": [
            {"path": ["pre_diagnosis", "image_flow", "image_cnn"], "t": 12},
            {"path": ["pre_diagnosis", "image_flow", "image_vision"], "t": 12},
            {"path": ["pre_diagnosis", "image_flow", "image_done"], "t": 900},
            {"path": ["pre_diagnosis", "text_flow", "extract_facts"], "t": 12},
            {"path": ["pre_diagnosis", "text_flow", "plan"], "t": 300},
            {"path": ["pre_diagnosis", "text_flow", "tools"], "t": 700},
        ],
    }


class TimelineTreeTest(unittest.TestCase):
    def test_parallel_nodes_start_together(self) -> None:
        by = {s["path"][-1]: s for s in spans(_debug())}
        self.assertEqual(by["image_vision"]["start"], 12)  # song song với image_cnn, không phải sau nó
        self.assertEqual(by["extract_facts"]["start"], 12)
        self.assertTrue(by["text_flow"]["container"] and by["image_flow"]["container"])

    def test_containment_and_leaves(self) -> None:
        rows = tree_rows(_debug())
        names = [(r["depth"], r["kind"], r["name"]) for r in rows]
        self.assertEqual(names[0], (0, "container", "pre_diagnosis"))
        self.assertIn((2, "node", "plan"), names)
        self.assertIn((3, "llm", "LLM · gemma"), names)  # lần gọi LLM nằm trong node plan
        self.assertIn((3, "tool", "hybrid_retrieval"), names)  # tool nằm trong node tools
        # con luôn đứng ngay sau cha
        self.assertLess(names.index((1, "container", "text_flow")), names.index((2, "node", "plan")))

    def test_text_and_lane(self) -> None:
        text = tree_text(tree_rows(_debug()))
        self.assertIn("├─ ▣ image_flow", text)
        self.assertIn("└─ ▣ text_flow", text)
        self.assertTrue(lane({"depth": 2, "name": "plan"}).startswith("    └ "))

    def test_tools_placed_by_their_node_down_to_smallest_step(self) -> None:
        d = _debug()
        d["tools"] = [
            {"name": "load_image", "node": "image_cnn", "t": 12, "ms": 2},
            {"name": "cnn_predict", "node": "image_cnn", "t": 14, "ms": 80},
            {"name": "vision_describe", "node": "image_vision", "t": 14, "ms": 880},
            {"name": "hybrid_retrieval", "node": "tools", "t": 710, "ms": 480},
        ]
        d["calls"].append({"node": "image_vision", "t": 20, "ms": 800, "model": "medgemma", "in_tool": "vision_describe"})
        names = [(r["depth"], r["name"]) for r in tree_rows(d)]
        self.assertIn((3, "load_image"), names)  # tool nằm trong node image_cnn (không chỉ trong node `tools`)
        self.assertIn((3, "cnn_predict"), names)
        self.assertIn((3, "vision_describe"), names)
        self.assertIn((4, "LLM · medgemma (trong tool vision_describe)"), names)  # LLM lồng trong tool

    def test_llm_lanes_unique_per_parent_node(self) -> None:
        d = _debug()
        d["calls"] = [
            {"node": "extract_facts", "t": 20, "ms": 200, "model": "x/gemma", "in_tool": None},
            {"node": "plan", "t": 310, "ms": 380, "model": "x/gemma", "in_tool": None},
        ]
        keys = [r["key"] for r in tree_rows(d) if r["kind"] == "llm"]
        self.assertEqual(len(set(keys)), 2)  # cùng tên LLM nhưng khác node cha thì khác dòng
        self.assertTrue(keys[0].endswith("/LLM · gemma") and "extract_facts" in keys[0])

    def test_fmt_ms(self) -> None:
        self.assertEqual(fmt_ms(3), "3 ms")
        self.assertEqual(fmt_ms(999), "999 ms")
        self.assertEqual(fmt_ms(2010), "2.01 s")

    def test_old_file_without_starts(self) -> None:
        d = _debug()
        del d["starts"]
        self.assertTrue(spans(d))  # file lưu cũ vẫn dựng được (suy ra từ node trước)


if __name__ == "__main__":
    unittest.main()
