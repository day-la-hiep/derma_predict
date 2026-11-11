import unittest
from unittest import mock

from app.infra.bm25 import stopwords, tokenize
from app.infra.bm25.tokenizer import tokenize_with_folds
from app.infra.text_clean import clean_text


class TextCleanTest(unittest.TestCase):
    def test_noi_gach_noi_cuoi_dong_va_bo_ky_tu_la(self) -> None:
        self.assertEqual(clean_text("psori-\nasis​ α-blocker"), "psoriasis alpha-blocker")
        self.assertEqual(clean_text("Anti-\nTNF"), "Anti-\nTNF")


class TokenizeTest(unittest.TestCase):
    def test_mixed(self) -> None:
        tokens = tokenize("The treatments of IL-17 inhibitors cho vảy nến mảng. Điều trị không có dị ứng.")
        for t in ("treatment", "il-17", "il", "17", "inhibitor", "điều_trị", "không"):
            self.assertIn(t, tokens)
        for t in ("the", "of", "."):
            self.assertNotIn(t, tokens)

    def test_so_it_so_nhieu(self) -> None:
        self.assertEqual(tokenize("databases"), tokenize("database"))

    def test_en_khong_goi_underthesea(self) -> None:
        with mock.patch("underthesea.word_tokenize", side_effect=AssertionError("không được gọi")):
            self.assertEqual(tokenize("The treatments of IL-17", "en"), ["treatment", "il-17", "il", "17"])

    def test_vi_giu_tu_ghep_va_khong_stem(self) -> None:
        tokens = tokenize("Điều trị databases", "vi")
        self.assertIn("điều_trị", tokens)
        self.assertIn("databases", tokens)

    def test_token_bo_dau(self) -> None:
        tokens, folds = tokenize_with_folds("Điều trị vảy nến", "vi")
        self.assertIn("~dieu", folds)
        self.assertIn("~vay", folds)
        self.assertNotIn("~vay", tokens)
        self.assertEqual(tokenize_with_folds("treatment", "en")[1], [])  # phía đoạn: chỉ từ có dấu
        self.assertEqual(tokenize_with_folds("treatment", "en", all_tokens=True)[1], ["~treatment"])

    def test_stopword(self) -> None:
        en = stopwords.get_stopwords("en")
        self.assertIn("the", en)
        self.assertNotIn("not", en)
        self.assertNotIn("không", stopwords.get_stopwords("vi"))


if __name__ == "__main__":
    unittest.main()
