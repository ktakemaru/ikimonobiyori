"""段階82 の続き 2(本人の判断 2026-11-13 の 1〜3・5): 月だけの記載は月のまま・公式より長い紹介サイトの時期は区別して資料に・
「花ごと落ちるサザンカ」の形の照合・種の名前と「いつ」だけの質問は種の質問。合成データ(通信しない)。"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_run as AR
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import research as RS
from ikimonobiyori import season_place as SP

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=JST)
URL = "https://www.kensetsu.metro.tokyo.lg.jp/park/hanamigoro/11sazanka"
C = GB.cfg()


class MonthOnly(unittest.TestCase):
    def test_month_only_text(self):
        self.assertEqual(SP.month_only("11月"), "11月")
        self.assertEqual(SP.month_only(" 7月〜8月 "), "7月〜8月")
        self.assertEqual(SP.month_only("7月～8月ごろ"), "7月〜8月")
        self.assertIsNone(SP.month_only("11月上旬"))
        self.assertIsNone(SP.month_only("10月下旬〜2月下旬"))
        self.assertIsNone(SP.month_only("通年"))


class Kameido(unittest.TestCase):
    """亀戸中央公園のサザンカ: 公式の「11月」(月のまま)と、紹介サイトの「1月末まで」の両方が資料に入る。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        RS._save_state("b-k", {"pages": [{"url": URL, "at": NOW.isoformat(), "status": 200}], "first_at": NOW.isoformat(), "question": "サザンカ"}, self.env)
        r = RS.record([{"subject": "flowers", "name": "亀戸中央公園", "prefecture": "東京都", "city": "江東区", "kind": "サザンカ", "typical": "11月",
                        "url": URL, "publisher": "東京都建設局"}], "b-k", question="サザンカ", env=self.env, now=NOW)
        self.assertEqual(r["written"], 1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_row_keeps_month_and_secondary(self):
        sp = SP.resolve_all("サザンカの見頃")[0]
        row = {x["name"]: x for x in SP.gather(sp, "東京", env=self.env)}["亀戸中央公園"]
        self.assertEqual((row["season"], row["official"]), ("11月", True))
        self.assertIn("1月", row["secondary_season"]["season"])
        self.assertIn("tabi-mag.jp", row["secondary_season"]["url"])

    def test_both_in_brief_official_first(self):
        b = GB.build("サザンカの見頃と見どころを教えて", now=NOW, env=self.env)
        rows = [f for f in b["facts"] if "亀戸中央公園" in f["content"]]
        texts = [f["content"] for f in rows]
        self.assertTrue(any("サザンカの例年の時期 11月(" in t for t in texts), texts)
        self.assertFalse(any("11月上旬〜11月下旬" in t for t in texts), texts)
        sec = [f for f in rows if "紹介サイトによると" in f["content"]]
        self.assertEqual(len(sec), 1, texts)
        self.assertEqual(sec[0]["source_class"], "secondary")
        self.assertIn("1月", sec[0]["content"])
        self.assertLess(rows.index(next(f for f in rows if f["source_class"] == "official")), rows.index(sec[0]))

    def test_secondary_inside_official_is_not_added(self):
        self.assertIsNone(SP._secondary_of({"start": "12-01", "end": "02-28"}, {"start": "10-21", "end": "02-28"}, SP.cfg()["text"]["thirds"]))


class ModifierForm(unittest.TestCase):
    CARD = {"id": "K004", "title": "サザンカとツバキの見分け方", "facts": [],
            "contrasts": [{"a": ["ツバキ"], "a_re": "花ごと(落ち|ぽとり|散)", "b": ["サザンカ"], "b_re": "花びらが(1|一)枚ずつ散|花びらが散"}]}

    def codes(self, text):
        return [e["code"] for e in GV.contrast_errors(GV.sentences([text], C), {"cards": [self.CARD]}, C)]

    def test_trait_right_before_the_name(self):
        self.assertEqual(self.codes("花ごと落ちるサザンカは、ツバキとよく似ています。[K004]"), ["trait_reversed"])
        self.assertEqual(self.codes("花びらが1枚ずつ散るツバキです。[K004]"), ["trait_reversed"])

    def test_correct_and_undecidable_forms_pass(self):
        self.assertEqual(self.codes("花ごと落ちるツバキとよく似たサザンカです。[K004]"), [])
        self.assertEqual(self.codes("サザンカは、花ごと落ちるツバキと違い、花びらが散ります。[K004]"), [])
        self.assertEqual(self.codes("花びらが1枚ずつ散るサザンカと、花ごと落ちるツバキ。[K004]"), [])
        self.assertEqual(self.codes("花ごと落ちないサザンカです。[K004]"), [])


class WhenQuestions(unittest.TestCase):
    def route(self, q):
        return AR.resolve(q, NOW)["route"]

    def test_species_and_when_is_a_species_question(self):
        for q in ("チングルマはいつ見られる?", "ロウバイはいつ咲く?", "サザンカの見頃はいつ?", "コスモスはいつまで見られる?", "河津桜はいつごろ?"):
            self.assertEqual(self.route(q), "season_place", q)

    def test_other_routes_stay(self):
        self.assertEqual(self.route("梅はいつ咲く?"), "normal")                    # 気象庁の平年の目安の型はそのまま
        self.assertEqual(self.route("今週末、ロウバイはいつ見られる?"), "species_dated")
        self.assertNotEqual(self.route("ロウバイはいつ日本に来たの?"), "season_place")
        self.assertNotEqual(self.route("今週末どこに行けばいい?"), "season_place")


if __name__ == "__main__":
    unittest.main()
