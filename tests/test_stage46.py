"""段階46(指示書 docs/stage46-registry-split-instructions.md): 通信なし。
- 紹介サイト・予報会社の台帳(data/sources/secondary/)は、公式の台帳とは別のファイル。公式の台帳のテストは緩めていない。
- tenki.jp は利用規約が「ブラウザ・RSSリーダー以外での取得」を禁じるため、読む対象(summary_pages・名所の pages)に入れない。
- ウェザーニュースは判断に迷うため読まない(承認しない)。"""
import copy
import unittest

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import sources

POLICY = sources.load_policy()
SEC = sources.load_secondary_registry("autumn_leaves")
OFFICIAL = sources.load_registry("autumn_leaves")
BAD_KINDS = ("aggregator", "travel_agency", "weather_company", "personal", "portal_media")


def one(**over):
    s = {"id": "x-koyo", "publisher": "テスト", "publisher_kind": "portal_media", "url": "https://example.test/koyo", "kind": "reference_link",
         "confidence_label": "紹介サイト(公式ではない)", "covers": [{"name": "テストの一覧", "label": "一覧"}],
         "readable": {"status": "ok", "checked_on": "2026-11-04", "robots": "allows"},
         "terms": {"status": "no_prohibition_found"},
         "approval": {"status": "approved", "approved_by": "user", "approved_on": "2026-11-04"}}
    s.update(over)
    return {"schema": "ikimono-status-sources-secondary/1", "subject": "autumn_leaves", "sources": [s]}


class SecondaryRegistry(unittest.TestCase):
    def errs(self, doc):
        return sources.check_secondary_registry(doc, name="autumn_leaves", policy=POLICY)

    def test_the_repository_secondary_registry_passes(self):
        res = dict((p.name, e) for p, e in sources.check_all_secondary())
        self.assertEqual(res.get("autumn_leaves.yaml"), [])

    def test_the_official_registry_is_not_loosened(self):
        """公式の台帳に、紹介サイト・予報会社の発信者を置かない(既存テストの禁止リストと同じ)。"""
        for s in OFFICIAL["sources"]:
            self.assertNotIn(s["publisher_kind"], BAD_KINDS, s["id"])
        self.assertEqual(dict((p.name, e) for p, e in sources.check_all())["autumn_leaves.yaml"], [])

    def test_the_two_registries_do_not_share_ids(self):
        self.assertFalse({s["id"] for s in OFFICIAL["sources"]} & {s["id"] for s in SEC["sources"]})

    def test_every_entry_has_a_confidence_label(self):
        for s in SEC["sources"]:
            self.assertIn(s["confidence_label"], sources.SECONDARY_LABELS, s["id"])
        by = {s["id"]: s for s in SEC["sources"]}
        self.assertEqual(by["walkerplus-koyo-kanagawa"]["confidence_label"], "紹介サイト(公式ではない)")
        self.assertEqual(by["nihon-kisho-koyo-forecast"]["confidence_label"], "予報会社")

    def test_approved_entries_meet_the_conditions(self):
        for s in SEC["sources"]:
            if s["approval"]["status"] == "approved":
                self.assertEqual(s["readable"]["status"], "ok", s["id"])
                self.assertEqual(s["terms"]["status"], "no_prohibition_found", s["id"])
                self.assertNotIn(s["readable"].get("robots"), sources.ROBOTS_BLOCKING, s["id"])
                self.assertEqual(s["approval"]["approved_by"], "user", s["id"])
                self.assertNotEqual(s["kind"], "status_page", s["id"])

    def test_tenki_and_weathernews_are_not_read(self):
        by = {s["id"]: s for s in SEC["sources"]}
        tk, wn = by["tenki-kouyou-kanagawa"], by["weathernews-koyo"]
        self.assertEqual(tk["approval"]["status"], "pending")
        self.assertEqual(tk["readable"]["status"], "refused")
        self.assertEqual(tk["terms"]["status"], "prohibits_summary")
        self.assertEqual(wn["approval"]["status"], "pending")

    def test_nothing_points_the_reader_at_tenki(self):
        """読む対象(地域のまとめページ・名所の pages)に tenki.jp を置かない。過去の値の出所(typical)は残ってよい。"""
        pol = O.load_policy()
        for subj in pol["summary_pages"].values():
            for pref in subj.values():
                for pg in pref:
                    self.assertNotIn("tenki.jp", pg["url"])
        spots = yaml.safe_load(O.SPOTS_PATH.read_text(encoding="utf-8"))
        for sp in spots["spots"]:
            for pg in sp.get("pages") or []:
                self.assertNotIn("tenki.jp", pg["url"], sp["id"])

    # ---- 検査の規則(合成) ----
    def test_a_valid_synthetic_entry_passes(self):
        self.assertEqual(self.errs(one()), [])

    def test_confidence_label_is_required(self):
        d = one()
        del d["sources"][0]["confidence_label"]
        self.assertTrue(self.errs(d))
        self.assertTrue(self.errs(one(confidence_label="公式")))

    def test_approval_needs_terms_readable_and_robots(self):
        self.assertTrue(any("利用条件" in e for e in self.errs(one(terms={"status": "not_checked"}))))
        self.assertTrue(any("読めていない" in e for e in self.errs(one(readable={"status": "unconfirmed", "checked_on": "2026-11-04"}))))
        self.assertTrue(any("robots" in e for e in self.errs(one(readable={"status": "ok", "checked_on": "2026-11-04", "robots": "disallows"}))))

    def test_status_page_and_site_covers_are_rejected(self):
        self.assertTrue(any("status_page" in e for e in self.errs(one(kind="status_page"))))
        self.assertTrue(any("site" in e for e in self.errs(one(covers=[{"site": "kouyou-0001", "label": "x"}]))))

    def test_an_id_shared_with_the_official_registry_is_rejected(self):
        self.assertTrue(any("重複" in e for e in self.errs(one(id="nikko-kankou-autumn-leaves"))))

    def test_the_official_schema_still_refuses_weather_companies(self):
        d = copy.deepcopy(OFFICIAL)
        d["sources"][0]["publisher_kind"] = "weather_company"
        self.assertTrue(sources.schema_errors(d))


class ConfidenceLabel(unittest.TestCase):
    def test_label_by_host(self):
        self.assertEqual(sources.secondary_label("https://n-kishou.com/corp/news-contents/autumn/"), "予報会社")
        self.assertEqual(sources.secondary_label("https://koyo.walkerplus.com/detail/ar0313e154521/"), "紹介サイト(公式ではない)")
        self.assertEqual(sources.secondary_label("https://unknown.example.test/"), "紹介サイト(公式ではない)")

    def test_official_records_have_no_label_and_secondary_do(self):
        self.assertIsNone(O._confidence_label({"source_class": "official", "url": "https://www.nikko-kankou.org/"}))
        self.assertEqual(O._confidence_label({"source_class": "secondary", "url": "https://koyo.walkerplus.com/x"}), "紹介サイト(公式ではない)")


if __name__ == "__main__":
    unittest.main()
