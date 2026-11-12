"""段階83 第1部(段階82 の続き 2 の本人の判断 2026-11-13): カタログの月だけの窓は月のまま・「○年○月現在」を時期と読まない・
名指しで公式に含めた運営会社の名前。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import research as RS
from ikimonobiyori import season_place as SP

THIRDS = SP.cfg()["text"]["thirds"]


class CatalogMonthOnly(unittest.TestCase):
    def test_whole_months_without_thirds_in_note(self):
        w = {"start": "01-01", "end": "03-31", "note": "本文「開花時期 1月から3月」"}
        self.assertEqual(SP.catalog_window_text(w, THIRDS), "1月〜3月")
        self.assertEqual(SP.catalog_window_text({"start": "06-01", "end": "06-30", "note": "6月の欄"}, THIRDS), "6月")
        self.assertEqual(SP.catalog_window_text({"start": "01-01", "end": "02-28", "note": "菜の花(1～2月)"}, THIRDS), "1月〜2月")

    def test_thirds_in_note_or_no_note_keep_thirds(self):
        w = {"start": "03-01", "end": "03-31", "note": "例年3月上旬〜下旬"}
        self.assertEqual(SP.catalog_window_text(w, THIRDS), SP.window_text("03-01", "03-31", THIRDS))
        self.assertEqual(SP.catalog_window_text({"start": "03-01", "end": "03-31"}, THIRDS), SP.window_text("03-01", "03-31", THIRDS))
        self.assertEqual(SP.catalog_window_text({"start": "02-11", "end": "03-10", "note": "x"}, THIRDS), SP.window_text("02-11", "03-10", THIRDS))

    def test_year_round_stays(self):
        w = {"start": "01-01", "end": "12-31", "note": "通年"}
        self.assertEqual(SP.catalog_window_text(w, THIRDS), SP.window_text("01-01", "12-31", THIRDS))


class AsOfIsNotSeason(unittest.TestCase):
    def test_as_of_removed(self):
        p = O.load_policy()
        self.assertIsNone(O.parse_typical("冬には多くの野鳥が確認できる(確認された野鳥は267種。2021年1月現在)", p))
        self.assertIsNone(O.parse_typical("令和7年3月時点の記録", p))
        self.assertEqual(O.parse_typical("令和6年12月27日現在 1月〜2月", p), ("01-01", "02-28"))
        self.assertEqual(O.parse_typical("11月中旬～12月上旬", p), ("11-11", "12-10"))

    def test_strip_as_of_keeps_other_text(self):
        self.assertEqual(O.strip_as_of("2021年1月現在、267種"), "、267種")
        self.assertEqual(O.strip_as_of("1月現在"), "1月現在")    # 年のない書き方は今までどおり


class ApprovedOperator(unittest.TestCase):
    def test_named_operator_is_accepted(self):
        self.assertTrue(RS._declared_ok("中央アルプス観光株式会社"))
        self.assertTrue(RS._declared_ok("Chuo Alps Kanko Co., Ltd."))
        self.assertFalse(RS._declared_ok("ほかの観光株式会社"))
        self.assertTrue(RS._declared_ok("湯河原温泉観光協会"))


if __name__ == "__main__":
    unittest.main()
