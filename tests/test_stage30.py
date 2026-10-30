"""段階30: Wikimedia Commons からの代表写真(iNaturalist に許可ライセンスの写真がない種だけ)・ユーザー指定の学名・写真の選び直し・ページの出どころ表示。通信なし。固定の応答だけ。"""
import json
import os
import tempfile
import unittest

import yaml
from datetime import date
from unittest import mock
from urllib.parse import urlsplit

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_page, guide_photos
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError, commons_photos as C, inat_photos

import test_stage29 as T29
import test_stage29_page as TP

P = guide.load_policy()
PH = P["photos"]
CM = PH["commons"]
TODAY = date(2026, 10, 31)
SCI = "Turdus pallidus"
ROW = {"name": "シロハラ", "scientific": SCI, "taxon_id": 77, "checked_on": "2026-10-31"}
THUMB = "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Turdus_pallidus.JPG/500px-Turdus_pallidus.JPG?utm_source=commons.wikimedia.org"
PAGE = "https://commons.wikimedia.org/wiki/File:Turdus_pallidus.JPG"


def info(lic="CC BY-SA 3.0", artist='<a href="//commons.wikimedia.org/wiki/User:A" title="x">Alpsdake</a>', restrictions="", mime="image/jpeg", thumb=THUMB, page=PAGE):
    em = {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}, "Restrictions": {"value": restrictions}}
    return json.dumps({"query": {"pages": [{"title": "File:x.jpg", "imageinfo": [{"descriptionurl": page, "thumburl": thumb, "mime": mime, "extmetadata": em}]}]}})


def search_doc(*qids):
    return json.dumps({"query": {"searchinfo": {"totalhits": len(qids)}, "search": [{"ns": 0, "title": q} for q in qids]}})


def claim(value, rank="normal"):
    return {"rank": rank, "mainsnak": {"snaktype": "value", "datavalue": {"value": value, "type": "string"}}}


def ents_doc(**by_qid):
    """by_qid: Q1=(学名の一覧, [(ファイル名, ランク)])"""
    out = {}
    for q, (names, files) in by_qid.items():
        claims = {"P225": [claim(n) for n in names]}
        if files:
            claims["P18"] = [claim(f, r) for f, r in files]
        out[q] = {"id": q, "claims": claims}
    return json.dumps({"entities": out})


def parsed(lic="CC BY-SA 3.0", **kw):
    return C.parse_imageinfo(json.loads(info(lic=lic, **kw)))


class Usable(unittest.TestCase):
    def test_allowed_licences(self):
        for lic in ("CC0", "CC0 1.0", "Public domain", "CC BY 2.0", "CC BY-SA 4.0", "CC BY-SA 3.0 de", "CC BY 4.0"):
            ok, why = C.usable(parsed(lic), CM)
            self.assertEqual((ok["license"], why), (lic, None), lic)

    def test_nc_nd_and_unknown_are_never_used(self):
        for lic in ("CC BY-NC 2.0", "CC BY-NC-SA 4.0", "CC BY-ND 2.0", "CC BY-NC-ND 3.0", "GFDL", "", "Attribution", "CC BY-SA", "Copyrighted free use"):
            ok, why = C.usable(parsed(lic), CM)
            self.assertIsNone(ok, lic)
            self.assertIn("ライセンス", why)

    def test_restrictions_note_blocks(self):
        self.assertIn("制限", C.usable(parsed(restrictions="trademarked"), CM)[1])

    def test_author_html_is_reduced_to_text(self):
        ok, _ = C.usable(parsed(artist='<span>Foo <b>Bar</b></span><script>x()</script>'), CM)
        self.assertNotIn("<", ok["author"])
        self.assertTrue(ok["author"].startswith("Foo Bar"))

    def test_author_is_needed_for_cc_by_but_not_for_cc0(self):
        self.assertIn("作者", C.usable(parsed("CC BY 4.0", artist=""), CM)[1])
        self.assertIn("作者", C.usable(parsed("CC BY-SA 4.0", artist=" "), CM)[1])
        ok, _ = C.usable(parsed("CC0", artist=""), CM)
        self.assertEqual(ok["author"], CM["author_unknown"])

    def test_mime_must_be_a_photo_format(self):
        for m in ("image/svg+xml", "image/gif", "image/tiff", None):
            self.assertIsNone(C.usable(parsed(mime=m), CM)[0], m)

    def test_thumbnail_host_is_moved_to_the_approved_host_with_the_same_path(self):
        ok, _ = C.usable(parsed(), CM)
        u = urlsplit(ok["image_url"])
        self.assertEqual((u.scheme, u.hostname, u.query), ("https", "upload.wikimedia.org", ""))
        self.assertEqual(u.path, "/wikipedia/commons/thumb/d/d7/Turdus_pallidus.JPG/500px-Turdus_pallidus.JPG")

    def test_other_hosts_or_paths_are_not_used(self):
        for thumb in ("https://evil.example.com/wikipedia/commons/thumb/a.jpg", "http://upload.wikimedia.org/wikipedia/commons/thumb/a.jpg",
                      "https://thumb.wikimedia.org/other/path/a.jpg", "https://upload.wikimedia.org.evil.example.com/a.jpg", "", None):
            self.assertIsNone(C.usable(parsed(thumb=thumb), CM)[0], thumb)

    def test_upload_host_url_is_kept(self):
        t = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/F.jpg/500px-F.jpg"
        self.assertEqual(C.usable(parsed(thumb=t), CM)[0]["image_url"], t)

    def test_file_page_must_be_on_commons(self):
        for page in ("https://evil.example.com/wiki/File:x.jpg", "http://commons.wikimedia.org/wiki/File:x.jpg", None):
            self.assertIsNone(C.usable(parsed(page=page), CM)[0], page)

    def test_missing_page_or_imageinfo(self):
        self.assertIn("画像の情報がない", C.usable(C.parse_imageinfo({"query": {"pages": [{"title": "File:x", "missing": True}]}}), CM)[1])
        for bad in ({}, {"query": {}}, {"query": {"pages": []}}, {"query": {"pages": [{"imageinfo": "x"}]}}):
            with self.assertRaises(ParseError):
                C.parse_imageinfo(bad)


class Parsing(unittest.TestCase):
    def test_search_and_entity(self):
        self.assertEqual(C.parse_search(json.loads(search_doc("Q1", "Q22")), CM), ["Q1", "Q22"])
        with self.assertRaises(ParseError):
            C.parse_search({"query": {"search": [{"title": "Property:P1"}]}}, CM)
        doc = json.loads(ents_doc(Q1=([SCI], [("A.jpg", "normal"), ("B.jpg", "preferred")])))
        self.assertEqual(C.parse_entity(doc, "Q1", CM), {"p225": [SCI], "p18": ["B.jpg", "A.jpg"]})

    def test_deprecated_and_non_value_claims_are_ignored(self):
        doc = {"entities": {"Q1": {"claims": {"P225": [claim(SCI)], "P18": [claim("Old.jpg", "deprecated"), {"rank": "normal", "mainsnak": {"snaktype": "novalue"}}]}}}}
        self.assertEqual(C.parse_entity(doc, "Q1", CM)["p18"], [])

    def test_unexpected_shapes_stop(self):
        with self.assertRaises(ParseError):
            C.parse_entity({"entities": {}}, "Q1", CM)
        with self.assertRaises(ParseError):
            C.parse_entity({"entities": {"Q1": {"claims": {"P225": [claim(1)]}}}}, "Q1", CM)

    def test_urls_use_policy_and_the_approved_hosts(self):
        u = C.search_url(SCI, CM)
        self.assertTrue(u.startswith("https://www.wikidata.org/w/api.php?"))
        self.assertIn("haswbstatement", u)
        self.assertEqual(urlsplit(C.entity_url(["Q1", "Q2"], CM)).hostname, "www.wikidata.org")
        self.assertIn("Q1%7CQ2", C.entity_url(["Q1", "Q2"], CM))
        i = C.imageinfo_url("A b.jpg", CM)
        self.assertEqual(urlsplit(i).hostname, "commons.wikimedia.org")
        self.assertIn("iiurlwidth=500", i)


def getter_calls(responses):
    """(URL に含まれる語 → 応答) の順に探す。呼ばれた URL を calls に残す。"""
    return T29.getter(responses)


class FetchCommons(unittest.TestCase):
    def run_fetch(self, rows, responses, image=T29.JPEG, max_requests=60, cached=(), skip=frozenset(), image_status=200):
        gi, bytes_calls, saved = getter_calls(responses), [], []

        def http_bytes(url, max_bytes):
            bytes_calls.append(url)
            return image_status, image, {}
        waits = []
        out = C.fetch_commons(rows, http_get=gi, http_bytes=http_bytes, ph=PH, max_requests=max_requests, has_cache=lambda t: t in cached,
                              today=TODAY, sleep=waits.append, skip=skip, on_got=saved.append)
        return out, gi, bytes_calls, waits, saved

    def ok_responses(self):
        return {"list=search": (200, search_doc("Q1")), "wbgetentities": (200, ents_doc(Q1=([SCI], [("Turdus pallidus.JPG", "normal")]))),
                "action=query&titles": (200, info())}

    def test_one_species_takes_four_requests_and_saves_with_credit(self):
        (got, unused, rep), gi, bc, waits, saved = self.run_fetch([ROW], self.ok_responses())
        self.assertEqual((rep["requests"], rep["status"], unused), (4, "ok", {}))
        m = got[0]["meta"]
        self.assertEqual((m["source"], m["license"], m["attribution"], m["photo_page"], m["image_type"]), ("wikimedia_commons", "CC BY-SA 3.0", "Alpsdake", PAGE, "jpeg"))
        self.assertEqual(saved, got)
        self.assertEqual(urlsplit(bc[0]).hostname, "upload.wikimedia.org")
        hosts = {urlsplit(u).hostname for u in gi.calls}
        self.assertEqual(hosts, {"www.wikidata.org", "commons.wikimedia.org"})

    def test_requests_are_spaced_at_least_one_second(self):
        _, _, _, waits, _ = self.run_fetch([ROW], self.ok_responses())
        self.assertEqual(len(waits), 3)
        self.assertTrue(all(w >= 1 for w in waits))
        self.assertGreaterEqual(CM["min_interval_s"]["value"], 1)

    def test_taxon_must_match_the_scientific_name_exactly_and_be_exactly_one(self):
        r = self.ok_responses()
        r["wbgetentities"] = (200, ents_doc(Q1=(["Turdus pallidus subsp"], [("a.jpg", "normal")])))
        (got, unused, rep), *_ = self.run_fetch([ROW], r)
        self.assertEqual((got, rep["requests"]), ([], 2))
        self.assertIn("ちょうど 1 件でない(0 件)", unused["シロハラ"])
        r = self.ok_responses()
        r["list=search"] = (200, search_doc("Q1", "Q2"))
        r["wbgetentities"] = (200, ents_doc(Q1=([SCI], [("a.jpg", "normal")]), Q2=([SCI], [("b.jpg", "normal")])))
        (got, unused, rep), *_ = self.run_fetch([ROW], r)
        self.assertEqual(got, [])
        self.assertIn("(2 件)", unused["シロハラ"])

    def test_no_search_hit_or_no_image_means_no_photo(self):
        r = self.ok_responses()
        r["list=search"] = (200, search_doc())
        (got, unused, rep), *_ = self.run_fetch([ROW], r)
        self.assertEqual((got, rep["requests"]), ([], 1))
        r = self.ok_responses()
        r["wbgetentities"] = (200, ents_doc(Q1=([SCI], [])))
        (got, unused, rep), *_ = self.run_fetch([ROW], r)
        self.assertIn("P18", unused["シロハラ"])
        self.assertEqual(rep["requests"], 2)

    def test_bad_licence_means_no_photo_and_no_image_request(self):
        r = self.ok_responses()
        r["action=query&titles"] = (200, info("CC BY-NC 4.0"))
        (got, unused, rep), gi, bc, *_ = self.run_fetch([ROW], r)
        self.assertEqual((got, bc), ([], []))
        self.assertIn("ライセンス", unused["シロハラ"])

    def test_oversize_or_wrong_type_image_is_dropped(self):
        for image in (b"GIF89a" + b"0" * 30, T29.JPEG + b"0" * PH["max_image_bytes"]["value"]):
            (got, unused, rep), *_ = self.run_fetch([ROW], self.ok_responses(), image=image)
            self.assertEqual(got, [])
            self.assertIn("写真を捨てた", unused["シロハラ"])

    def test_429_stops_at_once_and_reports_the_rest(self):
        rows = [ROW, {**ROW, "name": "ヨシガモ", "scientific": "Mareca falcata", "taxon_id": 78}]
        (got, unused, rep), gi, *_ = self.run_fetch(rows, {"list=search": (429, "")})
        self.assertEqual((rep["status"], rep["requests"], rep["not_started"]), ("HTTP 429", 1, ["ヨシガモ"]))

    def test_max_requests_stops_before_the_next_request(self):
        (got, unused, rep), gi, *_ = self.run_fetch([ROW], self.ok_responses(), max_requests=3)
        self.assertEqual((rep["requests"], got, rep["status"]), (3, [], "ok"))
        self.assertEqual(rep["not_started"], ["シロハラ"])

    def test_cached_and_reviewed_species_are_not_asked(self):
        (got, unused, rep), gi, *_ = self.run_fetch([ROW], self.ok_responses(), cached={77})
        self.assertEqual((gi.calls, [r["name"] for r in rep["skipped_cached"]]), ([], ["シロハラ"]))
        (got, unused, rep), gi, *_ = self.run_fetch([ROW], self.ok_responses(), skip={77})
        self.assertEqual(gi.calls, [])

    def test_network_error_keeps_what_was_saved(self):
        calls = []

        def hg(url, *a):
            calls.append(url)
            raise OSError("boom")
        got, unused, rep = C.fetch_commons([ROW], http_get=hg, http_bytes=None, ph=PH, max_requests=60, has_cache=lambda t: False, today=TODAY, sleep=lambda s: None)
        self.assertEqual((rep["status"], len(calls)), ("network_error", 1))


class NamedSpecies(unittest.TestCase):
    def cands(self, *specs):
        return inat_photos.parse_search({"results": [{"id": i, "name": n, "rank": r, "preferred_common_name": "x", "iconic_taxon_name": c} for i, n, r, c in specs]})

    def test_exact_species_bird_enters_with_source(self):
        row, why = inat_photos.decide_named("シロハラ", SCI, self.cands((5, SCI, "species", "Aves"), (6, "Turdus", "genus", "Aves")), PH)
        self.assertEqual((row, why), ({"name": "シロハラ", "scientific": SCI, "taxon_id": 5, "source": "ユーザー指定の学名"}, None))

    def test_not_entered_unless_name_rank_and_class_all_match(self):
        for specs in ([], [(5, "Turdus pallidus x", "species", "Aves")], [(5, SCI, "genus", "Aves")], [(5, SCI, "species", "Plantae")],
                      [(5, SCI, "species", "Aves"), (6, SCI, "species", "Aves")]):
            row, why = inat_photos.decide_named("シロハラ", SCI, self.cands(*specs), PH)
            self.assertIsNone(row, specs)

    def test_build_table_with_named_searches_by_scientific_name(self):
        g = T29.getter({"q=Turdus": (200, json.dumps({"results": [{"id": 5, "name": SCI, "rank": "species", "preferred_common_name": "シロハラ", "iconic_taxon_name": "Aves"}]}))})
        entered, rejected, rep = inat_photos.build_table(["シロハラ"], http_get=g, ph=PH, max_requests=80, today=TODAY, sleep=lambda s: None, named={"シロハラ": SCI})
        self.assertEqual(entered, [{"name": "シロハラ", "scientific": SCI, "taxon_id": 5, "source": "ユーザー指定の学名", "checked_on": "2026-10-31"}])
        self.assertIn("Turdus+pallidus", g.calls[0])

    def test_policy_has_the_two_user_named_species_and_the_committed_table_says_so(self):
        self.assertEqual(PH["named_scientific"], {"シロハラ": "Turdus pallidus", "ヨシガモ": "Mareca falcata"})
        rows = guide_photos.load_table(include_runtime=False)
        srcs = guide_photos.load_sources(include_runtime=False)
        for n in PH["named_scientific"]:
            self.assertEqual(rows[n]["scientific"], PH["named_scientific"][n])
            self.assertEqual(srcs[n], PH["named_source"])
        self.assertEqual(set(srcs), set(PH["named_scientific"]))             # 出どころの欄にあるのは指定の 2 種だけ

    def test_table_text_keeps_source_and_nothing_else_extra(self):
        t = guide_photos.table_text({"シロハラ": {**ROW, "source": "ユーザー指定の学名", "candidates": [1], "image": "x"}})
        self.assertIn("sources:", t)
        self.assertIn("シロハラ: ユーザー指定の学名", t)
        self.assertEqual(set(yaml.safe_load(t)["taxa"][0]), {"name", "scientific", "taxon_id", "checked_on"})   # 行は事実の 4 項目のまま
        self.assertNotIn("candidates", t)
        self.assertNotIn("image", t)


class Reselect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def meta(self, **kw):
        return {"meta": {"name": "ダイサギ", "taxon_id": 9, "photo_id": 555, "image_type": "jpeg", "license": "CC BY", "attribution": "x", **kw}, "data": T29.JPEG, "ext": "jpeg"}

    def test_exclude_inat_photo_keeps_the_species_and_remembers_the_photo(self):
        guide_photos.save_photo(self.meta())
        self.assertEqual(guide_photos.exclude_inat_photo(9), 555)
        self.assertFalse(guide_photos.has_cache(9))
        self.assertEqual(guide_photos.load_skip_photos(), {9: {555}})
        self.assertEqual(guide_photos.load_review(), {})

    def test_exclude_inat_photo_refuses_a_commons_photo(self):
        guide_photos.save_photo(self.meta(source="wikimedia_commons", photo_id=None))
        with self.assertRaises(ValueError):
            guide_photos.exclude_inat_photo(9)

    def test_skipped_photo_is_passed_over_for_the_next_allowed_one(self):
        def ph(i, lic):
            return {"id": i, "license_code": lic, "attribution": "a", "medium_url": T29.IMG_URL}
        t = inat_photos.parse_taxon({"results": [{"id": 9, "name": "X y", "default_photo": ph(1, "cc-by"), "taxon_photos": [{"photo": ph(2, "cc-by-nc")}, {"photo": ph(3, "cc0")}]}]})
        row = {"name": "x", "scientific": "X y", "taxon_id": 9}
        self.assertEqual(inat_photos.usable_photo(row, t, PH, skip={1})[0]["photo_id"], 3)
        ok, why = inat_photos.usable_photo(row, t, PH, skip={1, 3})
        self.assertIsNone(ok)

    def test_commons_exclusion_is_separate_from_the_inaturalist_one(self):
        guide_photos.save_photo(self.meta(source="wikimedia_commons", photo_id=None))
        guide_photos.exclude_photo(9, "遠すぎる", source="commons")
        self.assertEqual(list(guide_photos.load_review()), ["commons:9"])
        self.assertFalse(guide_photos.has_cache(9))


class Gate(unittest.TestCase):
    def test_commons_command_refuses_without_live_and_under_test(self):
        a = mock.Mock(live=False, max_requests=5, only=None)
        self.assertEqual(guide_photos.commons_cmd(a), 2)
        a = mock.Mock(live=True, max_requests=5, only=None)
        self.assertEqual(guide_photos.commons_cmd(a), 2)               # テスト中は --live を拒否

    def test_per_run_cap_is_the_policy_value(self):
        a = mock.Mock(live=True, max_requests=500)
        err, left = guide_photos._gate(a, lambda *x: None, "x", CM["max_requests_per_run"])
        self.assertEqual((err, left), (None, 60))
        with mock.patch.dict(os.environ, {"BIYORI_REQ_LOG": "x"}):
            pass


class ConfigAndPolicy(unittest.TestCase):
    def test_new_hosts_are_only_in_the_commons_list_and_wikidata_stays_in_the_places_list(self):
        hosts = load_config()["live"]["allowed_hosts_by_subject"]
        self.assertEqual(sorted(hosts["guide_photos_commons"]), ["commons.wikimedia.org", "upload.wikimedia.org"])
        self.assertEqual([k for k, v in hosts.items() if "www.wikidata.org" in v], ["guide_places"])
        self.assertEqual([k for k, v in hosts.items() if "upload.wikimedia.org" in v], ["guide_photos_commons"])
        self.assertEqual(sorted(hosts["guide_photos"]), sorted(["api.inaturalist.org", "static.inaturalist.org", "inaturalist-open-data.s3.amazonaws.com"]))
        self.assertEqual(CM["image_hosts"], ["upload.wikimedia.org"])
        self.assertEqual(CM["page_hosts"], ["commons.wikimedia.org"])

    def test_user_agent_has_no_email(self):
        self.assertNotIn("@", load_config()["live"]["user_agent"])

    def test_cap_and_licences_are_the_decided_ones(self):
        self.assertEqual((CM["max_requests_per_run"]["value"], CM["thumb_width"]["value"]), (60, 500))
        self.assertFalse(any("NC" in p or "ND" in p for p in CM["license_patterns"]))


class PageCredit(unittest.TestCase):
    def setUp(self):
        self.es = TP.entries(("試験の沼", [TP.U1, TP.U2], {u: {"kinds": ["カワセミ"]} for u in (TP.U1, TP.U2)}))
        self.found, self.parts = TP.parts_for(self.es)

    def page(self, meta):
        return guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [],
                                     photo_for=lambda n: (meta, T29.JPEG) if n == "カワセミ" else None)

    META = {"name": "カワセミ", "image_type": "jpeg", "license": "CC BY-SA 3.0", "attribution": "Alpsdake", "photo_page": PAGE, "source": "wikimedia_commons"}

    def test_commons_credit_has_author_licence_source_and_file_page_link(self):
        page = self.page(self.META)
        text = "".join(TP.parse(page).text)
        self.assertIn("Alpsdake", text)
        self.assertIn("CC BY-SA 3.0", text)
        self.assertIn("Wikimedia Commons", text)
        self.assertIn(CM["source_label"], text)
        self.assertIn(PH["html"]["credit"], TP.parse(page).text)
        self.assertIn(f'<a href="{PAGE}" rel="noopener noreferrer">{PH["html"]["photo_link_commons"]}</a>', page)

    def test_footer_names_both_sources_and_inaturalist_credit_is_unchanged(self):
        self.assertEqual(PH["html"]["credit"], "写真提供: iNaturalist / Wikimedia Commons")
        inat = {**self.META, "source": None, "license": "CC BY", "photo_page": "https://www.inaturalist.org/photos/1"}
        del inat["source"]
        page = self.page(inat)
        self.assertIn(PH["html"]["photo_link"], page)
        self.assertNotIn("出どころ: Wikimedia Commons", page)

    def test_author_is_escaped_and_images_stay_data_uris(self):
        page = self.page({**self.META, "attribution": '<img src=x onerror=alert(1)>'})
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x", page)
        self.assertEqual([a for t, a in TP.parse(page).tags if t == "img" and not dict(a).get("src", "").startswith("data:")], [])

    def test_unsafe_file_page_url_is_not_a_link(self):
        page = self.page({**self.META, "photo_page": "javascript:alert(1)"})
        self.assertNotIn('href="javascript', page)


if __name__ == "__main__":
    unittest.main()
