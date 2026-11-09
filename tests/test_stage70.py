"""段階70: 秋のお出かけの答えのススキ・草紅葉の名所・--out-dir の相対パス・CI の版。合成データ(通信しない)。"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)
WEEKEND = [date(2026, 11, 14), date(2026, 11, 15)]
ROOT = Path(__file__).resolve().parent.parent

SUSUKI = {"subject": "flowers", "name": "試験のすすき草原", "city": "箱根町", "prefecture": "神奈川県", "kind": "ススキ",
          "typical": "9月〜11月", "url": "https://www.example-hakone.test/susuki", "source_class": "official", "basis": "page",
          "publisher": "試験の観光協会"}
KUSAMOMIJI = {"subject": "flowers", "name": "試験の湿原", "city": "日光市", "prefecture": "栃木県", "kind": "草紅葉",
              "typical": "9月下旬〜10月上旬", "url": "https://www.example-nikko.test/kusamomiji", "source_class": "official", "basis": "page",
              "publisher": "試験の観光協会"}

PLAN_ANSWER = """見頃に向かう可能性がある場所を選びました。
対象の日は11/14・11/15です。

今回のおすすめ
① 試験の渓谷 約40km
・今の状況は色づき始め(11/6時点、試験町)

今年の情報が確認できていない候補
・試験の公園: 例年の見頃: 11月中旬〜12月上旬(今年の情報は確認できていません)

行く前に確認すること
試験の渓谷: 駐車場は混みます(11/6時点の公式のお知らせ)

出典
https://example.org/a

写真つきのページにもできます。
"""


class Part1GrassInAutumnPlan(unittest.TestCase):
    """第1部: 「今週末に紅葉やススキ、そのほか秋を満喫」の計画の答えに、記録済みのススキ・草紅葉の名所の節。"""

    def setUp(self):
        from ikimonobiyori import observations as O
        self.dir = tempfile.mkdtemp()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.dir}
        out = O.record([dict(SUSUKI), dict(KUSAMOMIJI)], env=self.env)
        self.assertFalse(out.get("rejected"), out)

    def tail(self, q, on=WEEKEND):
        from ikimonobiyori import season_place as SP
        return SP.grass_tail(q, today=NOW.date(), on=on, origin="横浜", env=self.env)

    def test_susuki_named_in_the_question(self):
        lines, urls = self.tail("今週末に紅葉やススキ、そのほか秋を満喫できそうなところ")
        text = "\n".join(lines)
        self.assertEqual(lines[0], "ススキの名所")
        self.assertIn("試験のすすき草原", text)
        self.assertIn("例年の時期", text)
        self.assertIn("穂の様子", text)
        self.assertNotIn("咲き具合", text)
        self.assertIn(SUSUKI["url"], urls)
        self.assertNotIn("試験の湿原", text)                 # 名前の出ていない草紅葉は、時期の外なら書かない

    def test_kusamomiji_named_out_of_season_is_one_line(self):
        lines, urls = self.tail("今週末、紅葉や草紅葉を楽しめるところ")
        text = "\n".join(lines)
        self.assertIn("草紅葉", lines[0])
        self.assertIn("時期の外: 試験の湿原(例年9月下旬〜10月上旬)", text)
        self.assertIn("試験のすすき草原", text)               # ススキは名前がなくても、時期が合えば書く

    def test_kusamomiji_in_season(self):
        lines, _ = self.tail("10月4日に紅葉や草紅葉を見に行きたい", on=[date(2026, 10, 4)])
        text = "\n".join(lines)
        self.assertIn("**試験の湿原**", text)
        self.assertNotIn("時期の外", text)

    def test_autumn_words_without_grass_words(self):
        lines, _ = self.tail("今週末、秋を満喫できるところは?")
        self.assertIn("試験のすすき草原", "\n".join(lines))

    def test_no_section_without_the_words_or_outside_autumn(self):
        self.assertEqual(self.tail("今週末の紅葉のおすすめは?"), ([], []))
        self.assertEqual(self.tail("ススキや紅葉を見たい", on=[date(2027, 3, 13)]), ([], []))

    def test_no_section_without_records(self):
        from ikimonobiyori import season_place as SP
        env = {"IKIMONOBIYORI_DATA_DIR": tempfile.mkdtemp()}
        with mock.patch.object(SP, "_flower_entries", return_value=[]), mock.patch.object(SP, "_guide_entries", return_value=[]):
            self.assertEqual(SP.grass_tail("紅葉やススキ", today=NOW.date(), on=WEEKEND, origin="横浜", env=env), ([], []))

    def test_section_goes_after_the_no_this_year_box_and_sources_before_offers(self):
        from ikimonobiyori import answer_run as AR
        cond = {"question": "今週末に紅葉やススキ、そのほか秋を満喫できそうなところ", "region": None, "origin": "横浜",
                "periods": [[d.isoformat() for d in WEEKEND]]}
        text = AR._with_grass_tail(PLAN_ANSWER, cond, NOW, self.env)
        lines = text.splitlines()
        i_box, i_sec, i_before = lines.index("今年の情報が確認できていない候補"), lines.index("ススキの名所"), lines.index("行く前に確認すること")
        self.assertLess(i_box, i_sec)
        self.assertLess(i_sec, i_before)
        i_src, i_url, i_offer = lines.index("出典"), lines.index(SUSUKI["url"]), lines.index("写真つきのページにもできます。")
        self.assertLess(i_src, i_url)
        self.assertLess(i_url, i_offer)
        self.assertEqual(text.count(SUSUKI["url"]), 1)
        self.assertNotIn("\n\n\n", text)
        self.assertEqual(AR._with_grass_tail(PLAN_ANSWER, dict(cond, question="今週末の紅葉"), NOW, self.env), PLAN_ANSWER)

    def test_final_check_keeps_the_section(self):
        from ikimonobiyori import answer_run as AR
        from ikimonobiyori import final_check as FC
        cond = {"question": "今週末に紅葉やススキ、そのほか秋を満喫できそうなところ", "region": None, "origin": "横浜",
                "periods": [[d.isoformat() for d in WEEKEND]]}
        text = AR._with_grass_tail(PLAN_ANSWER, cond, NOW, self.env)
        r = FC.check(text, answer=text)
        self.assertIn("ススキの名所", r["text"])
        self.assertIn("試験のすすき草原", r["text"])

    def test_dated_species_answer_is_unchanged_by_the_refactor(self):
        from ikimonobiyori import season_place as SP
        got = SP.compose_dated("今週末、ススキや草紅葉を見たい", today=NOW.date(), on=WEEKEND, origin="横浜", env=self.env)
        self.assertTrue(got["text"].startswith("**11/14・11/15のススキ・草紅葉**"))
        self.assertIn("\nススキ\n", got["text"])
        self.assertIn("時期の外: 試験の湿原", got["text"])
        self.assertIn("\n出典\n", got["text"])


class Part2RelativeOutDir(unittest.TestCase):
    """第2部: --out-dir の相対パスは、データ置き場からの相対(実行したフォルダ = リポジトリの中に作業フォルダを作らない)。"""

    def test_work_path(self):
        from ikimonobiyori import paths
        base = tempfile.mkdtemp()
        env = {"IKIMONOBIYORI_DATA_DIR": base}
        self.assertEqual(paths.work_path("ask/試験", env), Path(base) / "ask" / "試験")
        absolute = Path(tempfile.mkdtemp()) / "wd"
        self.assertEqual(paths.work_path(str(absolute), env), absolute)
        self.assertIsNone(paths.work_path(None, env))
        self.assertIsNone(paths.work_path("  ", env))

    def test_ask_prepare_with_relative_out_dir_writes_under_the_data_dir(self):
        from ikimonobiyori import ask
        base = tempfile.mkdtemp()
        cwd = tempfile.mkdtemp()
        old = os.getcwd()
        try:
            os.chdir(cwd)
            with mock.patch.dict("os.environ", {"IKIMONOBIYORI_DATA_DIR": base}), redirect_stdout(io.StringIO()):
                self.assertEqual(ask.main(["prepare", "--out-dir", "work/rel-test", "--subject", "autumn_leaves", "--region", "神奈川",
                                           "--when", "2026-11-14", "--now", NOW.isoformat()]), 0)
        finally:
            os.chdir(old)
        self.assertTrue((Path(base) / "work" / "rel-test" / "params.json").exists())
        self.assertFalse((Path(cwd) / "work").exists())

    def test_backtest_out_dir_uses_work_path(self):
        src = (ROOT / "ikimonobiyori" / "backtest_run.py").read_text(encoding="utf-8")
        self.assertIn("paths.work_path(a.out_dir)", src)

    def test_help_says_relative_paths_are_under_the_data_dir(self):
        from ikimonobiyori import ask
        self.assertIn("相対パスは IKIMONOBIYORI_DATA_DIR からの相対", ask.__doc__)


if __name__ == "__main__":
    unittest.main()
