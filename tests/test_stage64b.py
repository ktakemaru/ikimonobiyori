"""段階64 の続き(本人の判断 2026-11-08): 長瀞の 3 地点の承認・花菜ガーデンの承認・計画の答えの形。通信なし。"""
import unittest

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, paths, sources

NAGATORO = {"kouyou-0063": "金石水管橋", "kouyou-0064": "白鳥橋", "kouyou-0065": "埼玉県立自然の博物館"}


class NagatoroApproved(unittest.TestCase):
    CAT = {e["id"]: e for e in catalog.approved_entries(catalog.load_catalog("autumn_leaves"))}

    def test_three_places_are_approved_by_the_user_with_wikidata_points(self):
        for i in NAGATORO:
            e = self.CAT[i]
            with self.subTest(i):
                self.assertEqual((e["status"], e["approved_by"], e["approved_at"]), ("approved", "user", "2026-11-08"))
                self.assertEqual(e["status_sources"], ["nagatoro-kanko-koyo"])
                self.assertTrue(any("wikidata.org/wiki/Q" in s["url"] for s in e["sources"]))
                self.assertEqual(e["tags"]["city"], "長瀞町")
                km, _ = catalog.nearest_origin_km(catalog.load_policy(), {"lat": e["point"]["lat"], "lon": e["point"]["lon"]})
                self.assertLessEqual(km, catalog.load_policy()["range_limit"]["max_km"])

    def test_no_longer_in_the_drafts_and_iwadatami_is_not_added(self):
        drafts = yaml.safe_load((paths.CATALOG_DIR / "drafts" / "autumn_leaves.yaml").read_text(encoding="utf-8"))["entries"]
        self.assertFalse({e["id"] for e in drafts} & set(NAGATORO))
        self.assertFalse(any("岩畳" in e["name"] for e in self.CAT.values()))

    def test_the_approved_nagatoro_source_covers_the_labels_on_its_page(self):
        reg = sources.load_registry("autumn_leaves")
        src = next(s for s in reg["sources"] if s["id"] == "nagatoro-kanko-koyo")
        labels = {c["site"]: c["label"] for c in src["covers"]}
        for i, name in NAGATORO.items():
            self.assertEqual(labels[i], name)
        self.assertEqual(src["approval"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
