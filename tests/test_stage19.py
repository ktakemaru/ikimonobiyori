"""段階19: 推定の座標は使わない。座標は公式ページの地図の埋め込みを確認できた地点だけ承認する(日光の 13 地点)。ほかは下書き(candidate)のまま。通信なし。"""
import unittest

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, paths, sources

APPROVED = ["kouyou-0042"] + [f"kouyou-{i:04d}" for i in range(44, 55)] + ["kouyou-0058"]     # 公式ページの地図の埋め込みの座標を確認できた 13 地点
STILL_DRAFT = [f"kouyou-{i:04d}" for i in (36, 37, 38, 39, 40, 41, 43, 55, 56, 57, 59, 60, 61)]      # 座標未確認の 13 地点
DRAFTS = {e["id"]: e for e in yaml.safe_load((paths.CATALOG_DIR / "drafts" / "autumn_leaves.yaml").read_text(encoding="utf-8"))["entries"]}
CAT = {e["id"]: e for e in catalog.approved_entries(catalog.load_catalog("autumn_leaves"))}
POLICY = catalog.load_policy()


class Approved(unittest.TestCase):
    def test_thirteen_provisional_entries_from_the_map_embed(self):
        self.assertEqual(len(APPROVED), 13)
        for i in APPROVED:
            e = CAT[i]
            with self.subTest(i):
                self.assertEqual((e["status"], e["approved_by"], e["location_precision"]), ("approved", "claude_code_provisional", "exact"))
                self.assertIn("公式ページの地図の埋め込み", e["tags"]["source"])
                self.assertIn("公式ページの地図の埋め込み", e["note"])
                self.assertTrue(isinstance(e["point"]["elevation_m"], int))                 # Elevation API の値
                self.assertEqual(e["status_sources"], ["nikko-kankou-autumn-leaves"])
                self.assertTrue(e["sources"][0]["url"].startswith("https://www.nikko-kankou.org/spot/"))
                km, _ = catalog.nearest_origin_km(POLICY, {"lat": e["point"]["lat"], "lon": e["point"]["lon"]})
                self.assertLessEqual(km, POLICY["range_limit"]["max_km"])

    def test_the_coordinates_are_all_different(self):
        pts = [(CAT[i]["point"]["lat"], CAT[i]["point"]["lon"]) for i in APPROVED]
        self.assertEqual(len(set(pts)), len(pts))

    def test_the_registry_covers_point_to_the_new_ids(self):
        reg = sources.load_registry("autumn_leaves")
        covered = {c["site"] for s in reg["sources"] for c in s["covers"] if "site" in c}
        for i in APPROVED:
            self.assertIn(i, covered)

    def test_elevation_checks_that_passed_are_written_in_the_notes(self):
        self.assertIn("差は 11 m", CAT["kouyou-0058"]["note"])
        self.assertIn("差は 3 m", CAT["kouyou-0053"]["note"])


class StillDraft(unittest.TestCase):
    def test_unconfirmed_places_are_candidates_without_a_point(self):
        self.assertEqual(len(STILL_DRAFT), 13)
        for i in STILL_DRAFT:
            self.assertEqual((DRAFTS[i]["status"], "point" in DRAFTS[i]), ("candidate", False), i)
            self.assertNotIn(i, CAT)

    def test_maruyama_is_pending_because_of_the_elevation(self):
        self.assertIn("100 m 以上", DRAFTS["kouyou-0059"]["note"])
        self.assertIn("山頂", DRAFTS["kouyou-0059"]["note"])

    def test_every_entry_added_in_stage19_comes_from_the_map_embed(self):
        for i, e in CAT.items():
            if int(i.split("-")[1]) >= 36:
                self.assertIn("公式ページの地図の埋め込み", e["tags"]["source"], i)


if __name__ == "__main__":
    unittest.main()
