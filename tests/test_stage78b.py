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


class Leads(unittest.TestCase):
    """段階78 の追記 3(本人の指示 2026-11-11): 全体の目安は資料に入った名所の時期から。岩本山公園の梅の文を桜の時期にしない。"""

    def _sp(self, name, start, end, kinds, species="桜"):
        return dict(_row(name, start, kinds), end=end, species=species)

    def test_cherry_lead_by_group(self):
        from datetime import date
        rows = [self._sp("冬", "10-21", "12-10", ["冬桜"]), self._sp("早", "02-01", "03-10", ["河津桜"]),
                self._sp("春", "03-21", "04-10", ["ソメイヨシノ"]), self._sp("遅", "04-21", "05-10", ["八重桜"])]
        lines = GM.species_leads(rows, date(2026, 11, 11))["桜"]
        self.assertIn("冬桜 10月〜12月", lines[0])
        self.assertIn("春の桜 3月〜4月", lines[0])
        self.assertIn("遅咲き 4月〜5月", lines[0])
        self.assertNotIn("1月〜3月が目安", lines[0])
        self.assertIn("例年の時期にあたります", lines[1])     # 11 月は冬桜の時期

    def test_span_over_the_new_year(self):
        rows = [self._sp("a", "12-01", "01-31", ["水仙"], "水仙"), self._sp("b", "03-21", "04-20", ["スイセン"], "水仙")]
        self.assertEqual(GM._span(rows), (12, 4))
        self.assertEqual(GM._span([self._sp("c", "06-01", "06-30", ["ホタル"], "ホタル")]), (6, 6))

    def test_no_timed_rows(self):
        from datetime import date
        r = dict(self._sp("x", None, None, ["コスモス"], "コスモス"), season=None)
        self.assertEqual(GM.species_leads([r], date(2026, 11, 11))["コスモス"], ["コスモスの例年の時期は、資料の名所では分かりません。"])

    def test_season_text_of_another_kind_is_not_used(self):
        from ikimonobiyori import season_place as SP
        kinds = [{"kind": "梅"}, {"kind": "桜"}]
        self.assertTrue(SP._season_of_other_kind("梅は1月上旬から咲き始め2月下旬〜3月下旬頃まで", ["桜"], kinds))
        self.assertFalse(SP._season_of_other_kind("梅は1月上旬から咲き始め2月下旬〜3月下旬頃まで", ["梅"], kinds))
        self.assertFalse(SP._season_of_other_kind("3月下旬〜4月上旬", ["桜"], kinds))
        self.assertFalse(SP._season_of_other_kind("梅と桜が3月に", ["桜"], kinds))


if __name__ == "__main__":
    unittest.main()
