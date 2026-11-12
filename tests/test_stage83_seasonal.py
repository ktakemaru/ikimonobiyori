"""段階83 第2部: 例年この時期の観察記録(iNaturalist の集計)。合成データ(通信しない。http_get を差し替える)。"""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import seasonal_obs as SO
from ikimonobiyori.fetch import ParseError

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=JST)
P = SO.load_policy()


def _sp(tid, sci, ja, iconic, n):
    return {"count": n, "taxon": {"id": tid, "name": sci, "preferred_common_name": ja, "iconic_taxon_name": iconic,
                                  "default_photo": {"url": "x"}}}


def fake_get(calls):
    def get(url):
        calls.append(url)
        q = parse_qs(urlsplit(url).query)
        if "/histogram" in url:
            return 200, json.dumps({"results": {"week_of_year": {str(w): 10 for w in range(1, 53)}}}), {}
        if "term_id" in q:
            return 200, json.dumps({"total_results": 1, "results": [_sp(1, "Farfugium japonicum", "ツワブキ", "Plantae", 4)]}), {}
        taxa = q["iconic_taxa"][0]
        if "Aves" in taxa:
            res = [_sp(1, "Farfugium japonicum", "ツワブキ", "Plantae", 9), _sp(2, "Hypsipetes amaurotis", "ヒヨドリ", "Aves", 8),
                   _sp(3, "Solidago altissima", "Canada goldenrod", "Plantae", 7), _sp(4, "Aster microcephalus", "ノコンギク", "Plantae", 2)]
        else:
            res = [_sp(5, "Sympetrum frequens", "アキアカネ", "Insecta", 6), _sp(6, "Trametes versicolor", "カワラタケ", "Fungi", 3),
                   _sp(7, "Bufo japonicus", "アズマヒキガエル", "Amphibia", 2)]
        return 200, json.dumps({"total_results": len(res), "results": res}), {}
    return get


class Queries(unittest.TestCase):
    def test_years_and_weeks(self):
        self.assertEqual(SO.years_for(NOW), [2021, 2022, 2023, 2024, 2025])
        self.assertEqual(SO.week_of(date(2026, 11, 14)), 46)
        self.assertEqual(SO.week_of(date(2026, 12, 31)), 52)        # 第53週は最後の週にまとめる
        self.assertEqual(SO.window_weeks(1), [52, 1, 2])

    def test_week_queries_shape(self):
        qs = SO.week_queries(SO.region("tokyo_kanagawa"), 46, SO.years_for(NOW))
        self.assertEqual([n for n, _ in qs], ["group:0", "group:1", "flowering"])
        q = parse_qs(urlsplit(qs[0][1]).query)
        self.assertEqual(q["quality_grade"], ["research"])
        self.assertEqual(q["captive"], ["false"])
        self.assertEqual(q["week"], ["46"])
        self.assertEqual((q["d1"], q["d2"]), (["2021-01-01"], ["2025-12-31"]))
        self.assertNotIn("lat", q)                                   # 場所は地域の組(都県)だけ
        fq = parse_qs(urlsplit(qs[2][1]).query)
        self.assertEqual((fq["term_id"], fq["term_value_id"]), (["12"], ["13"]))

    def test_parse_rejects_bad_shapes(self):
        for bad in ({}, {"results": "x"}, {"results": [{"count": "1", "taxon": {"name": "a"}}]}, {"results": [{"count": 1}]}):
            with self.assertRaises(ParseError):
                SO.parse_counts(bad)
        with self.assertRaises(ParseError):
            SO.parse_histogram({"results": {}})

    def test_parse_keeps_only_aggregates(self):
        rows = SO.parse_counts({"results": [_sp(1, "A b", "ツワブキ", "Plantae", 3), _sp(2, "C d", "Canada goldenrod", "Plantae", 2)]})
        self.assertEqual(rows[0], {"taxon_id": 1, "sci": "A b", "ja": "ツワブキ", "iconic": "Plantae", "count": 3})
        self.assertIsNone(rows[1]["ja"])                              # 日本語でない名前は和名にしない


class FetchAndWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.tmp

    def tearDown(self):
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.old

    def test_fetch_resumes_and_respects_budget(self):
        calls = []
        get = fake_get(calls)
        left = lambda: 8 - len(calls)                                 # noqa: E731
        out = SO.run_fetch(NOW, get, left, regions=["tokyo_kanagawa"], weeks=[45, 46, 47])
        self.assertEqual(out["done"], [["tokyo_kanagawa", "totals"], ["tokyo_kanagawa", 45]])   # 5 + 3 回。残り 0 で次の週は送らない
        self.assertEqual(len(calls), 8)
        calls2 = []
        out2 = SO.run_fetch(NOW, fake_get(calls2), lambda: 60 - len(calls2), regions=["tokyo_kanagawa"], weeks=[45, 46, 47])
        self.assertEqual(out2["done"], [["tokyo_kanagawa", 46], ["tokyo_kanagawa", 47]])        # 続きから
        self.assertEqual(out2["left_jobs"], 0)
        saved = json.loads(SO.week_path("tokyo_kanagawa", 46).read_text(encoding="utf-8"))
        self.assertNotIn("default_photo", json.dumps(saved))
        self.assertEqual(saved["years"], [2021, 2022, 2023, 2024, 2025])

    def test_window_filters_and_flowering(self):
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["tokyo_kanagawa"], weeks=[45, 46, 47])
        win = SO.species_window("tokyo_kanagawa", date(2026, 11, 14))
        plants = win["categories"]["plants"]
        names = [r["name"] for r in plants]
        self.assertEqual(names[0], "ツワブキ")
        self.assertNotIn("Canada goldenrod", names)                   # 和名のない種は除く
        self.assertNotIn("ノコンギク", names)                         # 年 5 件に満たない(3 週 × 2 件 ÷ 5 年)
        self.assertTrue(plants[0]["flower_usable"])                   # 開花の注釈 4 × 3 週 = 12
        self.assertEqual(win["totals"]["plants"], 30)

    def test_status_and_ttl(self):
        s = SO.status(NOW)
        self.assertEqual(s["missing"], 6 * 52 + 6)
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["shizuoka"], weeks=[46])
        self.assertEqual(SO.status(NOW)["regions"]["shizuoka"]["weeks_ok"], 1)
        later = NOW + timedelta(days=SO._v(P["ttl_days"]) + 1)
        self.assertEqual(SO.status(later)["regions"]["shizuoka"]["weeks_ok"], 0)   # 有効期間を過ぎたら取り直し

    def test_cli_requires_live_flags(self):
        self.assertEqual(SO.main(["fetch", "--now", NOW.isoformat()], http_get=lambda u: (200, "{}", {})), 4)


class BriefAndVerify(unittest.TestCase):
    ROW = {"id": "O001", "kind": "seasonal_obs", "kind_label": "例年この時期の観察記録", "category": "plants", "region": "東京・神奈川",
           "content": "東京・神奈川・野生の植物(11/2〜11/22ごろ・過去5年(2021〜2025年)): ツワブキ(記録 27 件)",
           "species": ["ツワブキ"], "flowering": [], "values": {}, "source": P["brief"]["source_name"], "source_url": None,
           "url": P["brief"]["source_url"]}

    def _check(self, text):
        brief = {"question": "今の見頃のものを教えて", "facts": [], "cards": [], "seasonal_obs": [self.ROW],
                 "dates": {"today": "2026-11-13", "periods": [["2026-11-14", "2026-11-15"]]}}
        s = GV.sentences([text])[0]
        return [e["code"] for e in GV.seasonal_obs_errors(s, [self.ROW], GV.cfg(), vocab={"ツワブキ", "ノコンギク", "ヒヨドリ"})]

    def test_good_sentence(self):
        self.assertEqual(self._check("過去5年の観察記録では、この時期の東京・神奈川で、ツワブキの記録が多くなっています。[O001]"), [])

    def test_now_assertion_and_missing_past_word(self):
        self.assertIn("seasonal_obs_now", self._check("今、ツワブキが咲いています。過去の記録です。[O001]"))
        self.assertIn("seasonal_obs_not_past", self._check("この時期はツワブキが目立ちます。[O001]"))

    def test_species_not_in_row(self):
        self.assertIn("seasonal_obs_species", self._check("過去5年の観察記録では、ツワブキやノコンギクの記録が多くなっています。[O001]"))

    def test_categories_from_question(self):
        self.assertEqual(GB.seasonal_categories("今の時期に見られるチョウやトンボは?", {}), ["insects"])
        self.assertEqual(GB.seasonal_categories("今ごろ見られるきのこは?", {}), ["fungi"])
        self.assertEqual(GB.seasonal_categories("今週末の紅葉の情報は?", {}), [])
        self.assertEqual(len(GB.seasonal_categories("今の見頃のものを教えて", {})), 5)
        self.assertEqual(GB.seasonal_categories("河津桜はいつ見られる?", {"route": "season_place"}), [])

    def test_internal_word_allowed_phrase(self):
        errs = GV.common_errors("過去5年の観察記録では、ツワブキの記録が多くなっています。\n", "今の見頃のものを教えて", GV.cfg())
        self.assertNotIn("internal_word", [e["code"] for e in errs])
        errs = GV.common_errors("記録では、ツワブキが多い。\n", "今の見頃のものを教えて", GV.cfg())
        self.assertIn("internal_word", [e["code"] for e in errs])

    def test_final_source_line(self):
        src = GV.final_sources([self.ROW], GV.cfg())
        self.assertEqual(src, ["・" + P["brief"]["source_name"] + " " + P["brief"]["source_url"]])


if __name__ == "__main__":
    unittest.main()
