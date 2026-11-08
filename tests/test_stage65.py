"""段階65: 段階64の積み残しと、会話の練習(11/9)の修正。合成データ・通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP

import test_stage56 as T56

POL = AP.load_policy()
cand = T56.cand


def plan_of(cands, origin="大宮", dates=("2026-11-14", "2026-11-15")):
    f = T56.facts_of(cands, dates=dates)
    f["origin"] = origin
    return AP.build(f, "autumn_leaves", POL)


class Part1DriveAimFromOtherOrigins(unittest.TestCase):
    """第1部: 出発地が横浜以外でも「ドライブ・足を延ばして」の枠が今回のおすすめに入る。"""

    CS = [cand("近い公園", km=27, state="色づき始め", sdate="2026-11-06", age=2, typical=("11-20", "11-30"), prefecture="埼玉県"),
          cand("試験の渓谷の橋", km=51, state="色づき始め", sdate="2026-11-05", age=3, typical=None, city="試験町", prefecture="埼玉県"),
          cand("試験の山", km=46, state="色づき始め", sdate="2026-11-06", age=2, typical=("11-10", "12-05"), elev=600, prefecture="東京都")]

    def test_drive_first_is_a_pick_for_omiya(self):
        p = plan_of(self.CS)
        drive = next(s for s in p["sections"] if s["aim"] == "drive")
        self.assertEqual(drive["items"][0]["name"], "試験の渓谷の橋")
        self.assertIn("試験の渓谷の橋", [x["name"] for x in p["picks"]])

    def test_same_plan_shape_for_another_origin(self):
        p = plan_of(self.CS, origin="新宿")
        self.assertIn("drive", [x["aim"] for x in p["picks"]])

    def test_boundary_distance_is_near_not_drive(self):
        # 長瀞(月の石もみじ公園)が大宮から 50km で「近場」に入る決まり(近場は near_max_km 以内)をそのまま確かめる
        c = cand("境の渓谷", km=POL["aims"]["near_max_km"], state="色づき始め", sdate="2026-11-05", age=3, typical=None)
        self.assertEqual(AP.score_candidate(c, ["2026-11-14"], POL)["aim"], "near")


if __name__ == "__main__":
    unittest.main()
