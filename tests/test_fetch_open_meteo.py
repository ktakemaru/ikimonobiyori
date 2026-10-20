"""イキモノビヨリ(紅葉)の取得層(biyori-hub の tests/test_ikimono_live.py から移した。段階12。独立検査器 ikimono_check を使う部分は biyori-hub 側に残っている): キャッシュ・--cache-only・ParseError の保存・中止条件。すべて通信なし(偽の http_get)。"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H
from helpers import ROOT, run_child

from ikimonobiyori import engine, main as imain, profiles as ip
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError, live
from ikimonobiyori.fetch.cache import Cache, cache_key

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
CFG = load_config()
PROFS = ip.load_profiles()
SITES, _ = ip.load_sites()
AUT = PROFS["autumn_leaves"]
DATES = [datetime(2026, 10, 17).date(), datetime(2026, 10, 18).date()]


def resp(base=5.0, start="2026-10-08", days=12):
    t0 = datetime.fromisoformat(start)
    return {"latitude": 0, "longitude": 0, "daily": {"time": [(t0 + timedelta(days=i)).date().isoformat() for i in range(days)],
                                                   "temperature_2m_min": [base + (i % 3) * 0.5 for i in range(days)]}}


class FakeHttp:
    def __init__(self, status=200, body=None):
        self.calls, self.status, self.body = [], status, body

    def __call__(self, url):
        self.calls.append(url)
        return self.status, self.body if self.body is not None else json.dumps(resp())


def fetch(cache, http, *, live_=True, cache_only=False, max_requests=10, sites=("m001", "m002", "m013"), now=NOW, unparsed=None):
    return live.fetch_temperatures(list(sites), SITES, AUT, DATES, now.date(), now, cache=cache, cfg=CFG, http_get=http, live=live_,
                                   cache_only=cache_only, max_requests=max_requests if live_ else None,
                                   unparsed_dir=unparsed or tempfile.mkdtemp())


class CacheTests(unittest.TestCase):
    def test_key_is_order_independent_and_includes_url(self):
        self.assertEqual(cache_key("https://x/a", {"b": 1, "a": 2}), cache_key("https://x/a", {"a": 2, "b": 1}))
        self.assertNotEqual(cache_key("https://x/a", {"a": 1}), cache_key("https://x/b", {"a": 1}))
        self.assertNotEqual(cache_key("https://x/a", {"a": 1}), cache_key("https://x/a", {"a": 2}))

    def test_put_get_fresh_expired_miss(self):
        c = Cache(tempfile.mkdtemp())
        c.put(url="https://x/a", params={"p": 1}, body='{"k": 1}', source="S", fetched_at=NOW.isoformat(timespec="seconds"))
        e, st = c.get("https://x/a", {"p": 1}, now=NOW + timedelta(seconds=10), ttl_s=60)
        self.assertEqual((st, e["body"], e["source"], e["url"], e["fetched_at"]), ("fresh", '{"k": 1}', "S", "https://x/a", NOW.isoformat(timespec="seconds")))
        e, st = c.get("https://x/a", {"p": 1}, now=NOW + timedelta(seconds=61), ttl_s=60)
        self.assertEqual((e, st), (None, "expired"))
        e, st = c.get("https://x/a", {"p": 1}, now=NOW + timedelta(seconds=61), ttl_s=60, allow_expired=True)
        self.assertEqual(st, "expired")
        self.assertIsNotNone(e)
        self.assertEqual(c.get("https://x/other", {}, now=NOW, ttl_s=60), (None, "miss"))
        self.assertEqual([p.name for p in Path(c.dir).iterdir() if p.name.startswith(".")], [])    # 一時ファイルが残らない

    def test_default_cache_dir_is_runtime_not_snapshots(self):
        from ikimonobiyori import paths                                              # 段階12: 書き込み先の基準(IKIMONOBIYORI_DATA_DIR)からの相対
        self.assertEqual((CFG["cache"]["dir"], CFG["cache"]["unparsed_dir"]), ("cache", "_unparsed"))
        self.assertEqual(paths.data_path(CFG["cache"]["dir"], env={}), paths.PKG.parent / "runtime" / "ikimonobiyori" / "cache")   # 未設定は従来と同じ場所
        self.assertNotIn("snapshots", paths.data_path(CFG["cache"]["unparsed_dir"], env={}).parts)
        self.assertEqual(CFG["cache"]["ttl_s"]["open_meteo_forecast"], 10800)      # 3 時間(仮置き)
        self.assertEqual(CFG["live"]["allowed_hosts"], ["api.open-meteo.com"])


class FetchTests(unittest.TestCase):
    def test_miss_fetches_then_hit_does_not(self):
        c, http = Cache(tempfile.mkdtemp()), FakeHttp()
        inputs, rep = fetch(c, http)
        self.assertEqual((rep["requests"], rep["cache_hits"], len(http.calls)), (3, 0, 3))
        self.assertEqual(set(inputs["temperatures"]), {"m001", "m002", "m013"})
        self.assertTrue(all(not m["from_cache"] and m["fetched_at"] == NOW.isoformat(timespec="seconds") for m in inputs["temperatures_meta"].values()))
        http2 = FakeHttp()
        inputs2, rep2 = fetch(c, http2, now=NOW + timedelta(hours=1))
        self.assertEqual((rep2["requests"], rep2["cache_hits"], len(http2.calls)), (0, 3, 0))
        self.assertTrue(all(m["from_cache"] and m["fetched_at"] == NOW.isoformat(timespec="seconds") for m in inputs2["temperatures_meta"].values()))
        self.assertEqual(inputs["temperatures"], inputs2["temperatures"])

    def test_expired_entry_is_refetched(self):
        c, http = Cache(tempfile.mkdtemp()), FakeHttp()
        fetch(c, http)
        http2 = FakeHttp()
        _, rep = fetch(c, http2, now=NOW + timedelta(hours=3, seconds=1))          # TTL 3 時間を超えた
        self.assertEqual((rep["requests"], rep["cache_hits"]), (3, 0))

    def test_cache_only_never_calls_http(self):
        c = Cache(tempfile.mkdtemp())
        fetch(c, FakeHttp(), sites=("m001",))
        boom = FakeHttp(status=500)
        inputs, rep = fetch(c, boom, live_=False, cache_only=True, sites=("m001", "m002"))
        self.assertEqual(boom.calls, [])
        self.assertEqual((rep["requests"], rep["cache_hits"], rep["misses"]), (0, 1, ["m002"]))
        self.assertEqual(set(inputs["temperatures"]), {"m001"})
        self.assertTrue(any("キャッシュなし" in w for w in rep["warnings"]))
        _, rep = fetch(c, boom, live_=False, cache_only=True, sites=("m001",), now=NOW + timedelta(hours=4))
        self.assertEqual(rep["misses"], ["m001"])                                    # 期限切れは --cache-only では使わない
        with self.assertRaises(ValueError):
            fetch(c, boom, live_=False, cache_only=False)

    def test_max_requests_limits_live_calls(self):
        http = FakeHttp()
        _, rep = fetch(Cache(tempfile.mkdtemp()), http, max_requests=2)
        self.assertEqual((rep["requests"], len(http.calls), len(rep["misses"])), (2, 2, 1))
        with self.assertRaises(ValueError):
            live.fetch_temperatures(["m001"], SITES, AUT, DATES, NOW.date(), NOW, cache=Cache(tempfile.mkdtemp()), cfg=CFG,
                                    http_get=FakeHttp(), live=True, max_requests=None)

    def test_non_200_aborts_without_retry_and_is_not_cached(self):
        for status in (429, 403, 500):
            c, http = Cache(tempfile.mkdtemp()), FakeHttp(status=status, body="{}")
            with self.assertRaises(live.LiveError):
                fetch(c, http)
            self.assertEqual(len(http.calls), 1)                                      # 再試行しない・次の地点にも進まない
            self.assertEqual(list(Path(c.dir).glob("*.json")) if Path(c.dir).exists() else [], [])

    def test_parse_error_saves_raw_response_and_stops(self):
        d = Path(tempfile.mkdtemp())
        http = FakeHttp(body=json.dumps({"hourly": {}}))                              # 想定外の形(daily がない)
        with self.assertRaises(ParseError) as cm:
            fetch(Cache(tempfile.mkdtemp()), http, unparsed=d)
        saved = list(d.glob("*.json"))
        self.assertEqual(len(saved), 1)
        doc = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertEqual((doc["status"], doc["body"]), (200, '{"hourly": {}}'))
        self.assertTrue(doc["url"].startswith("https://api.open-meteo.com/"))
        self.assertIn(str(saved[0]), str(cm.exception))
        self.assertEqual(len(http.calls), 1)                                          # 止まる
        d2 = Path(tempfile.mkdtemp())
        with self.assertRaises(ParseError):
            fetch(Cache(tempfile.mkdtemp()), FakeHttp(body="<html>"), unparsed=d2)    # JSON でない
        self.assertEqual(len(list(d2.glob("*.json"))), 1)

    def test_disallowed_host_is_never_requested(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["live"]["allowed_hosts"] = ["example.invalid"]
        http = FakeHttp()
        with self.assertRaises(live.LiveError):
            live.fetch_temperatures(["m001"], SITES, AUT, DATES, NOW.date(), NOW, cache=Cache(tempfile.mkdtemp()), cfg=cfg,
                                    http_get=http, live=True, max_requests=3)
        self.assertEqual(http.calls, [])

    def test_needed_days_cover_the_mean_window(self):
        past, ahead, w = live.needed_days(AUT, DATES, NOW.date(), CFG["live"]["open_meteo"])
        self.assertEqual(w, [])
        # 対象日の最小(10/17)の 7 日平均は 10/11 から要る → 今日(10/14)から見て過去 3 日。予報は 10/18 まで = 今日を含めて 5 日
        self.assertEqual((past, ahead), (3, 5))
        far = [datetime(2026, 12, 1).date()]
        p2, a2, w2 = live.needed_days(AUT, far, NOW.date(), CFG["live"]["open_meteo"])
        self.assertEqual(a2, CFG["live"]["open_meteo"]["max_forecast_days"])
        self.assertTrue(w2)                                                           # 上限を超える分は警告して切り詰める


class Recorded(unittest.TestCase):
    """記録(2026-10-14)した実際の Open-Meteo 応答。合成ではない。CC BY 4.0 の帰属がファイルにある。"""
    PATH = ROOT / "tests" / "fixtures" / "recorded_open_meteo_2026-10-14.json"

    def inputs(self):
        return json.loads(self.PATH.read_text(encoding="utf-8"))

    def test_marked_recorded_with_attribution(self):
        d = self.inputs()
        self.assertTrue(d["recorded"])
        self.assertFalse(d["synthetic"])
        self.assertIn("CC BY 4.0", d["attribution"])
        self.assertIn("Open-Meteo", d["attribution"])
        self.assertIn("記録(2026-10-14)", d["note"])
        self.assertEqual(set(d["temperatures"]), {"m029", "m001", "m002"})

    def test_parser_reads_real_responses(self):
        from ikimonobiyori.fetch import open_meteo
        for sid, r in self.inputs()["temperatures"].items():
            s = open_meteo.parse_daily_tmin(r)
            self.assertEqual(len(s), 8)
            self.assertTrue(all(isinstance(v, float) for v in s.values()), sid)
            self.assertEqual(r["timezone"], "Asia/Tokyo")
            self.assertIn("elevation", r)                           # 応答のグリッド標高(山頂の標高とは違う)
            self.assertEqual(r["daily_units"]["temperature_2m_min"], "°C")

    def test_engine_on_recorded(self):
        d = self.inputs()
        req = {"schema": "biyori-request/1", "request_id": "rec", "intent": "weekend_outing", "origin": {"name": "x", "lat": 35.0, "lon": 139.0},
               "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-18T23:59:00+09:00"}, "interests": ["autumn_leaves"]}
        now = datetime.fromisoformat("2026-10-14T22:50:29+09:00")
        doc = engine.run(req, profiles=PROFS, sites=SITES, inputs=d, now=now)
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        st = {p["id"]: (p["phenology_stage"], p["suitability"]["band"]) for p in doc["proposals"]}
        self.assertEqual(st["ikimonobiyori:autumn_leaves:2026-10-17:m029"], ("before_bud", "no"))
        self.assertEqual(st["ikimonobiyori:autumn_leaves:2026-10-17:m001"], ("peak", "maybe"))
        self.assertEqual(st["ikimonobiyori:autumn_leaves:2026-10-18:m002"], ("peak", "maybe"))
        self.assertTrue(all(a["fetched_at"] == d["temperatures_meta"][sid]["fetched_at"] for a, sid in zip(doc["data_as_of"], sorted(d["temperatures"]))))


class EndToEnd(unittest.TestCase):
    def request_file(self):
        p = Path(tempfile.mkdtemp()) / "r.json"
        p.write_text(json.dumps({"schema": "biyori-request/1", "request_id": "e2e", "intent": "weekend_outing",
                                 "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-18T23:59:00+09:00"},
                                 "origin": {"name": "x", "lat": 35.0, "lon": 139.0}, "interests": ["autumn_leaves"]}), encoding="utf-8")
        return p

    def test_main_live_requires_env_max_requests_and_hook(self):
        import os
        r = self.request_file()
        env = {k: v for k, v in os.environ.items() if k not in ("BIYORI_ALLOW_LIVE", "BIYORI_REQ_LOG")}
        base = [sys.executable, "-X", "utf8", str(ROOT / "ikimonobiyori" / "main.py"), "--request", str(r), "--now", "2026-10-14T22:00:00+09:00", "--live"]
        run = lambda extra, e: run_child(base + extra, capture_output=True, text=True, encoding="utf-8", env=e)
        self.assertEqual(run(["--max-requests", "3"], env).returncode, 4)                                   # BIYORI_ALLOW_LIVE がない
        self.assertEqual(run([], dict(env, BIYORI_ALLOW_LIVE="1")).returncode, 4)                           # --max-requests がない  # gate-test
        self.assertEqual(run(["--max-requests", "3"], dict(env, BIYORI_ALLOW_LIVE="1")).returncode, 4)     # 計測フックがない  # gate-test

    def test_main_with_injected_http_produces_valid_proposal(self):
        import os
        pass                                                         # 偽の http_get を注入するので実通信にならない(ゲートは注入時に通る)
        r, cdir, inp_out, out = self.request_file(), tempfile.mkdtemp(), Path(tempfile.mkdtemp()) / "in.json", Path(tempfile.mkdtemp()) / "o.json"
        http = FakeHttp(body=json.dumps(resp(base=5.0, start="2026-10-11", days=8)))
        rc = imain.main(["--request", str(r), "--live", "--max-requests", "5", "--sites", "m001,m002,m013", "--now", NOW.isoformat(),
                         "--cache-dir", cdir, "--out", str(out), "--inputs-out", str(inp_out)], http_get=http)
        self.assertEqual(rc, 0)
        doc, inputs = json.loads(out.read_text(encoding="utf-8")), json.loads(inp_out.read_text(encoding="utf-8"))
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual((doc["diagnostics"]["api_calls"], doc["diagnostics"]["cache_hit"], len(http.calls)), (3, False, 3))
        self.assertEqual(len(doc["proposals"]), 6)
        self.assertEqual(len(doc["data_as_of"]), 3)
        self.assertTrue(all(a["fetched_at"] == NOW.isoformat(timespec="seconds") and a["url"].startswith("https://api.open-meteo.com/") for a in doc["data_as_of"]))
        self.assertTrue(all("SYNTHETIC" not in e["source"] for p in doc["proposals"] for e in p["evidence"]))
        # 2 回目: キャッシュヒット → 通信 0
        http2, out2 = FakeHttp(), Path(tempfile.mkdtemp()) / "o2.json"
        rc = imain.main(["--request", str(r), "--live", "--max-requests", "5", "--sites", "m001,m002,m013", "--now", (NOW + timedelta(minutes=5)).isoformat(),
                         "--cache-dir", cdir, "--out", str(out2)], http_get=http2)
        d2 = json.loads(out2.read_text(encoding="utf-8"))
        self.assertEqual((rc, http2.calls, d2["diagnostics"]["api_calls"], d2["diagnostics"]["cache_hit"]), (0, [], 0, True))
        self.assertEqual([p["id"] for p in d2["proposals"]], [p["id"] for p in doc["proposals"]])
        # --cache-only も同じ結果で、通信しない
        out3 = Path(tempfile.mkdtemp()) / "o3.json"
        self.assertEqual(imain.main(["--request", str(r), "--cache-only", "--sites", "m001,m002,m013", "--now", (NOW + timedelta(minutes=6)).isoformat(),
                                     "--cache-dir", cdir, "--out", str(out3)]), 0)

if __name__ == "__main__":
    unittest.main()
