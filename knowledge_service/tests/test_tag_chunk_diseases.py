import unittest

from app.scripts.tag_chunk_diseases import build_tags, clean_heading, find_names, match_heading

NAMES = {
    "psoriasis": ["disease:5083"], "contact dermatitis": ["disease:1"], "dermatitis": ["disease:2"],
    "lichen planus": ["disease:3a", "disease:3b"], "atopic dermatitis": ["disease:4"],
}


class TagChunkDiseasesTest(unittest.TestCase):
    def test_clean_heading_strips_numbering(self):
        self.assertEqual(clean_heading("29 Epidermal Nevi"), "epidermal nevi")
        self.assertEqual(clean_heading("CHƯƠNG 6. Bệnh vảy nến"), "bệnh vảy nến")
        self.assertEqual(clean_heading("14.2 Psoriasis"), "psoriasis")

    def test_longest_match_and_generic_removed(self):
        found = find_names("Allergic contact dermatitis differs from psoriasis and dermatitis.", NAMES)
        self.assertEqual(found, {"contact dermatitis", "psoriasis"})  # "dermatitis" đứng riêng là tên nhóm → bỏ

    def test_heading_leaf_first_and_plural(self):
        self.assertEqual(match_heading(["8 Papulosquamous", "Lichen Planus"], NAMES), ["disease:3a", "disease:3b"])
        self.assertEqual(match_heading(["10 Psoriasiss"], NAMES), ["disease:5083"])
        self.assertEqual(match_heading(["5 Dermatitis"], NAMES), [])

    def test_build_tags_excludes_primary_from_mentioned(self):
        chunks = [{"chunk_id": "c1", "toc_path": ["Psoriasis"], "text": "psoriasis vs atopic dermatitis"}]
        self.assertEqual(build_tags(chunks, NAMES)["c1"], {"primary_disease_ids": ["disease:5083"], "mentioned_disease_ids": ["disease:4"]})


if __name__ == "__main__":
    unittest.main()
