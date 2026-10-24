"""段階19: 推定の座標は使わない。座標は公式ページの地図の埋め込みを確認できた地点だけ承認する(日光の 13 地点)。ほかは下書き(candidate)のまま。通信なし。"""
import unittest
from datetime import date

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, paths, sources

APPROVED = ["kouyou-0042"] + [f"kouyou-{i:04d}" for i in range(44, 55)] + ["kouyou-0058"]     # 公式ページの地図の埋め込みの座標を確認できた 13 地点
STILL_DRAFT = [f"kouyou-{i:04d}" for i in (36, 37, 38, 39, 40, 41, 43, 55, 56, 57, 60, 61)]      # 座標未確認の 12 地点(丸山はユーザーの確認で足した)
DRAFTS = {e["id"]: e for e in yaml.safe_load((paths.CATALOG_DIR / "drafts" / "autumn_leaves.yaml").read_text(encoding="utf-8"))["entries"]}
CAT = {e["id"]: e for e in catalog.approved_entries(catalog.load_catalog("autumn_leaves"))}
POLICY = catalog.load_policy()
POLICY_S = sources.load_policy()


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


class Maruyama(unittest.TestCase):
    """丸山(ユーザーの確認 2026-10-24): 代表点は公式ページの地図の座標。山麓駅付近の可能性があるので粗さを area_1km にし、山頂の標高を details に残す。"""
    E = CAT["kouyou-0059"]

    def test_entry(self):
        e = self.E
        self.assertEqual((e["status"], e["approved_by"], e["location_precision"]), ("approved", "claude_code_provisional", "area_1km"))
        self.assertEqual((e["point"]["lat"], e["point"]["lon"], e["point"]["elevation_m"]), (36.84, 139.72, 468))       # 小数 2 桁(area_1km)
        self.assertEqual(e["site_details"]["map_point"]["lat"], 36.837592)                                              # 原文は site_details
        self.assertEqual(e["site_details"]["summit_elevation_m"], 700)
        self.assertIn("232 m", e["note"])
        self.assertIn("山麓駅付近", e["site_details"]["point_meaning"])

    def test_the_proposal_keeps_the_summit_elevation_in_details(self):
        import json
        import proposal_fixtures as F
        from ikimonobiyori import proposals, profiles
        reg = sources.load_registry("autumn_leaves")
        recs = [sources.make_record(registry=reg, policy=POLICY_S, read_at=F.NOW.isoformat(), source_id="nikko-kankou-autumn-leaves", site="kouyou-0059",
                                    label="【鬼怒川・川治】鬼怒川温泉 丸山", state="◎", updated="2026-10-22")]
        d = date(2026, 10, 25)
        cat = catalog.load_catalog("autumn_leaves")
        part = {"subject": "autumn_leaves", "name": "紅葉", "catalog": cat, "registry": reg,
                "summary": sources.summarize(recs, registry=reg, catalog_doc=cat, policy=POLICY_S, on=F.NOW.date(), dates=[d]),
                "candidates": sources.candidates(cat, reg, [d], POLICY_S), "care": None}
        doc = proposals.build([part], profiles.load_profiles(), policy=POLICY_S, catalog_policy=POLICY, now=F.NOW, dates=[d])
        p = doc["proposals"][0]
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual((p["place"]["lat"], p["place"]["lon"], p["place"]["location_precision"]), (36.84, 139.72, "area_1km"))
        self.assertEqual(p["details"]["site_details"]["summit_elevation_m"], 700)
        self.assertEqual(p["details"]["site_details"]["map_point"]["lon"], 139.718757)
        json.dumps(doc, ensure_ascii=False)


class StillDraft(unittest.TestCase):
    def test_unconfirmed_places_are_candidates_without_a_point(self):
        self.assertEqual(len(STILL_DRAFT), 12)
        for i in STILL_DRAFT:
            self.assertEqual((DRAFTS[i]["status"], "point" in DRAFTS[i]), ("candidate", False), i)
            self.assertNotIn(i, CAT)

    def test_hakone_and_other_unconfirmed_places_have_no_approved_entry(self):
        names = {e["name"] for e in CAT.values()}
        for n in ("箱根 元箱根", "箱根 宮ノ下", "箱根 湯本", "箱根 旧街道 甘酒茶屋付近", "元箱根", "宮ノ下", "八溝山", "西沢渓谷", "智満寺"):
            self.assertNotIn(n, names)

    def test_every_entry_added_in_stage19_comes_from_the_map_embed(self):
        for i, e in CAT.items():
            if int(i.split("-")[1]) >= 36:
                self.assertIn("公式ページの地図の埋め込み", e["tags"]["source"], i)


if __name__ == "__main__":
    unittest.main()
