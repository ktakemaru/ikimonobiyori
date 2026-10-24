"""スポットのページの地図の埋め込みの座標だけを読む小さなコード(段階19 の続き。ikimonobiyori/fetch/spot_coords.py)。
合成の見本(構造だけをまねたもの。本物の HTML は入れない)と、偽の http_get だけ。通信なし。"""
import contextlib
import io
import json
import os
import unittest
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import sources
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import spot_coords as sc

CFG = load_config()
BOUNDS = CFG["live"]["spot_coords"]
NIKKO = "https://www.nikko-kankou.org"
HAKONE = "https://www.hakone.or.jp"
ROBOTS_OK = "User-agent: *\nAllow: /\n"


def page(*iframes, body="見本の紹介文。座標のように見える 35.1,139.1 という文字列も本文にはある。"):
    return "<html><body><p>" + body + "</p>" + "".join(iframes) + "<script>var m='q=30.0,130.0';</script></body></html>"


def embed(q, host="https://www.google.com/maps", path="/embed/v1/place", key="q", lazy=False, esc=False):
    sep = "&amp;" if esc else "&"
    attr = "data-src" if lazy else "src"
    return f'<iframe {attr}="{host}{path}?key=SAMPLE{sep}{key}={q}{sep}zoom=15"></iframe>'


class Parse(unittest.TestCase):
    def test_q_pair(self):
        r = sc.parse_page(page(embed("36.123456,139.654321")), BOUNDS)
        self.assertEqual((r["status"], r["lat"], r["lon"], r["pattern"]), ("ok", 36.123456, 139.654321, "q"))

    def test_encoded_comma_lazy_attribute_and_escaped_ampersand(self):
        for html in (page(embed("36.1%2C139.6")), page(embed("36.1,139.6", lazy=True)), page(embed("36.1,139.6", esc=True))):
            r = sc.parse_page(html, BOUNDS)
            self.assertEqual((r["status"], r["lat"], r["lon"]), ("ok", 36.1, 139.6))

    def test_other_pair_keys(self):
        for key in ("ll", "center", "query"):
            self.assertEqual(sc.parse_page(page(embed("36.1,139.6", key=key)), BOUNDS)["status"], "ok", key)

    def test_pb_pattern_is_longitude_then_latitude(self):
        pb = "!1m18!1m12!1m3!1d3000!2d139.654321!3d36.123456!2m3!1f0!2f0!3f0"
        r = sc.parse_page(page(f'<iframe src="https://www.google.com/maps/embed?pb={pb}"></iframe>'), BOUNDS)
        self.assertEqual((r["status"], r["lat"], r["lon"], r["pattern"]), ("ok", 36.123456, 139.654321, "pb"))

    def test_q_is_preferred_over_pb_inside_one_url(self):
        u = "https://www.google.com/maps/embed?q=36.1,139.6&pb=!2d140.0!3d37.0"
        r = sc.parse_page(page(f'<iframe src="{u}"></iframe>'), BOUNDS)
        self.assertEqual((r["lat"], r["lon"], r["pattern"]), (36.1, 139.6, "q"))

    def test_no_map_means_no_coordinates_and_the_body_text_is_never_used(self):
        r = sc.parse_page(page(), BOUNDS)
        self.assertEqual((r["status"], r["frames"]), ("no_coordinates", 0))
        self.assertNotIn("lat", r)

    def test_an_address_is_not_a_coordinate(self):
        self.assertEqual(sc.parse_page(page(embed("栃木県日光市湯元")), BOUNDS)["status"], "no_coordinates")

    def test_other_hosts_and_non_map_iframes_are_ignored(self):
        html = page('<iframe src="https://video.example.org/embed?q=36.1,139.6"></iframe>',
                    '<iframe src="https://www.google.com/recaptcha/api2/anchor?q=36.1,139.6"></iframe>')
        self.assertEqual(sc.parse_page(html, BOUNDS)["status"], "no_coordinates")

    def test_numbers_outside_japan_are_ignored(self):
        self.assertEqual(sc.parse_page(page(embed("51.5,-0.12")), BOUNDS)["status"], "no_coordinates")

    def test_two_different_maps_are_ambiguous_and_nothing_is_chosen(self):
        r = sc.parse_page(page(embed("36.1,139.6"), embed("36.2,139.7")), BOUNDS)
        self.assertEqual((r["status"], r["candidates"]), ("ambiguous", [(36.1, 139.6), (36.2, 139.7)]))
        self.assertNotIn("lat", r)

    def test_the_same_pair_twice_is_one_coordinate(self):
        r = sc.parse_page(page(embed("36.1,139.6"), embed("36.1,139.6", lazy=True)), BOUNDS)
        self.assertEqual((r["status"], r["frames_with_coordinates"]), ("ok", 2))

    def test_the_result_has_numbers_and_statuses_only(self):
        r = sc.parse_page(page(embed("36.1,139.6")), BOUNDS)
        self.assertLessEqual(set(r), {"frames", "frames_with_coordinates", "status", "lat", "lon", "pattern", "candidates"})
        self.assertNotIn("見本の紹介文", json.dumps(r, ensure_ascii=False))


class FakeWeb:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url):
        self.calls.append(url)
        got = self.pages.get(url, (404, ""))
        return got[0], got[1], {}


class Read(unittest.TestCase):
    def run_read(self, urls, pages, max_requests=30):
        sleeps, web = [], FakeWeb(pages)
        rep = sc.read_spots(urls, http_get=web, cfg=CFG, max_requests=max_requests, sleep=sleeps.append)
        return rep, web, sleeps

    def test_robots_first_once_per_host_and_waits_between_requests(self):
        u = [f"{NIKKO}/spot/1", f"{NIKKO}/spot/2", f"{HAKONE}/spot/3"]
        pages = {f"{NIKKO}/robots.txt": (200, ROBOTS_OK), f"{HAKONE}/robots.txt": (200, ROBOTS_OK),
                 u[0]: (200, page(embed("36.1,139.6"))), u[1]: (200, page()), u[2]: (200, page(embed("35.2,139.1")))}
        rep, web, sleeps = self.run_read(u, pages)
        self.assertEqual(web.calls, [f"{NIKKO}/robots.txt", u[0], u[1], f"{HAKONE}/robots.txt", u[2]])
        self.assertEqual(rep["requests"], 5)
        self.assertEqual([r["status"] for r in rep["results"]], ["ok", "no_coordinates", "ok"])
        self.assertEqual(sleeps, [CFG["live"]["min_interval_s"]] * 4)                    # 最初の 1 回の前は待たない。ほかは 2 秒以上
        self.assertGreaterEqual(CFG["live"]["min_interval_s"], 2)
        self.assertIsNone(rep["stopped"])

    def test_other_hosts_are_refused_before_any_request(self):
        web = FakeWeb({})
        with self.assertRaises(ValueError):
            sc.read_spots([f"{NIKKO}/spot/1", "https://www.daigo-kanko.jp/spot-0003.html"], http_get=web, cfg=CFG, max_requests=30, sleep=lambda s: None)
        self.assertEqual(web.calls, [])

    def test_the_allowed_hosts_are_exactly_the_two_approved_ones(self):
        self.assertEqual(sorted(CFG["live"]["allowed_hosts_by_subject"]["autumn_leaves_status"]), ["www.hakone.or.jp", "www.nikko-kankou.org"])

    def test_robots_disallow_means_not_read(self):
        u = f"{NIKKO}/spot/1"
        rep, web, _ = self.run_read([u], {f"{NIKKO}/robots.txt": (200, "User-agent: *\nDisallow: /spot/\n"), u: (200, page(embed("36.1,139.6")))})
        self.assertEqual((rep["results"][0]["status"], web.calls), ("not_read", [f"{NIKKO}/robots.txt"]))

    def test_robots_not_found_is_not_read_but_other_hosts_continue(self):
        u = [f"{NIKKO}/spot/1", f"{HAKONE}/spot/3"]
        rep, web, _ = self.run_read(u, {f"{HAKONE}/robots.txt": (200, ROBOTS_OK), u[1]: (200, page(embed("35.2,139.1")))})
        self.assertEqual([r["status"] for r in rep["results"]], ["not_read", "ok"])

    def test_429_stops_everything(self):
        u = [f"{NIKKO}/spot/1", f"{NIKKO}/spot/2", f"{NIKKO}/spot/3"]
        pages = {f"{NIKKO}/robots.txt": (200, ROBOTS_OK), u[0]: (200, page(embed("36.1,139.6"))), u[1]: (429, "")}
        rep, web, _ = self.run_read(u, pages)
        self.assertEqual([r["status"] for r in rep["results"]], ["ok", "http_429"])
        self.assertIn("429", rep["stopped"])
        self.assertNotIn(u[2], web.calls)

    def test_a_404_page_is_recorded_and_the_rest_continue_only_for_non_errors(self):
        u = [f"{NIKKO}/spot/1", f"{NIKKO}/spot/2"]
        rep, web, _ = self.run_read(u, {f"{NIKKO}/robots.txt": (200, ROBOTS_OK), u[1]: (200, page(embed("36.1,139.6")))})
        self.assertEqual(rep["results"][0]["status"], "http_404")
        self.assertIsNotNone(rep["stopped"])                                             # 4xx は止める(安全側)
        self.assertNotIn(u[1], web.calls)

    def test_max_requests_stops(self):
        u = [f"{NIKKO}/spot/{i}" for i in range(1, 6)]
        pages = {f"{NIKKO}/robots.txt": (200, ROBOTS_OK), **{x: (200, page()) for x in u}}
        rep, web, _ = self.run_read(u, pages, max_requests=3)
        self.assertEqual((rep["requests"], len(web.calls)), (3, 3))
        self.assertIn("--max-requests 3", rep["stopped"])

    def test_html_is_not_kept_in_the_report(self):
        u = f"{NIKKO}/spot/1"
        rep, _, _ = self.run_read([u], {f"{NIKKO}/robots.txt": (200, ROBOTS_OK), u: (200, page(embed("36.1,139.6")))})
        self.assertNotIn("見本の紹介文", json.dumps(rep, ensure_ascii=False))
        self.assertNotIn("<", json.dumps(rep, ensure_ascii=False))


class Cli(unittest.TestCase):
    def run_main(self, argv, http_get=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sources.main(argv, http_get=http_get)
        return code, out.getvalue(), err.getvalue()

    BASE = ["spot-coords", "--url", f"{NIKKO}/spot/1", "--now", "2026-10-24T20:00:00+09:00"]

    def test_refuses_under_test_without_live_and_without_max_requests(self):
        self.assertEqual(self.run_main(self.BASE)[0], 2)                                              # --live なし
        code, _, err = self.run_main(self.BASE + ["--live", "--max-requests", "3"])
        self.assertEqual(code, 2)
        self.assertIn("BIYORI_UNDER_TEST", err)                                                      # テスト中は常に拒否
        self.assertEqual(self.run_main(self.BASE + ["--live"], http_get=FakeWeb({}))[0], 2)          # --max-requests なし

    def test_a_fake_http_get_reads_and_prints_numbers_only(self):
        u = f"{NIKKO}/spot/1"
        web = FakeWeb({f"{NIKKO}/robots.txt": (200, ROBOTS_OK), u: (200, page(embed("36.1,139.6")))})
        with mock.patch.object(sc.time, "sleep", lambda s: None):
            code, out, _ = self.run_main(self.BASE + ["--live", "--max-requests", "5"], http_get=web)
        res = json.loads(out)
        self.assertEqual((code, res["requests"], res["results"][0]["lat"], res["results"][0]["lon"]), (0, 2, 36.1, 139.6))
        self.assertNotIn("見本の紹介文", out)

    def test_other_host_is_refused_with_a_message(self):
        code, _, err = self.run_main(["spot-coords", "--url", "https://www.daigo-kanko.jp/spot-0003.html", "--now", "2026-10-24T20:00:00+09:00",
                                      "--live", "--max-requests", "5"], http_get=FakeWeb({}))
        self.assertEqual(code, 2)
        self.assertIn("許可リスト外", err)


if __name__ == "__main__":
    unittest.main()
