"""段階29b: 候補が 2 件以上のとき種を採る条件・日本語の別名の照合・写真の選び方(taxon_photos)・目での確認の除外・ページのカード。通信なし。"""
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_page, guide_photos
from ikimonobiyori.fetch import inat_photos

import test_stage29 as T29
import test_stage29_page as TP

P = guide.load_policy()
PH = P["photos"]
URL = "https://inaturalist-open-data.s3.amazonaws.com/photos/%d/medium.jpg"


def cand(tid, name, rank="species", common="シロハラ", cls="Aves", ja=(), anc=()):
    return {"id": tid, "name": name, "rank": rank, "preferred_common_name": common, "iconic_taxon_name": cls,
            "names": [{"name": n, "locale": "ja"} for n in ja], "ancestor_ids": list(anc)}


def decide(name, *cands):
    return inat_photos.decide(name, inat_photos.parse_search({"results": list(cands)}), PH)


class MultiCandidate(unittest.TestCase):
    def test_one_species_with_subspecies_below_it_is_adopted_and_lists_the_candidates(self):
        row, why = decide("オオタカ", cand(10, "Astur gentilis", common="オオタカ", anc=[1, 2]),
                          cand(11, "Astur gentilis fujiyamae", rank="subspecies", common="オオタカ", anc=[1, 2, 10]))
        self.assertIsNone(why)
        self.assertEqual((row["name"], row["scientific"], row["taxon_id"]), ("オオタカ", "Astur gentilis", 10))
        self.assertEqual([(c["scientific"], c["rank"], c["taxon_id"]) for c in row["candidates"]],
                         [("Astur gentilis", "species", 10), ("Astur gentilis fujiyamae", "subspecies", 11)])

    def test_two_species_are_not_adopted(self):
        row, why = decide("カイツブリ", cand(1, "A b", common="カイツブリ"), cand(2, "C d", common="カイツブリ"))
        self.assertIsNone(row)
        self.assertIn("ちょうど 1 件でない", why)

    def test_other_candidate_not_below_the_species_is_not_adopted(self):
        row, why = decide("X", cand(1, "A b", common="X", anc=[9]), cand(2, "A", rank="genus", common="X", anc=[9]))
        self.assertIsNone(row)
        self.assertIn("下位", why)

    def test_candidate_without_ancestor_ids_is_not_assumed_to_be_below(self):
        row, _ = decide("X", cand(1, "A b", common="X"), cand(2, "A b c", rank="subspecies", common="X"))
        self.assertIsNone(row)

    def test_single_non_species_is_still_not_adopted(self):
        self.assertIsNone(decide("X", cand(1, "A", rank="genus", common="X"))[0])


class JapaneseNames(unittest.TestCase):
    def test_a_ja_name_that_matches_exactly_is_used_when_the_preferred_name_differs(self):
        row, why = decide("シロハラ", cand(5, "Turdus pallidus", common="シロハラ(鳥)", ja=["シロハラ(鳥)", "シロハラ"]))
        self.assertEqual((row["scientific"], why), ("Turdus pallidus", None))

    def test_no_partial_match(self):
        self.assertIsNone(decide("シロハラ", cand(5, "A b", common="シロハラゴジュウカラ", ja=["シロハラゴジュウカラ"]))[0])

    def test_two_ja_matches_that_are_both_species_are_not_adopted(self):
        row, _ = decide("シロハラ", cand(5, "A b", common="あ", ja=["シロハラ"]), cand(6, "C d", common="い", ja=["シロハラ"]))
        self.assertIsNone(row)

    def test_generic_words_stay_out_even_with_a_matching_name(self):
        for n in ("カモ", "シギ", "チドリ"):
            self.assertIsNotNone(inat_photos.skipped(n, PH), n)
        self.assertIsNone(inat_photos.skipped("シロハラ", PH))

    def test_search_asks_for_all_names_on_the_same_host(self):
        url = inat_photos.search_url("シロハラ", PH)
        self.assertTrue(url.startswith("https://api.inaturalist.org/v1/taxa?"))
        self.assertIn("all_names=true", url)

    def test_build_table_reports_candidates_for_adopted_multi_candidate_names(self):
        g = T29.getter({"q=": (200, json.dumps({"results": [
            cand(10, "Astur gentilis", common="オオタカ", anc=[1]), cand(11, "Astur gentilis f", rank="subspecies", common="オオタカ", anc=[1, 10])]}))})
        entered, rejected, rep = inat_photos.build_table(["オオタカ"], http_get=g, ph=PH, max_requests=80, today=date(2026, 10, 31), sleep=lambda s: None)
        self.assertEqual([r["taxon_id"] for r in entered], [10])
        self.assertNotIn("candidates", entered[0])
        self.assertEqual(len(rep["multi_candidate"]["オオタカ"]), 2)


def taxon(photos, default=None, tid=1, name="Alcedo atthis"):
    def ph(i, lic):
        return {"id": i, "license_code": lic, "attribution": f"(c) 撮影者{i}", "medium_url": URL % i}
    return inat_photos.parse_taxon({"results": [{"id": tid, "name": name, "default_photo": ph(*default) if default else None,
                                                  "taxon_photos": [{"photo": ph(*p)} for p in photos]}]})


ROW = {"name": "カワセミ", "scientific": "Alcedo atthis", "taxon_id": 1, "checked_on": "2026-10-31"}


class PhotoChoice(unittest.TestCase):
    def pick(self, t):
        return inat_photos.usable_photo(ROW, t, PH)

    def test_default_photo_is_first(self):
        ok, _ = self.pick(taxon([(2, "cc-by")], default=(1, "cc0")))
        self.assertEqual((ok["photo_id"], ok["license"]), (1, "CC0"))

    def test_falls_back_to_the_first_allowed_taxon_photo_in_order(self):
        ok, _ = self.pick(taxon([(2, "cc-by-nc"), (3, "cc-by-sa"), (4, "cc-by")], default=(1, "cc-by-nc-sa")))
        self.assertEqual((ok["photo_id"], ok["license"]), (3, "CC BY-SA"))

    def test_same_photo_listed_twice_is_one_candidate(self):
        t = taxon([(1, "cc-by-nc")], default=(1, "cc-by-nc"))
        self.assertEqual(len(t["photos"]), 1)

    def test_none_allowed_gives_a_licence_reason(self):
        ok, why = self.pick(taxon([(2, "cc-by-nd"), (3, None)], default=(1, "cc-by-nc")))
        self.assertIsNone(ok)
        self.assertIn("ライセンス", why)
        self.assertIn("3 枚", why)

    def test_disallowed_host_photo_is_skipped_for_the_next(self):
        t = taxon([(3, "cc-by")], default=(1, "cc-by"))
        t["photos"][0]["urls"]["medium_url"] = "https://evil.example.com/p.jpg"
        ok, _ = self.pick(t)
        self.assertEqual(ok["photo_id"], 3)

    def test_still_checks_scientific_name(self):
        self.assertIn("学名", self.pick(taxon([(2, "cc-by")], name="Other x"))[1])


class Review(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def test_exclude_removes_the_cached_photo_and_records_the_reason_only_under_the_data_dir(self):
        guide_photos.save_photo({"meta": {"name": "カワセミ", "taxon_id": 1, "image_type": "jpeg", "license": "CC BY", "attribution": "x"},
                                 "data": T29.JPEG, "ext": "jpeg"})
        self.assertEqual(guide_photos.exclude_photo(1, "羽だけが写っている"), 2)
        self.assertFalse(guide_photos.has_cache(1))
        self.assertEqual(guide_photos.load_review(), {"1": "羽だけが写っている"})
        self.assertTrue(str(guide_photos.review_path()).startswith(self.tmp.name))

    def test_excluded_species_are_not_fetched_again(self):
        guide_photos.exclude_photo(1, "遠すぎる")
        table = {"カワセミ": {"name": "カワセミ", "scientific": "Alcedo atthis", "taxon_id": 1, "checked_on": "2026-10-31"}}
        calls = []

        def hg(url, *a):
            calls.append(url)
            return 500, "", {}
        a = mock.Mock(live=True, max_requests=10)
        with mock.patch.object(guide_photos, "load_table", return_value=table), mock.patch.dict(os.environ, {"BIYORI_REQ_LOG": "x"}):
            guide_photos.fetch_cmd(a, http_get=hg, http_bytes=lambda *x: (500, b"", {}))
        self.assertEqual(calls, [])


class PageCards(unittest.TestCase):
    def setUp(self):
        self.es = TP.entries(("試験の沼", [TP.U1, TP.U2], {u: {"kinds": ["カワセミ", "ヤマセミ"]} for u in (TP.U1, TP.U2)}))
        self.found, self.parts = TP.parts_for(self.es)
        self.names = guide_page.species_in(self.parts)

    def build(self, in_table):
        return guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [],
                                     photo_for=lambda n: None, in_table=in_table)

    def test_only_species_in_the_table_get_cards_and_the_rest_is_one_text_line(self):
        self.assertGreaterEqual(len(self.names), 2)
        keep, rest = self.names[0], self.names[1:]
        page = self.build(lambda n: n == keep)
        cards = [t for t in TP.parse(page).tags if t[0] == "h3"]
        h3_texts = TP.parse(page).text
        self.assertIn(P["photos"]["html"]["others"].format(names=P["photos"]["html"]["others_sep"].join(rest)), h3_texts)
        self.assertEqual(page.count('class="card"'), page.count('<li class="card">'))
        self.assertEqual(page.count(P["photos"]["html"]["no_photo"]), 1)         # 対応表にある 1 種のカードだけ
        self.assertTrue(cards is not None)

    def test_without_in_table_every_species_is_a_card(self):
        page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [], photo_for=lambda n: None)
        self.assertEqual(page.count(P["photos"]["html"]["no_photo"]), len(self.names))
        self.assertNotIn(P["photos"]["html"]["others"].split("{")[0], TP.parse(page).text)

    def test_the_others_line_is_escaped_text(self):
        parts = json.loads(json.dumps(self.parts, default=str))
        parts["sections"][0]["rows"][0]["entry"]["kinds"] = [{"kind": "<b>x</b>", "shown": True}]
        page = guide_page.build_page(parts, policy=P, now=TP.NOW, photo_for=lambda n: None, in_table=lambda n: False)
        self.assertNotIn("<b>x</b>", page)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", page)


if __name__ == "__main__":
    unittest.main()
