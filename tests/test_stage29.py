"""段階29: 野鳥の案内ページの代表写真(表づくり・写真の取得・キャッシュ)。通信なし。固定のサンプル応答だけ。"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from http import HTTPStatus
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_photos
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError, inat_photos

P = guide.load_policy()
PH = P["photos"]
TODAY = date(2026, 10, 31)
NOSLEEP = lambda s: None  # noqa: E731

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
WEBP = b"RIFF1234WEBPVP8 " + b"0" * 20
IMG_URL = "https://inaturalist-open-data.s3.amazonaws.com/photos/111/medium.jpg"


def cand(tid=1, name="Alcedo atthis", rank="species", common="カワセミ", cls="Aves"):
    return {"id": tid, "name": name, "rank": rank, "preferred_common_name": common, "iconic_taxon_name": cls}


def search_doc(*cands):
    return json.dumps({"total_results": len(cands), "results": list(cands)})


def taxon_doc(tid=1, name="Alcedo atthis", lic="cc-by", attribution="(c) 撮影者, some rights reserved (CC BY)", url=IMG_URL, photo_id=111, photo=True):
    p = {"id": photo_id, "license_code": lic, "attribution": attribution, "medium_url": url, "square_url": url.replace("medium", "square")} if photo else None
    return json.dumps({"results": [{"id": tid, "name": name, "default_photo": p}]})


def getter(responses):
    """URL に含まれる語 → (status, 本文)。呼ばれた URL を calls に残す。"""
    calls = []

    def get(url, *_a):
        calls.append(url)
        for key, val in responses.items():
            if key in url:
                return (val[0], val[1], {}) if len(val) == 2 else val
        raise AssertionError(f"想定外の URL: {url}")
    get.calls = calls
    return get


class Decide(unittest.TestCase):
    def d(self, name, *cands):
        return inat_photos.decide(name, inat_photos.parse_search(json.loads(search_doc(*cands))), PH)

    def test_exact_species_bird_enters(self):
        row, why = self.d("カワセミ", cand(), cand(2, "Halcyon smyrnensis", common="アカショウビン"))
        self.assertEqual((row, why), ({"name": "カワセミ", "scientific": "Alcedo atthis", "taxon_id": 1}, None))

    def test_not_entered_when_any_condition_fails(self):
        cases = {
            "候補が 0 件": ("カワセミ", []),
            "完全に一致する候補がない": ("カワセミ", [cand(common="ヤマセミ"), cand(2, common="カワセミ科")]),
            "ちょうど 1 件でない": ("カワセミ", [cand(), cand(2, "Other", common="カワセミ")]),
            "ランクが species でない": ("カワセミ", [cand(rank="genus")]),
            "鳥類": ("カワセミ", [cand(cls="Plantae")]),
        }
        for why, (name, cs) in cases.items():
            row, got = self.d(name, *cs)
            self.assertIsNone(row, why)
            self.assertIn(why, got)

    def test_no_fuzzy_match(self):
        row, _ = self.d("カワセミ", cand(common="カワセミ類"), cand(2, common="ヤマカワセミ"))
        self.assertIsNone(row)

    def test_generic_words_are_skipped(self):
        for n in ("カモ類", "ハクチョウ類", "シギ・チドリ", "スズガモ・カンムリカイツブリ"):
            self.assertIsNotNone(inat_photos.skipped(n, PH), n)
        self.assertIsNone(inat_photos.skipped("カワセミ", PH))

    def test_parse_rejects_unexpected_shapes(self):
        for bad in ("{}", '{"results": "x"}', '{"results": [1]}', '{"results": [{"name": "a"}]}'):
            with self.assertRaises(ParseError):
                inat_photos.parse_search(json.loads(bad))


class BuildTable(unittest.TestCase):
    def run_build(self, names, responses, max_requests=80):
        g = getter(responses)
        out = inat_photos.build_table(names, http_get=g, ph=PH, max_requests=max_requests, today=TODAY, sleep=NOSLEEP)
        return out, g

    def test_enters_only_exact_matches_and_skips_generic_words_without_asking(self):
        (entered, rejected, rep), g = self.run_build(["カワセミ", "カモ類", "ヤマセミ"], {
            "q=%E3%82%AB%E3%83%AF%E3%82%BB%E3%83%9F": (200, search_doc(cand())),
            "q=%E3%83%A4%E3%83%9E%E3%82%BB%E3%83%9F": (200, search_doc())})
        self.assertEqual(entered, [{"name": "カワセミ", "scientific": "Alcedo atthis", "taxon_id": 1, "checked_on": "2026-10-31"}])
        self.assertIn("カモ類", rejected)
        self.assertIn("ヤマセミ", rejected)
        self.assertEqual((rep["requests"], len(g.calls)), (2, 2))                # カモ類は問い合わせない

    def test_max_requests_stops_and_reports_the_rest(self):
        (entered, rejected, rep), g = self.run_build(["カワセミ", "ヤマセミ", "ヒヨドリ"], {"q=": (200, search_doc())}, max_requests=2)
        self.assertEqual((rep["requests"], rep["not_started"]), (2, ["ヒヨドリ"]))

    def test_429_stops_at_once(self):
        (entered, rejected, rep), g = self.run_build(["カワセミ", "ヤマセミ"], {"q=": (429, "")})
        self.assertEqual((rep["requests"], rep["status"], rep["not_started"]), (1, "HTTP 429", ["ヤマセミ"]))

    def test_unexpected_shape_stops(self):
        (entered, rejected, rep), g = self.run_build(["カワセミ", "ヤマセミ"], {"q=": (200, '{"x": 1}')})
        self.assertEqual((rep["status"], rep["requests"]), ("parse_error", 1))

    def test_requests_are_spaced_by_the_policy_interval(self):
        waits = []
        inat_photos.build_table(["カワセミ", "ヤマセミ", "ヒヨドリ"], http_get=getter({"q=": (200, search_doc())}), ph=PH, max_requests=80,
                                today=TODAY, sleep=waits.append)
        self.assertEqual(waits, [PH["min_interval_s"]["value"]] * 2)

    def test_only_the_api_host_is_asked(self):
        _, g = self.run_build(["カワセミ"], {"q=": (200, search_doc(cand()))})
        self.assertTrue(all(u.startswith("https://api.inaturalist.org/v1/taxa?") for u in g.calls))
        self.assertIn("locale=ja", g.calls[0])


ROW = {"name": "カワセミ", "scientific": "Alcedo atthis", "taxon_id": 1, "checked_on": "2026-10-31"}


class UsablePhoto(unittest.TestCase):
    def u(self, row=ROW, **kw):
        return inat_photos.usable_photo(row, inat_photos.parse_taxon(json.loads(taxon_doc(**kw))), PH)

    def test_allowed_licenses_are_used(self):
        for lic, label in (("cc0", "CC0"), ("cc-by", "CC BY"), ("cc-by-sa", "CC BY-SA"), ("CC-BY", "CC BY")):
            ok, why = self.u(lic=lic)
            self.assertEqual((ok["license"], why), (label, None), lic)

    def test_other_or_unknown_licenses_are_not(self):
        for lic in ("cc-by-nc", "cc-by-nd", "cc-by-nc-sa", None, "", "all-rights-reserved"):
            ok, why = self.u(lic=lic)
            self.assertIsNone(ok, lic)
            self.assertIn("ライセンス", why)

    def test_hosts(self):
        for host in ("static.inaturalist.org", "inaturalist-open-data.s3.amazonaws.com"):
            ok, _ = self.u(url=f"https://{host}/photos/1/medium.jpg")
            self.assertIsNotNone(ok, host)
        for url in ("https://evil.example.com/photos/1/medium.jpg", "http://static.inaturalist.org/photos/1/medium.jpg",
                    "https://static.inaturalist.org.evil.example.com/p.jpg", "https://api.inaturalist.org/p.jpg"):
            ok, why = self.u(url=url)
            self.assertIsNone(ok, url)

    def test_scientific_name_and_id_must_match_the_table(self):
        self.assertIn("学名", self.u(name="Other species")[1])
        self.assertIn("id", self.u(tid=2)[1])

    def test_missing_photo_or_attribution(self):
        self.assertIn("既定の写真がない", self.u(photo=False)[1])
        self.assertIn("撮影者", self.u(attribution="")[1])


class Images(unittest.TestCase):
    def test_types(self):
        for data, kind in ((JPEG, "jpeg"), (PNG, "png"), (WEBP, "webp")):
            self.assertEqual(inat_photos.check_image(data, PH), (kind, None))
        for data in (b"GIF89a" + b"0" * 20, b"<html>no</html>", b"", b"RIFF1234WAVEfmt "):
            self.assertIsNone(inat_photos.check_image(data, PH)[0])

    def test_too_large_is_dropped(self):
        big = JPEG + b"0" * PH["max_image_bytes"]["value"]
        self.assertEqual(inat_photos.check_image(big, PH), (None, "大きすぎる"))
        just = JPEG + b"0" * (PH["max_image_bytes"]["value"] - len(JPEG))
        self.assertEqual(inat_photos.check_image(just, PH)[0], "jpeg")


class FetchPhotos(unittest.TestCase):
    def run_fetch(self, rows, info, image, max_requests=80, cached=()):
        gi, gb = getter(info), []

        def http_bytes(url, max_bytes):
            gb.append((url, max_bytes))
            return image

        out = inat_photos.fetch_photos(rows, http_get=gi, http_bytes=http_bytes, ph=PH, max_requests=max_requests,
                                       has_cache=lambda t: t in cached, today=TODAY, sleep=NOSLEEP)
        return out, gi, gb

    def test_saves_image_with_attribution_license_page_and_date(self):
        (got, unused, rep), gi, gb = self.run_fetch([ROW], {"/taxa/1": (200, taxon_doc())}, (200, JPEG, {}))
        self.assertEqual((len(got), unused, rep["requests"]), (1, {}, 2))
        meta = got[0]["meta"]
        self.assertEqual((meta["license"], meta["attribution"], meta["photo_page"], meta["fetched_on"], meta["image_type"]),
                         ("CC BY", "(c) 撮影者, some rights reserved (CC BY)", "https://www.inaturalist.org/photos/111", "2026-10-31", "jpeg"))
        self.assertEqual(gb, [(IMG_URL, PH["max_image_bytes"]["value"])])

    def test_license_not_allowed_never_asks_for_the_image(self):
        (got, unused, rep), gi, gb = self.run_fetch([ROW], {"/taxa/1": (200, taxon_doc(lic="cc-by-nc"))}, (200, JPEG, {}))
        self.assertEqual((got, gb, rep["requests"]), ([], [], 1))
        self.assertIn("カワセミ", unused)

    def test_wrong_host_and_scientific_mismatch_are_not_used(self):
        for doc in (taxon_doc(url="https://evil.example.com/medium.jpg"), taxon_doc(name="Another bird")):
            (got, unused, rep), gi, gb = self.run_fetch([ROW], {"/taxa/1": (200, doc)}, (200, JPEG, {}))
            self.assertEqual((got, gb), ([], []))

    def test_bad_format_and_too_large_are_dropped(self):
        for image in ((200, b"GIF89a....", {}), (200, JPEG + b"0" * PH["max_image_bytes"]["value"], {})):
            (got, unused, rep), gi, gb = self.run_fetch([ROW], {"/taxa/1": (200, taxon_doc())}, image)
            self.assertEqual(got, [])
            self.assertIn("捨てた", unused["カワセミ"])

    def test_redirect_or_404_image_is_not_used_and_429_stops(self):
        (got, unused, rep), *_ = self.run_fetch([ROW], {"/taxa/1": (200, taxon_doc())}, (302, b"", {}))
        self.assertEqual(got, [])
        self.assertIn("HTTP 302", unused["カワセミ"])
        (got, unused, rep), *_ = self.run_fetch([ROW, {**ROW, "name": "ヤマセミ", "taxon_id": 2}], {"/taxa/1": (200, taxon_doc())}, (429, b"", {}))
        self.assertEqual((rep["status"], rep["not_started"]), ("HTTP 429", ["ヤマセミ"]))

    def test_cached_species_are_not_fetched_again(self):
        (got, unused, rep), gi, gb = self.run_fetch([ROW], {}, (200, JPEG, {}), cached={1})
        self.assertEqual((got, rep["requests"], rep["skipped_cached"]), ([], 0, [ROW]))
        self.assertEqual(gi.calls, [])

    def test_max_requests_counts_both_requests_of_a_species(self):
        rows = [ROW, {**ROW, "name": "ヤマセミ", "scientific": "Megaceryle lugubris", "taxon_id": 2}]
        (got, unused, rep), *_ = self.run_fetch(rows, {"/taxa/1": (200, taxon_doc())}, (200, JPEG, {}), max_requests=2)
        self.assertEqual((len(got), rep["requests"], rep["not_started"]), (1, 2, ["ヤマセミ"]))

    def test_info_request_goes_only_to_the_api_host(self):
        _, gi, _ = self.run_fetch([ROW], {"/taxa/1": (200, taxon_doc())}, (200, JPEG, {}))
        self.assertEqual(gi.calls, ["https://api.inaturalist.org/v1/taxa/1?locale=ja"])


class CacheAndCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def item(self):
        return {"meta": {"name": "カワセミ", "taxon_id": 1, "image_type": "jpeg", "license": "CC BY", "attribution": "x"}, "data": JPEG, "ext": "jpeg"}

    def test_save_load_clear_touch_only_the_cache_dir(self):
        other = Path(self.tmp.name) / "guide" / "keep.txt"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("x", encoding="utf-8")
        self.assertFalse(guide_photos.has_cache(1))
        guide_photos.save_photo(self.item())
        self.assertTrue(guide_photos.has_cache(1))
        meta, data = guide_photos.load_photo(1)
        self.assertEqual((meta["license"], data), ("CC BY", JPEG))
        self.assertTrue(str(guide_photos.cache_dir()).startswith(self.tmp.name))
        self.assertEqual(guide_photos.clear_cache(), 2)
        self.assertFalse(guide_photos.has_cache(1))
        self.assertTrue(other.is_file())                                         # キャッシュ以外は消さない
        self.assertEqual(guide_photos.clear_cache(), 0)

    def run_main(self, argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = guide.main(argv, **kw)
        return rc, out.getvalue(), err.getvalue()

    def test_live_is_required_and_refused_under_test(self):
        for cmd in ("photos-build-table", "photos-fetch"):
            rc, _, err = self.run_main([cmd])
            self.assertEqual(rc, 2)
            self.assertIn("--live", err)
            rc, _, err = self.run_main([cmd, "--live", "--max-requests", "5"])
            self.assertEqual(rc, 2)
            self.assertIn("テスト中", err)                                       # BIYORI_UNDER_TEST=1 は --live を常に拒否

    def test_max_requests_is_explicit(self):
        rc, _, err = self.run_main(["photos-fetch", "--live"], http_get=getter({}), http_bytes=lambda u, m: (200, JPEG, {}))
        self.assertEqual(rc, 2)
        self.assertIn("--max-requests", err)

    def test_run_limit_comes_from_the_policy(self):
        err, left = guide_photos._gate(mock.Mock(live=True, max_requests=500), lambda u: None, "x")
        self.assertEqual((err, left), (None, PH["max_requests_per_run"]["value"]))

    def test_clear_command(self):
        guide_photos.save_photo(self.item())
        rc, out, _ = self.run_main(["photos-clear"])
        self.assertEqual((rc, json.loads(out)["removed"]), (0, 2))

    def test_build_and_fetch_commands_with_fakes_write_only_under_the_data_dir(self):
        # 表づくり: 実データの答えに出る種名のうち、和名が完全一致するものだけ入る(ここでは常に 1 件の完全一致を返す偽の応答)
        def info(url, *_):
            name = guide_photos.guide.urlsplit(url).query.split("q=")[1].split("&")[0] if "q=" in url else None
            from urllib.parse import unquote
            return 200, search_doc(cand(100, "Aves exampleus", common=unquote(name))), {}

        with mock.patch.object(guide_photos, "table_path", return_value=Path(self.tmp.name) / "none.yaml"):
            rc, out, _ = self.run_main(["photos-build-table", "--live", "--max-requests", "3"], http_get=info)
        self.assertEqual(rc, 0)
        rep = json.loads(out)
        self.assertEqual(rep["report"]["requests"], 3)
        self.assertTrue(rep["export"].startswith(self.tmp.name))                # 書き込み先は IKIMONOBIYORI_DATA_DIR の下
        self.assertTrue(rep["report"]["not_started"])                            # 3 件で止まり、残りは未着手


class ConfigAndPolicy(unittest.TestCase):
    def test_hosts_are_exactly_the_approved_three(self):
        hosts = load_config()["live"]["allowed_hosts_by_subject"]["guide_photos"]
        self.assertEqual(sorted(hosts), sorted(["api.inaturalist.org", "static.inaturalist.org", "inaturalist-open-data.s3.amazonaws.com"]))
        self.assertEqual(sorted(PH["image_hosts"]), sorted(h for h in hosts if h != "api.inaturalist.org"))
        for subject, hs in load_config()["live"]["allowed_hosts_by_subject"].items():
            if subject != "guide_photos":
                self.assertFalse({"static.inaturalist.org", "inaturalist-open-data.s3.amazonaws.com"} & set(hs), subject)   # 広げない

    def test_policy_values(self):
        self.assertEqual((PH["max_requests_per_run"]["value"], PH["min_interval_s"]["value"], PH["max_image_bytes"]["value"]), (80, 1, 2000000))
        self.assertEqual(sorted(PH["licenses"]), ["cc-by", "cc-by-sa", "cc0"])
        for k in ("max_requests_per_run", "min_interval_s", "max_image_bytes"):
            self.assertFalse(PH[k]["provisional"])

    def test_committed_table_has_facts_only(self):
        p = guide_photos.table_path()
        if not p.is_file():
            self.skipTest("表はまだない")
        text = p.read_text(encoding="utf-8")
        for bad in ("http", "data:", "attribution", "license", "photo", "jpg", "base64"):
            self.assertNotIn(bad, text)
        for r in guide_photos.load_table(include_runtime=False).values():
            self.assertEqual(sorted(r), ["checked_on", "name", "scientific", "taxon_id"])


if __name__ == "__main__":
    unittest.main()
