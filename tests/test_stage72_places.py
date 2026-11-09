"""段階72 第3部: 知らない地名をすり替えない。合成データ(通信しない)。"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_run as AR
from ikimonobiyori import place_guard as PG

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)


class Candidates(unittest.TestCase):
    def test_unknown_places(self):
        self.assertEqual(PG.unknown_places("霞ヶ浦にはどんな野鳥がいるの?"), ["霞ヶ浦"])
        self.assertEqual(PG.unknown_places("大宮南部浄化センター付近には野鳥はいませんか?"), ["大宮南部浄化センター"])

    def test_known_places_are_not_unknown(self):
        for q in ("箱根周辺で紅葉は?", "日光には紅葉はある?", "秩父には何がある?", "冬には何が見られる?", "高尾山には何がいる?"):
            self.assertEqual(PG.unknown_places(q), [], q)

    def test_pending_large_areas(self):
        for n in ("霞ヶ浦", "霞ケ浦", "印旛沼", "相模湖", "荒川", "利根川"):
            self.assertIsNotNone(PG.pending_area(n), n)


class Route(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def run_q(self, q):
        return AR.run(q, now=NOW, env=self.env, workdir=Path(self.tmp.name) / "w")

    def test_kasumigaura_is_not_hakone(self):
        self.assertEqual(AR.resolve("霞ヶ浦にはどんな野鳥がいるの?", NOW)["route"], "unknown_place")
        res = self.run_q("霞ヶ浦にはどんな野鳥がいるの?")
        self.assertNotIn("箱根", res["text"])
        self.assertIn("霞ヶ浦", res["text"])
        self.assertEqual([t["where"] for t in res["research_targets"]], ["霞ヶ浦"])
        self.assertEqual(res["research_targets"][0]["what"], "野鳥")

    def test_omiya_plant_is_not_yokohama(self):
        res = self.run_q("大宮南部浄化センター付近には野鳥はいませんか?")
        self.assertNotIn("横浜", res["text"])
        self.assertEqual([t["where"] for t in res["research_targets"]], ["大宮南部浄化センター"])

    def test_recorded_facts_answer_after_research(self):
        from ikimonobiyori import observations as O
        O.record([{"subject": "birds", "name": "霞ヶ浦 妙岐ノ鼻", "city": "稲敷市", "prefecture": "茨城県", "state": "オオヒシクイが飛来", "state_date": "2026-11-08",
                   "typical": "冬はオオヒシクイなどが見られる", "url": "https://example.org/kasumi", "publisher": "試験の町", "source_class": "official",
                   "basis": "page"}], env=self.env, now=NOW)
        res = self.run_q("霞ヶ浦にはどんな野鳥がいるの?")
        self.assertIn("霞ヶ浦 妙岐ノ鼻", res["text"])
        self.assertIn("https://example.org/kasumi", res["text"])
        self.assertEqual(res["research_targets"], [])

    def test_print_result_has_research_line_only(self):
        import io
        res = self.run_q("霞ヶ浦にはどんな野鳥がいるの?")
        out, err = io.StringIO(), io.StringIO()
        AR.print_result(res, out, err)
        self.assertIn("調べる: ", err.getvalue())
        self.assertNotIn("資料が足りません", err.getvalue())


if __name__ == "__main__":
    unittest.main()
