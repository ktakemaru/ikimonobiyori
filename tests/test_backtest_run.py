"""紅葉の答え合わせの実行部分(段階14): 問い合わせの一覧・取得層・判定・CLI。合成データと偽の http_get だけ。通信なし。"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import backtest as B
from ikimonobiyori import backtest_run
from ikimonobiyori import jma_phenology as J
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError, archive_live
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.fetch.live import LiveError
from ikimonobiyori.profiles import load_profiles

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 22, 21, 0, tzinfo=JST)
CFG = load_config()
PROFILE = load_profiles()["autumn_leaves"]
PLAN = B.load_plan()
STATIONS = J.load_definition()["stations"]
REQS = B.build_requests(PLAN, STATIONS, PROFILE)


def body_for(req, base=5.0, **over):
    """応答の合成(Open-Meteo Historical API の形)。"""
    first = date.fromisoformat(req["params"]["start_date"])
    days = [(first + timedelta(days=i)).isoformat() for i in range(req["expected_days"])]
    resp = {"latitude": req["params"]["latitude"], "longitude": req["params"]["longitude"], "elevation": req["elevation"] if req["elevation"] is not None else 30.0,
            "utc_offset_seconds": 32400, "timezone": "Asia/Tokyo", "daily_units": {"time": "iso8601", "temperature_2m_min": "°C"},
            "daily": {"time": days, "temperature_2m_min": [base] * len(days)}}
    resp.update(over)
    return json.dumps(resp)


class FakeHttp:
    def __init__(self, status=200, mutate=None):
        self.calls, self.status, self.mutate = [], status, mutate
        self.by_url = {r["url"]: r for r in REQS}

    def __call__(self, url):
        self.calls.append(url)
        if self.status != 200:
            return self.status, json.dumps({"error": True, "reason": "x"}), {"X-Ratelimit-Remaining": "1"}
        body = body_for(self.by_url[url])
        if self.mutate:
            body = self.mutate(json.loads(body), self.by_url[url])
            body = json.dumps(body)
        return 200, body, {"X-Ratelimit-Remaining": "59", "Content-Type": "application/json"}


def run(reqs, http, cache, **kw):
    sleeps = []
    kw.setdefault("live", True)
    kw.setdefault("max_requests", 10)
    out = fetch_run(reqs, http, cache, sleeps, **kw)
    return out, sleeps


def fetch_run(reqs, http, cache, sleeps, **kw):
    return archive_live.fetch_archive(reqs, cache=cache, cfg=CFG, now=NOW, http_get=http, unparsed_dir=tempfile.mkdtemp(), sleep=sleeps.append, **kw)


class Requests(unittest.TestCase):
    def test_plan_is_180_requests_in_a_fixed_order(self):
        self.assertEqual(len(REQS), 180)                                                  # 9 地点 × 10 年 × 標高あり/なし
        self.assertEqual([r["id"] for r in REQS[:3]], ["610-2016-with", "610-2016-without", "610-2017-with"])
        self.assertEqual({r["station_no"] for r in REQS}, set(PLAN["station_nos"]))
        self.assertEqual({r["year"] for r in REQS}, set(range(2016, 2026)))
        self.assertEqual({urlsplit(r["url"]).netloc for r in REQS}, {"archive-api.open-meteo.com"})

    def test_query_has_models_timezone_period_and_elevation_only_for_with(self):
        for r in REQS:
            q = {k: v[0] for k, v in parse_qs(urlsplit(r["url"]).query).items()}
            self.assertEqual((q["models"], q["timezone"], q["daily"]), ("era5_land", "Asia/Tokyo", "temperature_2m_min"))
            self.assertEqual((q["start_date"], q["end_date"]), (f"{r['year']}-08-26", f"{r['year']}-12-31"))      # 季節 9〜12 月 + 平均日数 7 − 1 日前
            self.assertEqual("elevation" in q, r["mode"] == "with")
        tokyo = next(r for r in REQS if r["id"] == "662-2025-with")
        self.assertEqual(parse_qs(urlsplit(tokyo["url"]).query)["elevation"], ["25"])
        self.assertEqual(tokyo["expected_days"], 128)

    def test_a_station_without_coordinates_is_an_error(self):
        sts = [dict(s, lat=None) if s["station_no"] == "610" else s for s in STATIONS]
        with self.assertRaises(ValueError):
            B.build_requests(PLAN, sts, PROFILE)

    def test_the_nine_stations_have_coordinates_from_the_jma_list(self):
        by = {s["station_no"]: s for s in STATIONS}
        for no in PLAN["station_nos"]:
            s = by[no]
            self.assertTrue(30 < s["lat"] < 40 and 135 < s["lon"] < 142 and s["elevation_m"] >= 0, no)
            self.assertRegex(s["ame_no"], r"^\d{5}$")
        self.assertEqual((by["662"]["name"], by["662"]["elevation_m"]), ("東京", 25))
        self.assertTrue(all(by[no]["lat"] is None for no in ("618", "637", "672")))       # 範囲外の地点は書いていない


class Fetch(unittest.TestCase):
    def setUp(self):
        self.cache = Cache(tempfile.mkdtemp())

    def test_fetches_caches_and_does_not_repeat(self):
        http = FakeHttp()
        (series, rep), sleeps = run(REQS[:3], http, self.cache)
        self.assertEqual((rep["requests"], len(series), len(http.calls)), (3, 3, 3))
        self.assertEqual(len(sleeps), 2)                                                  # 通信の間だけ待つ(最初の前は待たない)
        self.assertTrue(all(0 < s <= CFG["live"]["min_interval_s"] for s in sleeps))
        (series2, rep2), _ = run(REQS[:3], http, self.cache)
        self.assertEqual((rep2["requests"], rep2["cache_hits"], len(http.calls)), (0, 3, 3))
        self.assertEqual(series2, series)

    def test_logs_status_and_rate_headers_only(self):
        logs = []
        run(REQS[:1], FakeHttp(), self.cache, log=logs.append)
        self.assertEqual(logs[0]["status"], 200)
        self.assertEqual(logs[0]["rate_headers"], {"X-Ratelimit-Remaining": "59"})
        self.assertNotIn("latitude", json.dumps(logs))

    def test_max_requests_limits_the_sends(self):
        http = FakeHttp()
        (series, rep), _ = run(REQS[:5], http, self.cache, max_requests=2)
        self.assertEqual((len(http.calls), len(series), len(rep["misses"])), (2, 2, 3))

    def test_429_stops_without_retrying(self):
        http = FakeHttp(status=429)
        with self.assertRaises(LiveError) as cm:
            run(REQS[:3], http, self.cache)
        self.assertEqual(len(http.calls), 1)
        self.assertIn("429", str(cm.exception))

    def test_other_non_200_stops_too_even_503(self):
        http = FakeHttp(status=503)
        with self.assertRaises(LiveError):
            run(REQS[:3], http, self.cache)
        self.assertEqual(len(http.calls), 1)                                               # 再試行しない

    def test_host_not_in_the_list_is_not_sent(self):
        bad = dict(REQS[0], url="https://example.invalid/v1/archive?x=1")
        http = FakeHttp()
        with self.assertRaises(LiveError):
            run([bad], http, self.cache)
        self.assertEqual(http.calls, [])

    def test_unexpected_shapes_stop_and_save_the_response(self):
        cases = {
            "変数名": lambda d, r: dict(d, daily={"time": d["daily"]["time"], "temperature_2m_mean": d["daily"]["temperature_2m_min"]}),
            "余分な項目": lambda d, r: dict(d, daily=dict(d["daily"], precipitation_sum=[0] * len(d["daily"]["time"]))),
            "日数": lambda d, r: dict(d, daily={"time": d["daily"]["time"][:-1], "temperature_2m_min": d["daily"]["temperature_2m_min"][:-1]}),
            "timezone": lambda d, r: dict(d, timezone="GMT"),
            "標高": lambda d, r: dict(d, elevation=999.0),
            "エラー": lambda d, r: {"error": True, "reason": "Cannot initialize SurfaceModel"},
        }
        for name, mut in cases.items():
            with self.subTest(name):
                cache, d = Cache(tempfile.mkdtemp()), tempfile.mkdtemp()
                with self.assertRaises(ParseError) as cm:
                    archive_live.fetch_archive(REQS[:1], cache=cache, cfg=CFG, now=NOW, http_get=FakeHttp(mutate=mut), live=True, max_requests=3,
                                               unparsed_dir=d, sleep=lambda s: None)
                self.assertIn("実応答を保存", str(cm.exception))
                self.assertEqual(len(list(Path(d).glob("*.json"))), 1)
                self.assertEqual(list(Path(cache.dir).glob("*.json")) if Path(cache.dir).exists() else [], [])      # 壊れた応答はキャッシュしない

    def test_null_temperatures_are_kept_as_none(self):
        http = FakeHttp(mutate=lambda d, r: dict(d, daily=dict(d["daily"], temperature_2m_min=[None] + d["daily"]["temperature_2m_min"][1:])))
        (series, _), _ = run(REQS[:1], http, self.cache)
        self.assertIsNone(series[REQS[0]["id"]][REQS[0]["params"]["start_date"]])

    def test_cache_only_never_sends(self):
        http = FakeHttp()
        run(REQS[:1], http, self.cache)
        (series, rep), _ = run(REQS[:2], http, self.cache, live=False, cache_only=True, max_requests=None)
        self.assertEqual((len(series), rep["misses"], len(http.calls)), (1, [REQS[1]["id"]], 1))

    def test_live_requires_explicit_max_requests(self):
        with self.assertRaises(ValueError):
            run(REQS[:1], FakeHttp(), self.cache, max_requests=None)


def pair(no, year, pred, obs):
    return B.pair(no, year, pred, obs)


class Judge(unittest.TestCase):
    """決定事項の各条件(docs/stage14-decisions.md)。v0 と平年値法の差を直接与えて、境界を確かめる。"""

    def v0(self, diffs, n_none=0):
        out = [{"station": "662", "year": 2000 + i, "predicted": "2000-11-01", "observed": "2000-11-01", "diff_days": d} for i, d in enumerate(diffs)]
        out += [{"station": "670", "year": 2000 + i, "predicted": None, "observed": "2000-11-01", "diff_days": None} for i in range(n_none)]
        return out

    def clim(self, diffs, n_none=0):
        return self.v0(diffs, 0) + [{"station": "670", "year": 2000 + i, "predicted": "x", "observed": "y", "diff_days": 9} for i in range(n_none)]

    def test_passes_when_all_three_hold(self):
        j = B.judge(PLAN, self.v0([1, -2, 3]), self.clim([5, 5, 5]))
        self.assertTrue(j["passed"])
        self.assertEqual((j["mae_v0"], j["mae_climatology"], j["median_diff_all_v0_pairs"]), (2, 5, 1))

    def test_median_of_exactly_3_days_is_inside_and_over_is_not(self):
        self.assertTrue(B.judge(PLAN, self.v0([3, 3, 3]), self.clim([9, 9, 9]))["passed"])
        self.assertTrue(B.judge(PLAN, self.v0([-3, -3, -3]), self.clim([9, 9, 9]))["passed"])
        j = B.judge(PLAN, self.v0([3.5, 3.5, 3.5]), self.clim([9, 9, 9]))
        self.assertFalse(j["passed"])
        self.assertFalse(j["conditions"]["median_within_tolerance"])

    def test_mae_equal_to_climatology_fails(self):
        j = B.judge(PLAN, self.v0([2, 2, 2]), self.clim([2, 2, 2]))
        self.assertFalse(j["conditions"]["mae_v0_smaller_than_climatology"])
        self.assertFalse(j["passed"])

    def test_no_prediction_ratio_exactly_20_percent_is_ok_over_is_not(self):
        ok = B.judge(PLAN, self.v0([1, 1, 1, 1], n_none=1), self.clim([5, 5, 5, 5], n_none=1))           # 1 ÷ 5 = 0.2
        self.assertEqual(ok["no_prediction_ratio"], 0.2)
        self.assertTrue(ok["conditions"]["no_prediction_ratio_within_limit"])
        bad = B.judge(PLAN, self.v0([1, 1, 1], n_none=1), self.clim([5, 5, 5], n_none=1))               # 1 ÷ 4 = 0.25
        self.assertFalse(bad["conditions"]["no_prediction_ratio_within_limit"])
        self.assertFalse(bad["passed"])
        self.assertIn("予測なしの割合", "".join(bad["reasons"]))

    def test_mae_uses_only_the_common_pairs(self):
        # v0 は 1 組だけ大きく外れるが、平年値法が差を出せない組(clim の diff なし)は MAE に入れない
        v0 = self.v0([1, 1, 20])
        clim = self.clim([5, 5, 5])
        clim[2]["diff_days"] = None
        j = B.judge(PLAN, v0, clim)
        self.assertEqual((j["pairs_common"], j["mae_v0"], j["mae_climatology"], j["pairs_v0_with_diff"]), (2, 1, 5, 3))
        self.assertEqual(j["median_diff_all_v0_pairs"], 1)                                # 中央値は v0 の全組
        self.assertEqual(j["median_diff_common_pairs"], 1)

    def test_empty_input_fails_with_a_reason(self):
        j = B.judge(PLAN, [], [])
        self.assertFalse(j["passed"])
        self.assertTrue(j["reasons"])

    def test_the_criteria_come_from_the_plan_not_the_code(self):
        plan = json.loads(json.dumps(PLAN))
        plan["pass_criteria"]["tolerance_days"] = 1
        self.assertFalse(B.judge(plan, self.v0([3, 3, 3]), self.clim([9, 9, 9]))["passed"])

    def test_plan_values_are_the_decided_ones(self):
        self.assertEqual((PLAN["pass_criteria"]["tolerance_days"], PLAN["pass_criteria"]["max_no_prediction_ratio"]), (3, 0.2))
        self.assertEqual((PLAN["climatology"]["mode"], PLAN["models"], PLAN["decisive_elevation_mode"]), ("leave_one_out", "era5_land", "with"))
        self.assertEqual((PLAN["year_from"], PLAN["year_to"], PLAN["target_stage"]), (2016, 2025, "peak"))


class Evaluate(unittest.TestCase):
    """合成の観測と気温で evaluate を通す。気温は、各年の 11/10 から急に下がる(7 日平均が 6℃ 以下になる最初の日 = 11/14)。"""

    def setUp(self):
        self.plan = json.loads(json.dumps(PLAN))
        self.plan["station_nos"] = ["662", "670"]
        self.plan["year_to"] = 2018
        self.reqs = B.build_requests(self.plan, STATIONS, PROFILE)

    def series(self, req, drop=date(2000, 11, 10)):
        first = date.fromisoformat(req["params"]["start_date"])
        s = {}
        for i in range(req["expected_days"]):
            d = first + timedelta(days=i)
            s[d.isoformat()] = 10 if d < date(req["year"], drop.month, drop.day) else 4
        return s

    def rows(self, obs):
        rows = []
        for (no, y), iso in obs.items():
            for ph in (self.plan["phenomenon"], self.plan["reference_phenomenon"]):
                rows.append({"phenomenon": ph, "status": "observed", "station_no": no, "year": str(y), "date": iso, "rm": "8"})
        return rows

    def test_end_to_end_numbers(self):
        series = {r["id"]: self.series(r) for r in self.reqs}
        obs = {("662", 2016): "2016-11-16", ("662", 2017): "2017-11-10", ("662", 2018): "2018-11-12", ("670", 2016): "2016-11-14", ("670", 2017): "2017-11-14"}
        res = B.evaluate(self.plan, STATIONS, PROFILE, series, self.rows(obs))
        self.assertEqual(res["counts"], {"all_pairs": 6, "with_observation": 5, "without_observation": 1, "icho_with_observation": 5})
        m = res["modes"]["with"]
        # v0 の予測は毎年 11/14(7 日平均 = (10 × (7 − k) + 4 × k) ÷ 7 ≦ 6 は k ≧ 5)。差: −2, +4, +2, 0, 0
        self.assertEqual(sorted(p["diff_days"] for p in m["pairs"]), [-2, 0, 0, 2, 4])
        j = m["judge"]
        self.assertEqual((j["pairs_with_observation"], j["no_prediction"], j["median_diff_all_v0_pairs"]), (5, 0, 0))
        self.assertAlmostEqual(j["mae_v0"], 1.6)
        self.assertEqual(res["passed"], j["passed"])
        self.assertIn("early_bloom", res["reference"]["kaede_early_bloom"]["stage"])
        md = B.result_markdown(res)
        self.assertIn("合否", md)
        self.assertNotIn("判定はしない", md)                                               # 結果の文書は合否を書く(report_markdown の注記は入れない)
        self.assertIn("## 参考: icho_peak", md)

    def test_missing_temperature_input_is_an_error_not_no_prediction(self):
        series = {r["id"]: self.series(r) for r in self.reqs if r["id"] != "662-2016-with"}
        with self.assertRaises(KeyError):
            B.evaluate(self.plan, STATIONS, PROFILE, series, self.rows({("662", 2016): "2016-11-16"}))

    def test_no_prediction_is_counted_when_the_season_never_gets_cold(self):
        series = {r["id"]: {k: 10 for k in self.series(r)} for r in self.reqs}             # 季節の間ずっと 10℃ → 見頃に入らない
        res = B.evaluate(self.plan, STATIONS, PROFILE, series, self.rows({("662", 2016): "2016-11-16", ("662", 2017): "2017-11-10"}))
        j = res["modes"]["with"]["judge"]
        self.assertEqual((j["no_prediction"], j["no_prediction_ratio"], j["passed"]), (2, 1.0, False))

    def test_climatology_uses_only_the_plan_years(self):
        series = {r["id"]: self.series(r) for r in self.reqs}
        obs = {("662", 2016): "2016-11-16", ("662", 2017): "2017-11-10", ("662", 2018): "2018-11-12"}
        rows = self.rows(obs) + [{"phenomenon": self.plan["phenomenon"], "status": "observed", "station_no": "662", "year": "1960", "date": "1960-10-01", "rm": "8"}]
        res = B.evaluate(self.plan, STATIONS, PROFILE, series, rows)
        self.assertEqual(res["counts"]["with_observation"], 3)                              # 1960 年は入らない
        diffs = sorted(p["diff_days"] for p in res["modes"]["with"]["pairs"])
        self.assertEqual(diffs, [-2, 2, 4])


class Cli(unittest.TestCase):
    def setUp(self):
        import os
        old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = tempfile.mkdtemp()                       # 取得の記録・読めなかった応答を実際の書き込み先に残さない
        self.addCleanup(lambda: os.environ.pop("IKIMONOBIYORI_DATA_DIR", None) if old is None else os.environ.__setitem__("IKIMONOBIYORI_DATA_DIR", old))

    def test_live_is_refused_under_test(self):
        # テスト中は --live を常に拒否する(BIYORI_UNDER_TEST=1)。注入した http_get がなければ通信しない
        d = tempfile.mkdtemp()
        rc = backtest_run.main(["fetch", "--now", NOW.isoformat(), "--live", "--max-requests", "1", "--limit", "1", "--cache-dir", d])
        self.assertEqual(rc, 4)

    def test_plan_counts_without_communicating(self):
        d = tempfile.mkdtemp()
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = backtest_run.main(["plan", "--now", NOW.isoformat(), "--cache-dir", d])
        info = json.loads(buf.getvalue())
        self.assertEqual((rc, info["requests"], info["cached"], info["to_fetch"]), (0, 180, 0, 180))
        self.assertAlmostEqual(info["worst_case_calls"], 1656.0)

    def test_fetch_with_injected_http_and_judge_roundtrip(self):
        import contextlib
        import io
        import os
        d, out = tempfile.mkdtemp(), os.environ["IKIMONOBIYORI_DATA_DIR"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = backtest_run.main(["fetch", "--now", NOW.isoformat(), "--live", "--max-requests", "2", "--limit", "2", "--cache-dir", d],
                                   http_get=FakeHttp(), sleep=lambda s: None)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["requests"], 2)
        log = (Path(out) / "backtest" / "fetch_log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 2)
        # 気温が揃っていなければ judge は止まる(予測なしと取り違えない)
        rc = backtest_run.main(["judge", "--now", NOW.isoformat(), "--normalized", str(H.ROOT / "data" / "jma_phenology" / "normalized.csv"), "--cache-dir", d])
        self.assertEqual(rc, 3)

    def test_over_the_daily_call_cap_is_refused(self):
        from unittest import mock
        plan = json.loads(json.dumps(PLAN))
        plan["cost"]["daily_call_cap"] = 100                                              # 最悪 9.2 call × 12 件 = 110.4 > 100
        http = FakeHttp()
        with mock.patch.object(B, "load_plan", return_value=plan):
            rc = backtest_run.main(["fetch", "--now", NOW.isoformat(), "--live", "--max-requests", "12", "--cache-dir", tempfile.mkdtemp()], http_get=http, sleep=lambda s: None)
            self.assertEqual(rc, 4)
            self.assertEqual(http.calls, [])
            rc = backtest_run.main(["fetch", "--now", NOW.isoformat(), "--live", "--max-requests", "10", "--cache-dir", tempfile.mkdtemp()], http_get=http, sleep=lambda s: None)
            self.assertEqual((rc, len(http.calls)), (0, 10))                              # 9.2 × 10 = 92 ≦ 100 は送る

if __name__ == "__main__":
    unittest.main()
