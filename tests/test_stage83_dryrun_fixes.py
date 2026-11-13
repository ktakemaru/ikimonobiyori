"""段階83 第5部の試し(Sonnet)で見つけた照合の誤りの直し。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV

NL = chr(10)
ROW = {"id": "O001", "kind": "seasonal_obs", "species": ["ヤマトシジミ", "オオカマキリ"], "content": "x"}


def codes(text):
    s = GV.sentences([text])[0]
    return [e["code"] for e in GV.seasonal_obs_errors(s, [ROW], GV.cfg(), vocab={"ヤマトシジミ", "オオカマキリ"})]


class DryRunFixes(unittest.TestCase):
    def test_same_period_sentence_passes(self):
        self.assertEqual(codes("オオカマキリなどの秋の虫も、同じ時期によく見つかっています。[O001]"), [])

    def test_state_verbs_blocked_even_with_period_word(self):
        self.assertIn("seasonal_obs_now", codes("今の時期、ヤマトシジミが飛んでいます。過去の記録です。[O001]"))

    def test_obs_record_with_negative_not_internal(self):
        errs = GV.common_errors("同じ観察記録には、オオカマキリなど、チョウやトンボではない秋の虫も並んでいます。" + NL, "q", GV.cfg())
        self.assertNotIn("internal_word", [e["code"] for e in errs])
        errs = GV.common_errors("記録にはありません。" + NL, "q", GV.cfg())
        self.assertIn("internal_word", [e["code"] for e in errs])

    def test_calendar_targets_follow_asked_category(self):
        src = {"name": "試験", "title": "t", "url": "https://museum.example.org/a", "checked_on": "2026-11-13"}

        def cal(title, target):
            return {"title": title, "category": "見頃の流れ", "subject": "試験", "place": "水辺", "facts": ["試験の水辺の話"],
                    "narrative": ["なぜ今"], "condition": {"months": [11]}, "source": src, "confidence": "紹介", "rights": "r",
                    "usage": "u", "calendar": {"environment": "水辺", "months": [11], "target": target, "where": "試験"}}
        shown = [cal("鳥の暦", "鳥"), cal("虫の暦", "虫")]
        got = GB.calendar_cards("今の時期に見られるチョウやトンボは?", {}, [], [11], GB.cfg(), True, shown=shown)
        self.assertEqual([k["title"] for k in got], ["虫の暦"])
        got = GB.calendar_cards("今の見頃のものを教えて", {}, [], [11], GB.cfg(), True, shown=shown)
        self.assertEqual(len(got), 2)

    def test_question_month(self):
        self.assertEqual(GB.question_month("2月の週末、水辺で何が見られる?"), 2)
        self.assertEqual(GB.question_month("5月の高原で見られる花と鳥を教えて"), 5)
        self.assertIsNone(GB.question_month("今週末の紅葉の情報は?"))


if __name__ == "__main__":
    unittest.main()
