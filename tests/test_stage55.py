"""段階55: 曜日チェックの年またぎ（第7部）ほか。合成データ・通信しない。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import festivals as F, season


def chk(text, year=2026):
    return season.weekday_check(text, year)


class CrossYear(unittest.TestCase):
    def test_cross_year_range_with_explicit_years_passes(self):
        r = chk("2026年12月25日（金）〜2027年1月3日（日）")
        self.assertEqual((r["checked"], r["mismatches"]), (2, []))

    def test_omitted_end_year_is_the_next_matching_date(self):
        for t in ("2026年12月25日（金）～1月3日（日）", "12/25(金)〜1/3(日)"):
            self.assertEqual(chk(t)["mismatches"], [], t)
        self.assertEqual(chk("2026年12月25日（金）～1月4日（日）")["mismatches"], ["1月4日（日）"])     # 2027-01-04 は月曜

    def test_each_date_is_checked_in_its_own_year(self):
        self.assertEqual(chk("2026年12月25日（土）～2027年1月3日（日）")["mismatches"], ["2026年12月25日（土）"])
        self.assertEqual(chk("2026年12月25日（金）～2027年1月3日（月）")["mismatches"], ["2027年1月3日（月）"])

    def test_day_only_end_inherits_the_month(self):
        self.assertEqual(chk("2026年10月23日（金）～24日（土）"), {"checked": 2, "mismatches": []})
        self.assertEqual(chk("10月30日（金）～11月1日（日）、11月6日（金）～8日（日）")["mismatches"], [])

    def test_known_calendar_values(self):
        self.assertEqual(date(2026, 12, 25).weekday(), 4)           # 金
        self.assertEqual(date(2027, 1, 1).weekday(), 4)             # 金
        self.assertEqual(date(2027, 1, 3).weekday(), 6)             # 日

    def test_same_year_behaviour_is_unchanged(self):
        self.assertEqual(chk("11/21(土)")["mismatches"], [])
        self.assertEqual(chk("11/21(日)")["mismatches"], ["11/21(日)"])
        self.assertEqual(chk("10/25(土)")["mismatches"], ["10/25(土)"])           # 2026年の10/25は日曜（前年の暦の日付）
        self.assertEqual(chk("2/30(月)")["mismatches"], ["2/30(月)"])             # 存在しない日付は不一致
        self.assertEqual(chk("日付なし")["checked"], 0)

    def test_previous_year_by_weekday(self):
        self.assertFalse(season.previous_year_by_weekday("2026年12月25日（金）〜2027年1月3日（日）", date(2026, 11, 7)))
        self.assertTrue(season.previous_year_by_weekday("12/25(木)〜1/3(土)", date(2026, 11, 7)))        # 前年の暦のまま残った日付
        self.assertIsNone(season.previous_year_by_weekday("曜日なしの 12/25〜1/3", date(2026, 11, 7)))


class FestivalCrossYear(unittest.TestCase):
    def fest(self, raw, start="2026-12-25", end="2027-01-03"):
        return {"id": "t", "name": "試験の冬の催し", "start": start, "end": end, "raw": raw, "organizer": "試験", "organizer_class": "official",
                "url": "https://example.org/", "spots": ["x"]}

    def test_cross_year_event_is_usable(self):
        ok, why = F.usable(self.fest(["2026年12月25日（金）〜2027年1月3日（日）"]), date(2026, 11, 7))
        self.assertEqual((ok, why), (True, None))

    def test_wrong_weekday_is_dropped(self):
        ok, why = F.usable(self.fest(["2026年12月25日（土）〜2027年1月3日（日）"]), date(2026, 11, 7))
        self.assertEqual((ok, why), (False, "weekday_mismatch"))

    def test_last_season_event_is_still_dropped(self):
        ok, why = F.usable(self.fest(["2025年12月25日（木）〜2026年1月3日（土）"], "2025-12-25", "2026-01-03"), date(2026, 11, 7))
        self.assertEqual((ok, why), (False, "other_year"))

    def test_moonlight_rose_garden_is_now_present(self):
        doc = F.load()
        self.assertIn("ibaraki-moonlight-rose-2026", {f["id"] for f in doc["festivals"]})
        self.assertEqual(F.dropped(date(2026, 11, 7), doc), {})


if __name__ == "__main__":
    unittest.main()
