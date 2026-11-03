"""段階44: 地域の指定がない質問は、都道府県に縛らず登録済みの全範囲（出発地から片道250km前後）で答える。通信しない。"""
import unittest
from datetime import date, datetime, timezone, timedelta

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O, ask

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone(timedelta(hours=9)))


class AllRange(unittest.TestCase):
    def test_ask_default_region_is_all_range(self):
        self.assertEqual(ask.load_policy()["default_region"], "全範囲")

    def test_plan_covers_more_than_one_prefecture(self):
        p = O.plan("autumn_leaves", region="全範囲", dates=[date(2026, 11, 7)], now=NOW)
        self.assertIn("全範囲", p["region"])
        prefs = {i["id"] for i in p["items"]}
        kanagawa_only = O.plan("autumn_leaves", region=None, dates=[date(2026, 11, 7)], now=NOW)
        self.assertGreater(len(prefs), len({i["id"] for i in kanagawa_only["items"]}))

    def test_explicit_region_still_limits_to_that_region(self):
        p = O.plan("autumn_leaves", region="神奈川", dates=[date(2026, 11, 7)], now=NOW)
        self.assertNotIn("日光", " ".join(i["name"] for i in p["items"]))

    def test_unknown_distance_keeps_the_origin_prefecture_only(self):
        reg = O.resolve("全範囲", "横浜", O.load_policy())
        self.assertTrue(O.in_region({"prefecture": "神奈川県", "area": None}, reg, None, 250))      # 座標がなくても出発地の県は入れる
        self.assertFalse(O.in_region({"prefecture": "栃木県", "area": None}, reg, None, 250))       # 他県は距離が分からなければ入れない
        self.assertTrue(O.in_region({"prefecture": "栃木県", "area": None}, reg, 140, 250))
        self.assertFalse(O.in_region({"prefecture": "北海道", "area": None}, reg, 800, 250))
        reg_tokyo = O.resolve("全範囲", "東京", O.load_policy())
        self.assertTrue(O.in_region({"prefecture": "東京都", "area": None}, reg_tokyo, None, 250))
        self.assertFalse(O.in_region({"prefecture": "神奈川県", "area": None}, reg_tokyo, None, 250))

    def test_candidates_without_coordinates_in_the_home_prefecture_are_not_dropped(self):
        cat_pol = O.catalog_mod.load_policy()
        no_point = [c["name"] for c in O.all_candidates("autumn_leaves", O.load_policy(), None, None)
                    if O._distance(c, "横浜", cat_pol) is None and c.get("prefecture") == "神奈川県"]
        self.assertTrue(no_point)                                  # 座標のない神奈川の名所が実際にある
        p = O.plan("autumn_leaves", region="全範囲", dates=[date(2026, 11, 7)], now=NOW)
        names = {i["name"] for i in p["items"]} | set(p["fresh"])
        self.assertTrue(set(no_point) <= names, set(no_point) - names)

    def test_same_conditions_as_this_weekend_question_give_kanagawa_and_other_prefectures(self):
        dates = [date(2026, 11, 7), date(2026, 11, 8)]
        f = O.facts("autumn_leaves", region="全範囲", dates=dates, now=NOW, with_alternatives=False)
        prefs = {c["prefecture"] for c in f["candidates"] + f["avoid"]}
        self.assertIn("神奈川県", prefs)
        self.assertTrue(prefs - {"神奈川県"}, prefs)
        self.assertIn("三溪園", {c["name"] for c in f["candidates"] + f["avoid"]})                # 座標のない神奈川の名所
        p = O.plan("autumn_leaves", region="全範囲", dates=dates, now=NOW)
        self.assertEqual(p["region"], O.load_policy()["all_range_name"])


if __name__ == "__main__":
    unittest.main()
