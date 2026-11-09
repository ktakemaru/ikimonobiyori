"""段階72 第6部: 細かい崩れ(11/10 の会話)。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import season_place as SP

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)


class OldYearAndDistance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_year_is_written(self):
        r = {"source_year": 2014, "read_at": "2026-11-09T20:59:16+09:00"}
        self.assertEqual(SP._old_year(r, "7月上旬まで"), "2014年の記載では、7月上旬まで")
        self.assertEqual(SP._old_year({"source_year": 2026, "read_at": "2026-11-09T20:59:16+09:00"}, "7月上旬まで"), "7月上旬まで")
        self.assertEqual(SP._old_year({"read_at": "2026-11-09T20:59:16+09:00"}, "7月上旬まで"), "7月上旬まで")

    def test_record_keeps_source_year(self):
        out = O.record([{"subject": "flowers", "name": "試験川(試験院周辺)", "city": "あきる野市", "prefecture": "東京都", "kind": "ホタル", "state": "",
                         "typical": "例年ですと、試験川全体で7月上旬までホタルをみることができます", "url": "https://example.org/p1251",
                         "publisher": "試験の観光協会", "source_class": "official", "basis": "page", "source_year": 2014}], env=self.env, now=NOW)
        self.assertEqual(out["written"], 1, out)
        self.assertEqual(O.read_records("flowers", self.env)[0]["source_year"], 2014)

    def test_akiruno_answer(self):
        from ikimonobiyori import answer_run as AR
        O.record([{"subject": "flowers", "name": "試験川(試験院周辺)", "city": "あきる野市", "prefecture": "東京都", "kind": "ホタル", "state": "",
                   "typical": "例年ですと、試験川全体で7月上旬までホタルをみることができます", "url": "https://example.org/p1251",
                   "publisher": "試験の観光協会", "source_class": "official", "basis": "page", "source_year": 2014}], env=self.env, now=NOW)
        res = AR.run("あきる野市でホタルが見られるところと時期は?", now=NOW, env=self.env, workdir=Path(self.tmp.name) / "w")
        t = res["text"]
        self.assertIn("2014年の記載では、7月上旬まで", t)
        self.assertNotIn("〜7月上旬", t)
        if "約" not in t.split("出典")[0]:                         # 座標(距離)のない名所だけなら、距離の 1 文を出さない
            self.assertNotIn("直線距離です", t)
        self.assertFalse(t.startswith("\n"))


class YearRound(unittest.TestCase):
    def test_label_and_outlook(self):
        pol = O.load_policy()
        typ = {"start": "01-01", "end": "12-31", "text": "1/1〜12/31"}
        self.assertTrue(O.is_year_round(typ))
        self.assertEqual(O.typical_line(typ, {}, [], pol), "例年の見頃: 通年（咲く花は季節で変わる）")
        self.assertEqual(SP.window_text("01-01", "12-31", SP.cfg()["text"]["thirds"]), "通年（咲く花は季節で変わる）")

    def test_year_round_is_not_in_peak(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        c = {"name": "試験植物園", "typical": [{"start": "01-01", "end": "12-31"}], "current": None}
        self.assertNotEqual(AP.outlook_of(c, NOW.date(), pol), "in_peak")
        c2 = {"name": "試験庭園", "typical": [{"start": "11-01", "end": "11-30"}], "current": None}
        self.assertEqual(AP.outlook_of(c2, NOW.date(), pol), "in_peak")


class OffersOnce(unittest.TestCase):
    def test_drop_repeated(self):
        from ikimonobiyori import offers as OF
        prev = "答え\n\n写真つきのページにもできます。\n\nここまでの候補は表にして比べられます。\n"
        new = "別の答え\n\n写真つきのページにもできます。\n"
        self.assertEqual(OF.drop_repeated(new, prev), "別の答え\n")
        self.assertEqual(OF.drop_repeated(new, "前の答え\n"), new)
        self.assertEqual(OF.drop_repeated(new, None), new)

    def test_same_question_rerun_keeps_offers(self):
        from ikimonobiyori import final_check as FC
        tmp = tempfile.TemporaryDirectory()
        env = {"IKIMONOBIYORI_DATA_DIR": tmp.name}
        FC.remember_answer("答え\n写真つきのページにもできます。\n", "今週末の紅葉は?", NOW, env)
        self.assertEqual(FC.load_question(NOW, env), "今週末の紅葉は?")
        self.assertIsNone(FC.load_question(NOW + timedelta(days=2), env))
        tmp.cleanup()


class WidePhotoPageSections(unittest.TestCase):
    def test_wide_plan_has_no_near_label(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.scope_policy(AP.load_policy(), "wide")
        self.assertNotIn("near", pol["aims"]["order"])
        self.assertNotIn("近場で手軽に", [pol["aims"]["labels"][k] for k in pol["aims"]["order"]])


if __name__ == "__main__":
    unittest.main()
