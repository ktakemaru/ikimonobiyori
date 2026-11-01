"""取得層(紅葉)の再試行と keep-alive: 通信エラーの再試行(7b)、requests.Session の共有・(connect, read) のタイムアウト(7c)、
一時的なサーバー障害(HTTP 502/503/504)だけの再試行(9b)。通信なし(偽の Session / 偽の http_get)。待ちは注入して、実際には sleep しない。
biyori-hub の tests/test_stage7b.py(Retry)、test_stage7c.py(KeepAlive)、test_stage9b.py(Config の1件・RetryBehaviour)から移した(段階12)。
計測フック(hub/measure)・台帳・adapters・ワークフローに触れる部分は biyori-hub 側に残っている。"""
import copy
import json
import socket
import ssl
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import fakes as T
import helpers as H
import requests
from helpers import ROOT
from ikimonobiyori.fetch import live
from ikimonobiyori.fetch.cache import Cache

HTTP = T.CFG["live"]["retry"]["http"]


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.content = (body if body is not None else json.dumps(T.resp())).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}


class FakeSession:
    """requests.Session の偽物。script は応答(FakeResponse)または投げる例外の列(尽きたら 200)。"""
    def __init__(self, script=()):
        self.script, self.calls, self.closed = list(script), [], 0

    def get(self, url, **kw):
        self.calls.append((url, kw))
        if self.script:
            x = self.script.pop(0)
            if isinstance(x, BaseException):
                raise x
            return x
        return FakeResponse()

    def close(self):
        self.closed += 1


def run_fetch(session, *, cfg=None, sites=("m001", "m002", "m013"), max_requests=20):
    made, slept = [], []

    def factory():
        made.append(session)
        return session
    out = live.fetch_temperatures(list(sites), T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=Cache(tempfile.mkdtemp()), cfg=cfg or T.CFG,
                                  live=True, max_requests=max_requests, unparsed_dir=tempfile.mkdtemp(), sleep=slept.append, session_factory=factory,
                                  clock=lambda: T.NOW)                    # 段階37: 取得時刻は応答を受け取った時刻。テストは時計を合わせる
    return out, made, slept


def run_fetch(session, *, cfg=None, sites=("m001", "m002", "m013"), max_requests=20):
    made, slept = [], []

    def factory():
        made.append(session)
        return session
    out = live.fetch_temperatures(list(sites), T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=Cache(tempfile.mkdtemp()), cfg=cfg or T.CFG,
                                  live=True, max_requests=max_requests, unparsed_dir=tempfile.mkdtemp(), sleep=slept.append, session_factory=factory,
                                  clock=lambda: T.NOW)                    # 段階37: 取得時刻は応答を受け取った時刻。テストは時計を合わせる
    return out, made, slept


class Flaky:
    """errors を順に投げ、尽きたら 200 を返す偽の http_get。"""
    def __init__(self, errors):
        self.errors, self.calls = list(errors), []

    def __call__(self, url):
        self.calls.append(url)
        if self.errors:
            raise self.errors.pop(0)
        return 200, json.dumps(T.resp())


def R(status, headers=None, body="{}"):
    r = FakeResponse(status, body)
    r.headers = dict(headers or {})
    return r


def fetch(script, *, sites=("m001",), max_requests=20, cfg=None):
    return run_fetch(FakeSession(script), cfg=cfg, sites=sites, max_requests=max_requests)


class Retry(unittest.TestCase):
    def cfg(self, retry="default"):
        c = copy.deepcopy(T.CFG)
        if retry is None:
            c["live"].pop("retry", None)
        elif retry != "default":
            c["live"]["retry"] = retry
        return c

    def run_fetch(self, http, *, cfg=None, max_requests=10, sites=("m001",)):
        slept = []
        cache = Cache(tempfile.mkdtemp())
        inputs, rep = live.fetch_temperatures(list(sites), T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=cache, cfg=cfg or self.cfg(),
                                              http_get=http, live=True, max_requests=max_requests, unparsed_dir=tempfile.mkdtemp(), sleep=slept.append)
        return inputs, rep, slept

    def test_config_exposes_limits(self):
        r = T.CFG["live"]["retry"]
        self.assertEqual({k: r[k] for k in ("max_retries", "wait_s")}, {"max_retries": 2, "wait_s": [2, 5]})        # 通信エラーの再試行(HTTP は 9b の http。tests/test_stage9b.py)

    def test_recovers_on_second_try_waits_2s_and_counts_both_requests(self):
        http = Flaky([urllib.error.URLError(socket.timeout("handshake timed out"))])
        inputs, rep, slept = self.run_fetch(http)
        self.assertEqual(slept, [2])
        self.assertEqual((rep["requests"], len(http.calls)), (2, 2))  # 再試行も 1 リクエスト
        self.assertIn("m001", inputs["temperatures"])
        self.assertTrue(any("再試行" in w for w in rep["warnings"]))

    def test_two_retries_then_success_waits_2_then_5(self):
        http = Flaky([TimeoutError("t"), ssl.SSLError("tls")])
        _, rep, slept = self.run_fetch(http)
        self.assertEqual(slept, [2, 5])
        self.assertEqual(rep["requests"], 3)

    def test_gives_up_after_max_retries_and_raises_last_error(self):
        http = Flaky([ConnectionResetError("a"), TimeoutError("b"), urllib.error.URLError("c")])
        with self.assertRaises(urllib.error.URLError):
            self.run_fetch(http)
        self.assertEqual(len(http.calls), 3)                          # 1 回 + 再試行 2 回。それ以上は送らない

    def test_non_200_is_not_retried(self):
        http = T.FakeHttp(status=429, body="x")
        with self.assertRaises(live.LiveError):
            self.run_fetch(http)
        self.assertEqual(len(http.calls), 1)

    def test_http_error_exception_is_not_retried(self):
        http = Flaky([urllib.error.HTTPError("u", 429, "Too Many", {}, None)])
        with self.assertRaises(urllib.error.HTTPError):
            self.run_fetch(http)
        self.assertEqual(len(http.calls), 1)

    def test_unreadable_body_is_not_retried(self):
        http = T.FakeHttp(status=200, body="not json")
        with self.assertRaises(Exception):
            self.run_fetch(http)
        self.assertEqual(len(http.calls), 1)

    def test_retry_respects_max_requests(self):
        http = Flaky([TimeoutError("a")] * 5)
        with self.assertRaises(TimeoutError):
            self.run_fetch(http, max_requests=2)
        self.assertEqual(len(http.calls), 2)                          # 上限 2 件に達したら再試行しない

    def test_no_retry_setting_means_no_retry(self):
        http = Flaky([TimeoutError("a")])
        with self.assertRaises(TimeoutError):
            self.run_fetch(http, cfg=self.cfg(None))
        self.assertEqual(len(http.calls), 1)

    def test_settings_come_from_config(self):
        http = Flaky([TimeoutError("a"), TimeoutError("b")])
        slept = []
        with self.assertRaises(TimeoutError):                         # 最大 1 回 → 2 回目の失敗で中止。待ちは設定の 1 つ目(7 秒)
            live.fetch_temperatures(["m001"], T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=Cache(tempfile.mkdtemp()),
                                    cfg=self.cfg({"max_retries": 1, "wait_s": [7, 9]}), http_get=http, live=True, max_requests=10,
                                    unparsed_dir=tempfile.mkdtemp(), sleep=slept.append)
        self.assertEqual((slept, len(http.calls)), ([7], 2))


class KeepAlive(unittest.TestCase):
    def test_all_requests_share_one_session(self):
        s = FakeSession()
        (inputs, rep), made, _ = run_fetch(s)
        self.assertEqual(made, [s])                                       # Session は 1 つだけ作る
        self.assertEqual((len(s.calls), rep["requests"], len(inputs["temperatures"])), (3, 3, 3))
        self.assertEqual(s.closed, 1)                                     # 終了時に閉じる

    def test_all_cache_hits_never_create_a_session(self):
        cache = Cache(tempfile.mkdtemp())
        s = FakeSession()
        live.fetch_temperatures(["m001"], T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=cache, cfg=T.CFG, live=True, max_requests=5,
                                unparsed_dir=tempfile.mkdtemp(), session_factory=lambda: s)
        s2 = FakeSession()
        made = []
        _, rep = live.fetch_temperatures(["m001"], T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=cache, cfg=T.CFG, live=True, max_requests=5,
                                         unparsed_dir=tempfile.mkdtemp(), session_factory=lambda: made.append(1) or s2)
        self.assertEqual((len(s.calls), rep["requests"], made, s2.closed), (1, 0, [], 0))

    def test_timeout_is_a_connect_read_tuple_from_config(self):
        s = FakeSession()
        run_fetch(s, sites=("m001",))
        kw = s.calls[0][1]
        self.assertEqual(kw["timeout"], (10, 20))
        self.assertEqual(kw["headers"], {"User-Agent": T.CFG["live"]["user_agent"]})
        cfg = copy.deepcopy(T.CFG)
        cfg["live"]["request_timeout"] = {"connect_s": 3, "read_s": 7}
        s2 = FakeSession()
        run_fetch(s2, cfg=cfg, sites=("m001",))
        self.assertEqual(s2.calls[0][1]["timeout"], (3, 7))                # コードに直書きしていない

    def test_config_marks_values_as_provisional(self):
        text = (ROOT / "ikimonobiyori" / "config.yaml").read_text(encoding="utf-8")
        self.assertEqual(T.CFG["live"]["request_timeout"], {"connect_s": 10, "read_s": 20})
        self.assertIn("5 秒に縮めない", text)
        self.assertIn("仮置き", text.split("request_timeout:")[1].splitlines()[0])

    def test_dropped_connection_is_retried_and_recovers(self):
        s = FakeSession([requests.ConnectionError("Connection aborted: RemoteDisconnected")])
        (inputs, rep), _, slept = run_fetch(s, sites=("m001", "m002"))
        self.assertEqual((slept, rep["requests"], len(s.calls), len(inputs["temperatures"])), ([2], 3, 3, 2))   # 再試行も 1 リクエスト
        self.assertEqual(len(rep["warnings"]), 1)
        self.assertIn("ConnectionError", rep["warnings"][0])
        self.assertEqual(s.closed, 1)

    def test_connect_and_read_timeouts_are_network_errors(self):
        s = FakeSession([requests.ConnectTimeout("handshake"), requests.ReadTimeout("read")])
        (_, rep), _, slept = run_fetch(s, sites=("m001",))
        self.assertEqual((slept, rep["requests"]), ([2, 5], 3))

    def test_exhausted_retries_raise_and_the_session_is_closed(self):
        s = FakeSession([requests.ConnectionError("x")] * 3)
        with self.assertRaises(requests.ConnectionError):
            run_fetch(s, sites=("m001",))
        self.assertEqual((len(s.calls), s.closed), (3, 1))                 # 最大 2 回の再試行(合計 3 回)の後に止まり、例外でも閉じる

    def test_session_is_closed_on_any_exception(self):
        s = FakeSession([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            run_fetch(s, sites=("m001",))
        self.assertEqual(s.closed, 1)

    def test_http_429_and_500_are_not_retried(self):
        for code in (429, 500, 404):                                      # 502/503/504 は 9b で再試行の対象(tests/test_stage9b.py)
            s = FakeSession([FakeResponse(code, "{}")])
            with self.assertRaises(live.LiveError, msg=code):
                run_fetch(s, sites=("m001",))
            self.assertEqual((len(s.calls), s.closed), (1, 1), code)

    def test_retry_counts_against_max_requests(self):
        s = FakeSession([requests.ConnectionError("x")] * 5)
        with self.assertRaises(requests.ConnectionError):
            run_fetch(s, sites=("m001",), max_requests=2)
        self.assertEqual(len(s.calls), 2)

    def test_injected_http_get_still_works_without_a_session(self):
        http = T.FakeHttp()
        inputs, rep = T.fetch(Cache(tempfile.mkdtemp()), http)
        self.assertEqual((len(http.calls), rep["requests"]), (3, 3))        # 従来の注入経路(自宅のテスト)は変わらない

    def test_result_shape_is_the_same_as_the_injected_path(self):
        a, ra = T.fetch(Cache(tempfile.mkdtemp()), T.FakeHttp())
        (b, rb), _, _ = run_fetch(FakeSession())
        self.assertEqual(a, b)                                              # 取得結果(inputs)は経路によらず同じ
        self.assertEqual((ra["requests"], ra["warnings"]), (rb["requests"], rb["warnings"]))


class Config(unittest.TestCase):
    def test_config_values_and_provisional_marker(self):
        self.assertEqual(HTTP, {"statuses": [502, 503, 504], "max_retries": 2, "wait_s": [10, 30], "retry_after_max_s": 60, "max_total_per_run": 6})
        text = (ROOT / "ikimonobiyori" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("すべて仮置き", text.split("    http:")[1].splitlines()[0])


class RetryBehaviour(unittest.TestCase):
    def test_503_then_200_recovers_after_10s(self):
        (inputs, rep), _, slept = fetch([R(503), FakeResponse()])
        self.assertEqual((slept, rep["requests"], rep["http_retries"], len(inputs["temperatures"])), ([10], 2, {"503": 1}, 1))
        self.assertIn("HTTP 503", rep["warnings"][0])
        self.assertEqual(rep["http_recovered"], [{"status": 503, "retries": 1, "site": "m001"}])

    def test_503_503_200_second_wait_is_30s(self):
        (_, rep), _, slept = fetch([R(503), R(503), FakeResponse()])
        self.assertEqual((slept, rep["requests"], rep["http_retries"]), ([10, 30], 3, {"503": 2}))

    def test_503_three_times_exhausts_and_aborts(self):
        s = FakeSession([R(503), R(503), R(503)])
        slept = []
        with self.assertRaises(live.LiveError) as cm:
            live.fetch_temperatures(["m001"], T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=live.Cache(tempfile.mkdtemp()), cfg=T.CFG, live=True,
                                    max_requests=20, unparsed_dir=tempfile.mkdtemp(), sleep=slept.append, session_factory=lambda: s)
        self.assertEqual((len(s.calls), slept, s.closed), (3, [10, 30], 1))
        self.assertIn("HTTP 503", str(cm.exception))
        self.assertIn("使い切った", str(cm.exception))

    def test_502_and_504_are_retried(self):
        for code in (502, 504):
            (_, rep), _, slept = fetch([R(code), FakeResponse()])
            self.assertEqual((slept, rep["http_retries"]), ([10], {str(code): 1}), code)

    def test_429_500_404_and_others_abort_at_once(self):
        for code in (429, 500, 404, 501, 400, 403):
            s = FakeSession([R(code)])
            with self.assertRaises(live.LiveError, msg=code):
                run_fetch(s, sites=("m001",))
            self.assertEqual((len(s.calls), s.closed), (1, 1), code)

    def test_retry_after_seconds_is_followed(self):
        (_, rep), _, slept = fetch([R(503, {"Retry-After": "5"}), FakeResponse()])
        self.assertEqual(slept, [5])

    def test_retry_after_is_case_insensitive_and_zero_is_allowed(self):
        _, _, slept = fetch([R(503, {"retry-after": "0"}), FakeResponse()])
        self.assertEqual(slept, [0])

    def test_retry_after_over_the_cap_aborts_without_retry(self):
        for v in ("120", "61"):
            s = FakeSession([R(503, {"Retry-After": v})])
            with self.assertRaises(live.LiveError) as cm:
                run_fetch(s, sites=("m001",))
            self.assertEqual(len(s.calls), 1, v)
            self.assertIn("Retry-After", str(cm.exception))

    def test_retry_after_at_the_cap_is_accepted(self):
        _, _, slept = fetch([R(503, {"Retry-After": "60"}), FakeResponse()])
        self.assertEqual(slept, [60])

    def test_retry_after_http_date(self):
        when = T.NOW + timedelta(seconds=20)
        _, _, slept = fetch([R(503, {"Retry-After": format_datetime(when.astimezone(timezone.utc), usegmt=True)}), FakeResponse()])
        self.assertEqual(slept, [20])
        far = T.NOW + timedelta(seconds=600)
        s = FakeSession([R(503, {"Retry-After": format_datetime(far.astimezone(timezone.utc), usegmt=True)})])
        with self.assertRaises(live.LiveError):
            run_fetch(s, sites=("m001",))
        self.assertEqual(len(s.calls), 1)

    def test_parse_retry_after(self):
        now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(live.parse_retry_after("7", now), 7)
        self.assertEqual(live.parse_retry_after("Sat, 17 Oct 2026 12:00:30 GMT", now), 30)
        self.assertEqual(live.parse_retry_after("Sat, 17 Oct 2026 11:00:00 GMT", now), 0)        # 過去は待たない
        self.assertIsNone(live.parse_retry_after("soon", now))
        self.assertIsNone(live.parse_retry_after(None, now))

    def test_run_wide_cap_of_6_retries(self):
        # 3 地点が 2 回ずつ 503(各地点は 3 回目で成功)→ 計 6 回で上限。4 地点目の最初の 503 で中止
        script = []
        for _ in range(3):
            script += [R(503), R(503), FakeResponse()]
        script += [R(503)]
        s = FakeSession(script)
        slept = []
        with self.assertRaises(live.LiveError) as cm:
            live.fetch_temperatures(["m001", "m002", "m013", "m003"], dict(T.SITES, m003=dict(T.SITES["m001"], lat=T.SITES["m001"]["lat"] + 0.5)), T.AUT, T.DATES, T.NOW.date(), T.NOW,
                                    cache=live.Cache(tempfile.mkdtemp()), cfg=T.CFG, live=True, max_requests=40, unparsed_dir=tempfile.mkdtemp(),
                                    sleep=slept.append, session_factory=lambda: s)
        self.assertEqual(len(slept), 6)
        self.assertIn("実行全体", str(cm.exception))

    def test_retries_count_against_max_requests(self):
        s = FakeSession([R(503)] * 5)
        with self.assertRaises(live.LiveError) as cm:
            run_fetch(s, sites=("m001",), max_requests=2)
        self.assertEqual(len(s.calls), 2)
        self.assertIn("max-requests", str(cm.exception))

    def test_no_http_config_means_no_http_retry(self):
        cfg = copy.deepcopy(T.CFG)
        cfg["live"]["retry"].pop("http")
        s = FakeSession([R(503)])
        with self.assertRaises(live.LiveError):
            run_fetch(s, cfg=cfg, sites=("m001",))
        self.assertEqual(len(s.calls), 1)

    def test_network_error_retry_is_unchanged(self):
        s = FakeSession([requests.ConnectionError("x"), FakeResponse()])
        (_, rep), _, slept = run_fetch(s, sites=("m001",))
        self.assertEqual((slept, rep["http_retries"]), ([2], {}))
        s = FakeSession([requests.ConnectionError("x")] * 3)
        with self.assertRaises(requests.ConnectionError):
            run_fetch(s, sites=("m001",))
        self.assertEqual(len(s.calls), 3)

    def test_network_error_then_503_then_200(self):
        (_, rep), _, slept = fetch([requests.ConnectionError("x"), R(503), FakeResponse()])
        self.assertEqual((slept, rep["requests"]), ([2, 10], 3))

    def test_injected_two_tuple_http_get_works(self):
        slept, calls = [], []

        def http_get(url):
            calls.append(url)
            return (503, "{}") if len(calls) == 1 else (200, json.dumps(T.resp()))
        _, rep = live.fetch_temperatures(["m001"], T.SITES, T.AUT, T.DATES, T.NOW.date(), T.NOW, cache=live.Cache(tempfile.mkdtemp()), cfg=T.CFG,
                                         http_get=http_get, live=True, max_requests=5, unparsed_dir=tempfile.mkdtemp(), sleep=slept.append)
        self.assertEqual((slept, rep["requests"]), ([10], 2))


if __name__ == "__main__":
    unittest.main()
