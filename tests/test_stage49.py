"""段階49 第2部2: find の JSON の official_check(公式の確認あり／公式未確認)。定評の条件ではない。--text は変えない。通信しない。"""
import unittest

import helpers as H  # noqa: F401

from ikimonobiyori import guide


class OfficialCheck(unittest.TestCase):
    def test_label(self):
        pol = guide.load_policy()
        a = guide.official_check_of({"sources": [{"class": "C"}, {"class": "A"}]}, pol)
        self.assertEqual(a, {"has_official": True, "label": "公式の確認あり"})
        b = guide.official_check_of({"sources": [{"class": "C"}, {"class": "C"}, {"class": "D"}]}, pol)
        self.assertEqual(b, {"has_official": False, "label": "公式未確認"})

    def test_marks_find_output(self):
        pol = guide.load_policy()
        out = {"recommend": [{"name": "x", "sources": [{"class": "B"}]}], "kind_notes": [{"name": "k"}]}
        guide._mark_official(out, pol)
        self.assertTrue(out["recommend"][0]["official_check"]["has_official"])
        self.assertNotIn("official_check", out["kind_notes"][0])


if __name__ == "__main__":
    unittest.main()
