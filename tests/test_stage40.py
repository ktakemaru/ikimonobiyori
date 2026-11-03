"""段階40(指示書 docs/stage40-wildflower-instructions.md): 野草・高山植物の知識と guide wildflower。通信しない。"""
import json
import unittest
from pathlib import Path

import jsonschema
import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as V
from ikimonobiyori import wildflower as W

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "ikimonobiyori" / "schemas" / "wildflower.schema.json").read_text(encoding="utf-8"))
READY = ["丹沢"]                                   # 山域ごとのコミットで増える


class Data(unittest.TestCase):
    def setUp(self):
        self.d = W.load()

    def test_every_row_is_consistent(self):
        sites = W.sites_by_id()
        for r in self.d["rows"]:
            self.assertIn(r["area"], self.d["areas"], r)
            self.assertTrue(r["src"], r)
            for s in r["src"]:
                self.assertIn(s, self.d["facts"]["sources"], r)
            self.assertIn(r["name"], self.d["facts"]["species"], r)
            W.parse_bloom(r["bloom"])
            if r.get("elev"):
                lo, hi = r["elev"]
                self.assertLessEqual(lo, hi, r)
        for a in self.d["areas"].values():
            for s in a["sites"]:
                self.assertIn(s, sites)

    def test_sources_have_url_class_and_date(self):
        for k, s in self.d["facts"]["sources"].items():
            self.assertTrue(s["url"].startswith("http"), k)
            self.assertIn(s["class"], ("official", "secondary"), k)
            self.assertRegex(s["read_on"], r"^\d{4}-\d\d-\d\d$")

    def test_protected_species_have_a_caution(self):
        for n, sp in self.d["facts"]["species"].items():
            if sp.get("protected"):
                self.assertTrue(sp.get("caution"), n)

    def test_ready_areas_have_rows_in_every_season(self):
        for a in READY:
            months = {m for r in self.d["rows"] if r["area"] == a for m in range(1, 13) if W.month_active(r["bloom"], m)}
            self.assertGreaterEqual(len(months), 8, (a, sorted(months)))


class Parse(unittest.TestCase):
    def test_bloom_parsing(self):
        self.assertTrue(W.month_active("5上-6中", 6))
        self.assertFalse(W.month_active("5上-6中", 7))
        self.assertTrue(W.month_active("10-2", 1))
        self.assertTrue(W.month_active("7", 7))
        self.assertEqual(W.parse_bloom("3-4"), ((3, 0), (4, 2)))


class Output(unittest.TestCase):
    def test_site_json_validates_and_is_not_empty(self):
        r = W.query(site="m022", month=5, with_photo=False)
        jsonschema.validate(r, SCHEMA)
        self.assertEqual(r["status"], "ok")
        self.assertGreaterEqual(len(r["flowers"]), 3)
        self.assertEqual(r["site"]["id"], "m022")
        self.assertIn("例年の時期の目安", r["text"])

    def test_protected_species_are_not_shown_for_a_site_but_are_in_the_area(self):
        site = W.query(site="m022", month=6, with_photo=False)
        area = W.query(area="丹沢", month=6, with_photo=False)
        self.assertNotIn("キンラン", [f["name"] for f in site["flowers"]])
        self.assertIn("キンラン", [f["name"] for f in area["flowers"]])

    def test_preparing_area_says_so_and_invents_nothing(self):
        r = W.query(area="北アルプス", month=8, with_photo=False)
        jsonschema.validate(r, SCHEMA)
        self.assertEqual((r["status"], r["flowers"]), ("preparing", []))
        self.assertIn("準備中", r["text"])

    def test_unknown_site_is_refused(self):
        with self.assertRaises(ValueError):
            W.query(site="m999")

    def test_text_has_no_internal_terms(self):
        rules = V.load_rules()
        for a in READY:
            for m in (3, 5, 8, 11):
                t = W.query(area=a, month=m, with_photo=False)["text"]
                for w in rules.get("internal_terms") or []:
                    self.assertNotIn(w, t)
                for pat in rules.get("dev_terms") or []:
                    import re
                    self.assertIsNone(re.search(pat, t), (a, m, pat))

    def test_grade_follows_the_number_of_independent_publishers(self):
        r = W.query(area="丹沢", month=5, with_photo=False)
        for f in r["flowers"]:
            self.assertEqual(f["grade"] == "established", f["source_count"] >= 2)
