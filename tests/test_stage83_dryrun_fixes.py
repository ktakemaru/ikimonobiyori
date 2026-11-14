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


class NoiseFixes(unittest.TestCase):
    def test_word_hit_ignores_prefecture_and_katakana_inside(self):
        self.assertFalse(GB.word_hit("川", "神奈川と東京で紅葉の見ごろを教えて"))
        self.assertTrue(GB.word_hit("川", "荒川の土手で何が見られる?"))
        self.assertFalse(GB.word_hit("セミ", "カワセミが見たい"))
        self.assertTrue(GB.word_hit("セミ", "セミの抜け殻を探したい"))
        self.assertEqual(GB.seasonal_categories("カワセミが見たい", {}), [c["id"] for c in __import__("ikimonobiyori.seasonal_obs", fromlist=["x"]).load_policy()["categories"]])

    def test_difference_route_has_no_obs(self):
        self.assertEqual(GB.seasonal_categories("梅と桜の見分け方を教えて", {"route": "difference"}), [])

    def test_flowering_claim_needs_annotation(self):
        row = {"id": "O001", "kind": "seasonal_obs", "category": "plants", "species": ["ススキ", "ツワブキ"], "flowering": ["ツワブキ"], "content": "x"}
        s = GV.sentences(["過去5年の観察記録では、この時期はススキが咲く記録が多くなっています。[O001]"])[0]
        self.assertIn("seasonal_obs_flower", [e["code"] for e in GV.seasonal_obs_errors(s, [row], GV.cfg(), vocab={"ススキ", "ツワブキ"})])
        s = GV.sentences(["過去5年の観察記録では、この時期はツワブキの花の記録が多くなっています。[O001]"])[0]
        self.assertEqual([e["code"] for e in GV.seasonal_obs_errors(s, [row], GV.cfg(), vocab={"ススキ", "ツワブキ"})], [])
        s = GV.sentences(["過去5年の観察記録では、この時期はススキの記録が多くなっています。[O001]"])[0]
        self.assertEqual([e["code"] for e in GV.seasonal_obs_errors(s, [row], GV.cfg(), vocab={"ススキ", "ツワブキ"})], [])

    def test_one_kanji_species_tale(self):
        src = {"name": "試験", "title": "t", "url": "https://museum.example.org/a", "checked_on": "2026-11-13"}
        tale = {"title": "梅の小話", "category": "名前・歴史・文化", "subject": "ウメ", "subject_aliases": ["梅"], "place": "ウメ",
                "facts": ["ウメは中国から来た"], "narrative": ["小話"], "condition": {"months": []}, "source": src,
                "confidence": "紹介", "rights": "r", "usage": "u", "tale": {"topic": "歴史"}}
        self.assertEqual(len(GB.tale_cards("梅を見たい", {}, [], [], GB.cfg(), shown=[tale])), 1)
        self.assertEqual(GB.tale_cards("梅雨の時期の花は?", {}, [], [], GB.cfg(), shown=[tale]), [])
