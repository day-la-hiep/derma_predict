import unittest
from unittest.mock import patch

from app.tools import pre_diagnosis_tool_registry as registry
from app.prompt.pre_diagnosis_prompts import CHOOSE_SYSTEM, FINALIZE_REPORT_LINE


class FinalizeReportToggleTest(unittest.TestCase):
    def test_tool_follows_setting(self) -> None:
        for enabled in (True, False):
            with patch.object(registry.settings, "AGENT_FINALIZE_REPORT_SEARCH_ENABLED", enabled):
                names = [t.name for t in registry.build_tools()]
            self.assertEqual("search_finalize_report" in names, enabled)

    def test_prompt_line_only_when_enabled(self) -> None:
        on = CHOOSE_SYSTEM.format(context="", finalize_report=FINALIZE_REPORT_LINE)
        off = CHOOSE_SYSTEM.format(context="", finalize_report="")
        self.assertIn("search_finalize_report", on)
        self.assertNotIn("search_finalize_report", off)


if __name__ == "__main__":
    unittest.main()
