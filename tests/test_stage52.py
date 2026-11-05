"""段階52: ウェザーニュース由来(転載を含む)の予想を答えの材料にしない。通信しない。"""
import copy
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


# ---- 第3部: 日付の統一・古い表示 ----
import helpers as H  # noqa: E402,F401
from ikimonobiyori import ask  # noqa: E402
from test_stage51 import STRICT, GOOD51, c51  # noqa: E402


class DatesAndStaleDisplay(unittest.TestCase):
    def test_date_range_on_one_state_is_rejected(self):
        self.assertIn("date_range", c51(GOOD51 + "箱根は10/29～11/3時点で「色づきはじめ」です。\n"))
        self.assertIn("date_range", c51(GOOD51 + "箱根は10/29〜11/3時点で「色づきはじめ」です。\n"))
        self.assertNotIn("date_range", c51(GOOD51 + "箱根は10/29時点で「色づきはじめ」です。\n"))
        self.assertNotIn("date_range", c51(GOOD51 + "菊花展が10/31～11/23にあります。\n"))          # 行事の期間は対象外

    def test_hakone_state_far_from_read_date_is_reference_only(self):
        cur = {"state": "色づきはじめ", "state_date": "2026-10-29", "read_at": "2026-11-06T05:00:00+09:00", "publisher": "箱根町観光協会"}
        subj = {"autumn_leaves": {"candidates": [{"name": "箱根強羅公園", "current": dict(cur)},
                                                   {"name": "箱根湖尻", "current": dict(cur, state_date="2026-11-05")},
                                                   {"name": "日光", "current": dict(cur, publisher="日光市観光協会")}]}}
        ask.mark_stale_display(subj, ask.load_policy())
        c = subj["autumn_leaves"]["candidates"]
        self.assertTrue(c[0]["current"]["reference_only"])
        self.assertEqual(c[0]["current"]["gap_days"], 8)
        self.assertNotIn("reference_only", c[1]["current"])        # 2 日前までは現況として使える
        self.assertNotIn("reference_only", c[2]["current"])        # 箱根町観光協会以外は対象外

    def test_reference_only_state_must_be_written_as_reference(self):
        f = copy.deepcopy(STRICT)
        c0 = f["subjects"]["birds"]["candidates"][0]
        c0["current"] = {**(c0.get("current") or {}), "state": "色づきはじめ", "reference_only": True, "url": "https://www.inaturalist.org/"}
        name = c0["name"]
        bad = GOOD51 + f"{name}は10/29時点で「色づきはじめ」です。\n"
        self.assertIn("stale_state_asserted", c51(bad, f))
        ok = GOOD51 + f"{name}は10/29時点の参考として「色づきはじめ」との表示があります。\n"
        self.assertNotIn("stale_state_asserted", c51(ok, f))


class PracticalInfo(unittest.TestCase):
    def facts(self, practical):
        f = copy.deepcopy(STRICT)
        f["lines"]["practical_rules"] = True
        for c in f["subjects"]["birds"]["candidates"]:
            c["practical"] = []
        if practical:
            f["subjects"]["birds"]["candidates"][0]["practical"] = [{"text": "11/6の昭和記念公園は有料エリア9:30~21:00", "publisher": "試験", "url": "https://birds.example.org/"}]
        return f

    def test_practical_line_must_be_used_when_a_read_page_has_it(self):
        f = self.facts(True)
        self.assertIn("practical_missing", c51(GOOD51, f))
        self.assertNotIn("practical_missing", c51(GOOD51 + "11/6の昭和記念公園は有料エリア9:30~21:00です。\n", f))

    def test_fallback_sentence_when_nothing_was_read(self):
        f = self.facts(False)
        self.assertIn("practical_fallback_missing", c51(GOOD51, f))
        self.assertNotIn("practical_fallback_missing", c51(GOOD51 + "アクセスや混雑は出かける前に公式ページで確認してください。\n", f))

    def test_old_facts_without_the_mark_are_unchanged(self):
        self.assertNotIn("practical_fallback_missing", c51(GOOD51))


if __name__ == "__main__":
    unittest.main()
