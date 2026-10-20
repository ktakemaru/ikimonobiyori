"""紅葉の答え合わせの通信しない部分(段階13 フェーズ4。ikimonobiyori/backtest.py)。合成データだけ。通信なし。"""
import copy
import unittest
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import backtest as B
from ikimonobiyori.config import load_config
from ikimonobiyori.profiles import load_profiles, param

PROFILE = load_profiles()["autumn_leaves"]


def series(year, change_on, before, after, start=None, end=None):
    """start〜end の日最低気温。change_on より前は before、以後は after。"""
    s = {}
    d, end = start or date(year, 8, 1), end or date(year, 12, 31)
    while d <= end:
        s[d.isoformat()] = before if d < change_on else after
        d += timedelta(days=1)
    return s


class Predict(unittest.TestCase):
    def test_uses_the_profile_thresholds_and_window(self):
        # 7 日平均 = (before × (7 − k) + after × k) ÷ 7(k = after の日数)。before 10、after 4 なら
        # 8 以下(色づき始め)は k ≥ 3 → 11/12、6 以下(見頃)は k ≥ 5 → 11/14
        self.assertEqual((param(PROFILE, "start_min_temp_c"), param(PROFILE, "advance_min_temp_c"), param(PROFILE, "mean_window_days")), (8, 6, 7))
        s = series(2024, date(2024, 11, 10), 10, 4)
        p = B.predict(s, PROFILE, 2024)
        self.assertEqual(p["date"], "2024-11-14")
        self.assertEqual(p["first"], {"before_bud": "2024-09-01", "early_bloom": "2024-11-12", "peak": "2024-11-14"})
        self.assertEqual((p["days"], p["missing_days"]), (122, 0))                        # 9/1〜12/31
        self.assertEqual(B.predict(s, PROFILE, 2024, target_stage="early_bloom")["date"], "2024-11-12")

    def test_follows_the_profile_when_thresholds_change(self):
        prof = copy.deepcopy(PROFILE)
        for q in prof["method"]["params"]:
            if q["name"] == "advance_min_temp_c":
                q["value"] = 4
        s = series(2024, date(2024, 11, 10), 10, 4)
        self.assertEqual(B.predict(s, prof, 2024)["date"], "2024-11-16")                 # k = 7 で平均 4

    def test_missing_days_are_skipped_not_zero_filled(self):
        s = series(2024, date(2024, 11, 10), 10, 4)
        s["2024-10-01"] = None
        p = B.predict(s, PROFILE, 2024)
        self.assertEqual((p["date"], p["missing_days"]), ("2024-11-14", 7))               # 10/1〜10/7 の平均が出せない
        del s["2024-11-12"]
        self.assertEqual(B.predict(s, PROFILE, 2024)["date"], "2024-11-19")               # 11/12 を含む窓(11/12〜11/18)は飛ばす

    def test_no_peak_in_the_season_gives_none(self):
        p = B.predict(series(2024, date(2024, 11, 10), 12, 9), PROFILE, 2024)
        self.assertIsNone(p["date"])
        self.assertNotIn("peak", p["first"])

    def test_season_and_fetch_range_come_from_the_profile(self):
        self.assertEqual(B.season_range(PROFILE, 2025), (date(2025, 9, 1), date(2025, 12, 31)))
        self.assertEqual(B.fetch_range(PROFILE, 2025), (date(2025, 8, 26), date(2025, 12, 31)))


class Compare(unittest.TestCase):
    PAIRS = [B.pair("662", 2021, "2021-11-20", "2021-11-25"), B.pair("662", 2022, "2022-12-01", "2022-11-30"),
             B.pair("670", 2021, "2021-11-28", "2021-11-28"), B.pair("670", 2022, "2022-12-20", "2022-12-08"),
             B.pair("626", 2022, None, "2022-11-27"), B.pair("626", 2021, "2021-11-26", None)]

    def test_pair_difference_is_predicted_minus_observed(self):
        self.assertEqual([p["diff_days"] for p in self.PAIRS], [-5, 1, 0, 12, None, None])

    def test_aggregate(self):
        a = B.aggregate(self.PAIRS, tolerances=(3, 7))
        o = a["overall"]
        self.assertEqual((o["n"], o["median"], o["mean"], o["min"], o["max"], o["mad"]), (4, 0.5, 2.0, -5, 12, 3.0))   # |差 − 0.5| = 5.5, 0.5, 0.5, 11.5 の中央値
        self.assertEqual(o["within"], {"3": 0.5, "7": 0.75})
        self.assertEqual((a["no_prediction"], a["no_observation"], a["pairs"]), (1, 1, 6))
        self.assertEqual(sorted(a["by_station"]), ["662", "670"])
        self.assertEqual(a["by_station"]["670"]["median"], 6)
        self.assertEqual(a["by_year"][2022]["n"], 2)

    def test_empty_and_single_inputs(self):
        a = B.aggregate([], tolerances=(3,))
        self.assertEqual((a["overall"]["n"], a["overall"]["median"], a["overall"]["within"]), (0, None, {"3": None}))
        one = B.aggregate([self.PAIRS[0]])["overall"]
        self.assertEqual((one["n"], one["stdev"], one["quartiles"]), (1, None, None))

    def test_report_has_no_verdict_and_lists_tolerances(self):
        md = B.report_markdown(B.aggregate(self.PAIRS, tolerances=(3, 7)), title="合成", notes=["合成データ"])
        self.assertIn("±3日以内", md)
        self.assertIn("| 全体 | 4 | 0.5 | 2.0 |", md)
        self.assertIn("予測なし 1、観測なし 1", md)
        self.assertNotIn("合格です", md)
        self.assertEqual(md, B.report_markdown(B.aggregate(list(self.PAIRS), tolerances=(3, 7)), title="合成", notes=["合成データ"]))   # 決定論

    def test_observed_dates_filter(self):
        rows = [{"station_no": "662", "phenomenon": "kaede_koyo", "year": "2021", "date": "2021-11-25", "status": "observed", "rm": "9"},
                {"station_no": "662", "phenomenon": "kaede_koyo", "year": "2022", "date": "", "status": "no_value", "rm": ""},
                {"station_no": "670", "phenomenon": "kaede_koyo", "year": "2021", "date": "2021-11-28", "status": "observed", "rm": "8"},
                {"station_no": "670", "phenomenon": "icho_koyo", "year": "2021", "date": "2021-11-20", "status": "observed", "rm": "8"},
                {"station_no": "675", "phenomenon": "kaede_koyo", "year": "2005", "date": "2005-12-01", "status": "observed", "rm": "8"}]
        self.assertEqual(B.observed_dates(rows, "kaede_koyo"), {("662", 2021): "2021-11-25", ("670", 2021): "2021-11-28", ("675", 2005): "2005-12-01"})
        self.assertEqual(B.observed_dates(rows, "kaede_koyo", station_nos={"662", "670"}, years=range(2016, 2026), rm={"8"}),
                         {("670", 2021): "2021-11-28"})


class DecidedCriterionParts(unittest.TestCase):
    """2026-10-21 に決めた合格基準(案3)に要る部品: 平均絶対誤差と平年値法の基準線。合否の判定そのものは書かない。"""

    def test_mean_absolute_error(self):
        a = B.aggregate(Compare.PAIRS)
        self.assertEqual(a["overall"]["mae"], 4.5)                                         # (5 + 1 + 0 + 12) / 4
        self.assertIsNone(B.aggregate([])["overall"]["mae"])
        self.assertIn("| 平均絶対誤差 |", B.report_markdown(a, title="合成"))

    OBS = {("662", 2021): "2021-11-25", ("662", 2022): "2022-11-30", ("662", 2023): "2023-12-02",
           ("670", 2021): "2021-11-28", ("670", 2022): "2023-01-02"}                         # 670 の 2022 年は年またぎ(翌年 1/2)

    def test_climatology_leave_one_out(self):
        got = {(p["station"], p["year"]): (p["predicted"], p["diff_days"]) for p in B.climatology_pairs(self.OBS, mode="leave_one_out")}
        # 662 の 2021 年: 他の年の 1/1 からの日数 333(11/30)と 335(12/2)の中央値 334 → 2021-12-01、差 334 − 328 = 6
        self.assertEqual(got[("662", 2021)], ("2021-12-01", 6))
        self.assertEqual(got[("662", 2022)], ("2022-11-28", -1.5))                          # (328 + 335) / 2 = 331.5(切り捨てて 11/28)− 333
        self.assertEqual(got[("670", 2021)], ("2022-01-02", 35))                            # 他の年は年をまたいだ 366 日目
        self.assertEqual(got[("670", 2022)], ("2022-11-28", -35))

    def test_climatology_prior_only(self):
        ps = B.climatology_pairs(self.OBS, mode="prior_only")
        got = {(p["station"], p["year"]): p["diff_days"] for p in ps}
        self.assertEqual(got, {("662", 2021): None, ("662", 2022): -5, ("662", 2023): -4.5, ("670", 2021): None, ("670", 2022): -35})
        self.assertEqual(B.aggregate(ps)["no_prediction"], 2)

    def test_climatology_mode_must_be_chosen(self):
        with self.assertRaises(TypeError):
            B.climatology_pairs(self.OBS)
        with self.assertRaises(ValueError):
            B.climatology_pairs(self.OBS, mode="all")


class ArchiveQuery(unittest.TestCase):
    def test_query_with_and_without_elevation(self):
        q = B.archive_query(lat=35.69, lon=139.75, start_date="2025-08-26", end_date="2025-12-31", elevation=25)
        u = urlsplit(q["url"])
        self.assertEqual((u.scheme, u.netloc, u.path), ("https", "archive-api.open-meteo.com", "/v1/archive"))
        self.assertEqual(parse_qs(u.query), {"latitude": ["35.69"], "longitude": ["139.75"], "start_date": ["2025-08-26"], "end_date": ["2025-12-31"],
                                             "daily": ["temperature_2m_min"], "timezone": ["Asia/Tokyo"], "elevation": ["25"]})
        self.assertNotIn("elevation", B.archive_query(lat=35.69, lon=139.75, start_date="2025-08-26", end_date="2025-12-31")["params"])

    def test_the_archive_host_is_not_allowed_yet(self):
        # 段階14 で実通信するには、許可ホストの追加(ユーザーの承認)が要る。ここでは広げない
        live = load_config()["live"]
        self.assertNotIn("archive-api.open-meteo.com", live["allowed_hosts"])
        self.assertNotIn("archive-api.open-meteo.com", sum(live["allowed_hosts_by_subject"].values(), []))


if __name__ == "__main__":
    unittest.main()
