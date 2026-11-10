"""段階78 の追記(本人の指示 2026-11-11): 後半の月を省いた時期の読み方と、日付の指定がない種の質問の名所の枠。"""
import unittest
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_materials as GM
from ikimonobiyori import observations as O


class OmittedMonth(unittest.TestCase):
    def setUp(self):
        self.pol = O.load_policy()

    def test_second_half_takes_the_same_month(self):
        self.assertEqual(O.parse_typical("例年4月上旬〜下旬", self.pol), ("04-01", "04-30"))
        self.assertEqual(O.parse_typical("見頃は11月中旬～下旬", self.pol), ("11-11", "11-30"))
        self.assertEqual(O.parse_typical("例年の見頃は11月中旬から下旬", self.pol), ("11-11", "11-30"))

    def test_full_form_unchanged(self):
        self.assertEqual(O.parse_typical("4月上旬〜4月中旬", self.pol), ("04-01", "04-20"))
        self.assertEqual(O.parse_typical("11月中旬〜12月上旬", self.pol), ("11-11", "12-10"))

    def test_backward_third_is_not_guessed(self):
        # 「12月下旬〜上旬」は後半の月が分からないので補わない(今までどおり前半だけ)
        self.assertEqual(O.parse_typical("12月下旬〜上旬", self.pol), ("12-21", "12-31"))


def _row(name, start, kinds, km=30):
    return {"name": name, "prefecture": "東京都", "city": "試験市", "km": km, "km_estimated": False, "kinds": kinds,
            "start": start, "end": start, "season": "試験", "url": None, "official": True}


class Spread(unittest.TestCase):
    def setUp(self):
        self.conf = GM.cfg()["species_rows"]["spread"]

    def test_every_cherry_group_gets_a_place(self):
        rows = ([_row(f"早{i}", "02-01", ["河津桜"]) for i in range(10)] + [_row("冬", "11-01", ["冬桜"])]
                + [_row(f"春{i}", "03-21", ["ソメイヨシノ"]) for i in range(5)] + [_row("遅", "04-21", ["八重桜"])])
        got = GM.spread_rows(rows, "桜", 8, self.conf)
        groups = [GM.row_group(r, self.conf["groups"]["桜"]) for r in got]
        self.assertEqual(len(got), 8)
        for g in ("冬桜", "早咲き", "春の桜", "遅咲き"):
            self.assertIn(g, groups)
        self.assertGreaterEqual(groups.count("春の桜"), 3)

    def test_kind_and_date_decide_the_group(self):
        gs = self.conf["groups"]["桜"]
        self.assertEqual(GM.row_group(_row("a", "11-11", ["冬桜", "河津桜"]), gs), "冬桜")
        self.assertEqual(GM.row_group(_row("b", "03-21", ["ソメイヨシノ", "寒桜"]), gs), "春の桜")
        self.assertEqual(GM.row_group(_row("c", "02-11", ["桜"]), gs), "早咲き")     # 種で決まらなければ月日で

    def test_other_flowers_spread_over_months(self):
        rows = [_row(f"一{i}", "01-11", ["梅"]) for i in range(8)] + [_row("二", "02-11", ["梅"]), _row("三", "03-01", ["梅"])]
        got = GM.spread_rows(rows, "梅", 4, self.conf)
        self.assertEqual({r["start"][:2] for r in got}, {"01", "02", "03"})

    def test_only_when_no_date_is_given(self):
        rows = ([_row(f"早{i}", "02-01", ["河津桜"], km=10 + i) for i in range(14)] + [_row("春", "03-21", ["ソメイヨシノ"])])
        from ikimonobiyori import season_place as SP
        with mock.patch.object(SP, "gather", return_value=rows):
            spread = GM.species_rows("桜の見られる時期と場所を教えて", {"route": "season_place", "origin": "横浜", "defaulted_date": True})
            plain = GM.species_rows("桜の見られる時期と場所を教えて", {"route": "season_place", "origin": "横浜"})
        self.assertIn("春", [r["name"] for r in spread])
        self.assertNotIn("春", [r["name"] for r in plain])           # 今までどおり(今から近い順で枠まで)


if __name__ == "__main__":
    unittest.main()
