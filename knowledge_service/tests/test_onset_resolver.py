import unittest
from datetime import date

from app.services.onset_resolver import resolve_onset

REF = date(2026, 11, 12)


class OnsetResolverTest(unittest.TestCase):
    def test_relative_phrases(self) -> None:
        cases = {
            "hôm qua": date(2026, 11, 11),
            "khoảng 3 ngày nay": date(2026, 11, 9),
            "từ tuần trước": date(2026, 11, 5),
            "2 tuần": date(2026, 10, 29),
            "hai tuần nay": date(2026, 10, 29),
            "5 tháng": date(2026, 6, 15),
            "năm năm": date(2021, 11, 13),
            "năm ngày": date(2026, 11, 7),
            "hôm nay": REF,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(resolve_onset(text, REF), expected)

    def test_month_name_picks_latest_past_year(self) -> None:
        self.assertEqual(resolve_onset("từ tháng 10", REF), date(2026, 10, 1))
        self.assertEqual(resolve_onset("tháng 12", REF), date(2025, 12, 1))

    def test_unresolvable_returns_none(self) -> None:
        for text in ["", "từ nhỏ", "bẩm sinh", "không rõ", "vài ngày", "gần đây"]:
            with self.subTest(text=text):
                self.assertIsNone(resolve_onset(text, REF))


if __name__ == "__main__":
    unittest.main()
