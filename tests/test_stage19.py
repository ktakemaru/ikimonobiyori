"""段階19: 紅葉の名所カタログへの追加(座標は所在地・目印からの推定)。追加した 20 件の性質と、足さなかった 6 件の下書き。通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, paths, sources
import yaml

ADDED = [f"kouyou-{i:04d}" for i in range(36, 56)]
NOT_ADDED = {"kouyou-0056": "八溝山", "kouyou-0057": "男体山(大子町)", "kouyou-0058": "六方沢(六方沢橋)", "kouyou-0059": "鬼怒川温泉 丸山",
             "kouyou-0060": "接岨峡・長島ダム・奥大井湖上駅", "kouyou-0061": "智満寺"}
CAT = {e["id"]: e for e in catalog.approved_entries(catalog.load_catalog("autumn_leaves"))}
POLICY = catalog.load_policy()


class Added(unittest.TestCase):
    def test_twenty_provisional_entries_with_coarse_estimated_points(self):
        for i in ADDED:
            e = CAT[i]
            with self.subTest(i):
                self.assertEqual((e["status"], e["approved_by"], e["approved_at"]), ("approved", "claude_code_provisional", "2026-10-24"))
                self.assertIn(e["location_precision"], ("area_1km", "area_10km"))            # 推定の点は exact にしない
                self.assertIsNone(e["point"]["elevation_m"])                                   # 推定の点なので標高は入れない(D-12)
                self.assertIn("推定", e["tags"]["source"])
                km, _ = catalog.nearest_origin_km(POLICY, {"lat": e["point"]["lat"], "lon": e["point"]["lon"]})
                self.assertLessEqual(km, POLICY["range_limit"]["max_km"])

    def test_only_the_nishizawa_entry_has_a_typical_window(self):
        self.assertEqual([i for i in ADDED if CAT[i].get("typical_window")], ["kouyou-0055"])
        self.assertEqual((CAT["kouyou-0055"]["typical_window"]["start"], CAT["kouyou-0055"]["typical_window"]["end"]), ("10-01", "10-20"))

    def test_the_registry_covers_point_to_the_new_ids(self):
        reg = sources.load_registry("autumn_leaves")
        covered = {c["site"]: s["id"] for s in reg["sources"] for c in s["covers"] if "site" in c}
        for i in ADDED:
            self.assertIn(i, covered)
            self.assertEqual(CAT[i]["status_sources"], [covered[i]])


class NotAdded(unittest.TestCase):
    def test_drafts_are_candidates_without_a_point(self):
        d = yaml.safe_load((paths.CATALOG_DIR / "drafts" / "autumn_leaves.yaml").read_text(encoding="utf-8"))
        got = {e["id"]: e for e in d["entries"]}
        for i, name in NOT_ADDED.items():
            self.assertEqual((got[i]["name"], got[i]["status"], "point" in got[i]), (name, "candidate", False))
            self.assertNotIn(i, CAT)

    def test_unapproved_places_are_not_in_the_catalog_names(self):
        names = {e["name"] for e in CAT.values()}
        for n in ("八溝山", "男体山(大子町)", "智満寺"):
            self.assertNotIn(n, names)


if __name__ == "__main__":
    unittest.main()
