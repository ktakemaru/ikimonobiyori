"""段階62 第3部: 地点の種類(登山・山岳 / 公園・庭園・湖畔・施設)で狙いを分ける(近場は手軽な地点だけ)・古い現況はおすすめの上位に置かない。
通信なし・合成データ。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import observations as O
from ikimonobiyori import skeleton as SK

import test_stage57 as T57

POL = AP.load_policy()


class SpotKind(unittest.TestCase):
    def test_mountain_names_from_sites(self):
        self.assertIn("檜洞丸", AP.mountain_names())
        self.assertEqual(len(AP.mountain_names()), 76)
        for n in ("檜洞丸(西丹沢)", "丹沢 檜洞丸", "檜洞丸"):
            with self.subTest(n=n):
                self.assertEqual(AP.spot_kind_of({"name": n}, POL), "mountain")
        self.assertIsNone(AP.spot_kind_of({"name": "大山寺・大山阿夫利神社下社"}, POL))      # 名前の一部だけの一致は山にしない
        self.assertEqual(AP.spot_kind_of({"name": "檜洞丸", "spot_kind": "park"}, POL), "park")   # 名所の属性が先

    def test_terrain_to_kind(self):
        self.assertEqual(O._kind_by_terrain(["mountain", "valley"]), "mountain")
        self.assertEqual(O._kind_by_terrain(["lake"]), "park")
        self.assertIsNone(O._kind_by_terrain(["valley"]))
        self.assertIsNone(O._kind_by_terrain(None))

    def test_near_is_only_for_non_mountain_spots(self):
        self.assertEqual(AP.aim_of({"name": "檜洞丸(西丹沢)"}, 40, False, "in_peak", POL), "trek")        # 50km 以内でも登山は近場にしない
        self.assertEqual(AP.aim_of({"name": "試験の庭園"}, 40, False, "in_peak", POL), "near")
        self.assertEqual(AP.aim_of({"name": "河口湖 もみじ回廊", "spot_kind": "park", "elevation_m": 830}, 80, False, "in_peak", POL), "drive")   # 湖畔は標高だけで山歩きにしない
        self.assertEqual(AP.aim_of({"name": "試験の高原", "elevation_m": 830}, 80, False, "in_peak", POL), "trek")                              # 種類が分からなければ従来どおり


class OldRecord(unittest.TestCase):
    def plan(self, today="2026-11-08"):
        subj = {"subject": "autumn_leaves", "avoid": [], "nearby_out_of_region": [], "alternatives": [],
                "candidates": [T57.spot("古い記録の園", 20, date_="2026-10-28", city="古町"), T57.spot("新しい記録の谷", 120, date_="2026-11-07", city="谷町"),
                               T57.spot("新しい記録の山", 60, date_="2026-11-07", city="山町", elevation_m=800)]}
        return AP.build(T57.facts_doc({"autumn_leaves": subj}, dates=(today,), now=today + "T09:00:00+09:00"), "autumn_leaves")

    def test_old_record_is_not_on_top_and_is_hedged(self):
        p = self.plan()
        names = [x["name"] for x in p["picks"]]
        self.assertEqual(names[-1], "古い記録の園")
        old = p["picks"][-1]
        self.assertEqual(old["old_record_note"], "11日前の記録です")
        self.assertEqual(old["phrase"], POL["evidence"]["old_record_phrases"][old["outlook"]])
        self.assertTrue(all(not x.get("old_record") for x in p["picks"][:-1]))

    def test_future_target_counts_from_today(self):
        self.assertEqual(AP._target_age({"current": {"state": "見頃", "state_date": "2026-11-07"}}, AP._d("2026-11-14"), "2026-11-08T09:00:00+09:00"), 1)
        self.assertEqual(AP._target_age({"current": {"state": "見頃", "state_date": "2026-11-07"}}, AP._d("2026-11-14")), 7)

    def test_skeleton_writes_the_note(self):
        p = self.plan()
        subj = {"autumn_leaves": {"subject": "autumn_leaves", "candidates": [T57.spot("古い記録の園", 20, date_="2026-10-28", city="古町"),
                                                                             T57.spot("新しい記録の谷", 120, date_="2026-11-07", city="谷町"),
                                                                             T57.spot("新しい記録の山", 60, date_="2026-11-07", city="山町", elevation_m=800)],
                                  "avoid": [], "nearby_out_of_region": [], "alternatives": []}}
        f = T57.facts_doc(subj, dates=("2026-11-08",), now="2026-11-08T09:00:00+09:00")
        text = SK.compose(f, p, cards=[])
        line = next(ln for ln in text.splitlines() if "古い記録の園" in ln and ln.startswith(("①", "②", "③")))
        self.assertIn("11日前の記録です", line)


if __name__ == "__main__":
    unittest.main()
