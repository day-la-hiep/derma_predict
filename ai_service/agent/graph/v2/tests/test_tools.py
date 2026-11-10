import unittest
from unittest.mock import patch

from agent.graph.v2 import pre_diagnosis_graph
from agent.prompt.v2 import CHOOSE_SYSTEM, FINALIZE_REPORT_LINE


class FinalizeReportToggleTest(unittest.TestCase):
    def test_tool_follows_setting(self) -> None:
        for enabled in (True, False):
            with patch.object(pre_diagnosis_graph.settings, "AGENT_FINALIZE_REPORT_SEARCH_ENABLED", enabled):
                names = [t.name for t in pre_diagnosis_graph.build_tools()]
            self.assertEqual("search_finalize_report" in names, enabled)

    def test_prompt_line_only_when_enabled(self) -> None:
        on = CHOOSE_SYSTEM.format(context="", finalize_report=FINALIZE_REPORT_LINE)
        off = CHOOSE_SYSTEM.format(context="", finalize_report="")
        self.assertIn("search_finalize_report", on)
        self.assertNotIn("search_finalize_report", off)


if __name__ == "__main__":
    unittest.main()
