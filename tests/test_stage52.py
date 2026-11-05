"""段階52: ウェザーニュース由来(転載を含む)の予想を答えの材料にしない。通信しない。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ikimonobiyori import observations as O  # noqa: E402


class WeathernewsExcluded(unittest.TestCase):
    def setUp(self):
        self.pol = O.load_policy()

    def test_reprint_is_rejected_at_record(self):
        rec = {"subject": "autumn_leaves", "name": "御岳昇仙峡", "city": "甲府市", "state": "見頃予想:11月8日(日)頃から", "state_date": "2026-10-29",
               "url": "https://koyo.walkerplus.com/topics/article/161896/", "publisher": "ウォーカープラス(ウェザーニューズ予想)", "source_class": "secondary"}
        self.assertTrue(O.validate(rec, self.pol))
        self.assertTrue(O._reprint_of_blocked(rec, self.pol))

    def test_hosts_are_not_read(self):
        for h in ("weathernews.jp", "n-kishou.com"):
            self.assertTrue(O._blocked_host(h, self.pol), h)
        self.assertFalse(O._blocked_host("koyo.walkerplus.com", self.pol))

    def test_other_walkerplus_content_is_kept(self):
        rec = {"subject": "autumn_leaves", "name": "三溪園", "city": "横浜市", "state": "紅葉の状態の記載なし", "typical": "11月中旬～12月中旬",
               "url": "https://koyo.walkerplus.com/list/ar0314/", "publisher": "ウォーカープラス", "source_class": "secondary"}
        self.assertFalse(O.validate(rec, self.pol))

    def test_existing_reprint_rows_do_not_reach_facts(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            p = O.log_path("autumn_leaves", env, self.pol)
            p.parent.mkdir(parents=True, exist_ok=True)
            row = {"subject": "autumn_leaves", "name": "高尾山", "state": "見頃予想:11月13日(金)頃から", "state_date": "2026-10-29",
                   "url": "https://koyo.walkerplus.com/topics/article/161896/", "publisher": "ウォーカープラス(ウェザーニューズ予想)",
                   "source_class": "secondary", "read_at": "2026-11-06T05:00:00+09:00"}
            p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual(O.read_records("autumn_leaves", env, self.pol), [])

    def test_summary_pages_do_not_include_reprint(self):
        for subj in self.pol["summary_pages"].values():
            for pages in subj.values():
                for pg in pages:
                    self.assertNotIn("161896", pg["url"])
                    self.assertNotIn("n-kishou", pg["url"])


if __name__ == "__main__":
    unittest.main()
