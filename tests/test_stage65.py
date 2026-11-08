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


class Part3ApprovalList(unittest.TestCase):
    """第3部: 承認の一覧(docs/sources-approval.md)は台帳から作る。台帳と一覧の承認の状態が食い違ったら落ちる。"""

    def setUp(self):
        from ikimonobiyori import approval_list as AL
        self.AL = AL
        self.doc = (H.ROOT / "docs" / "sources-approval.md").read_text(encoding="utf-8")

    def test_the_doc_is_what_the_ledgers_produce(self):
        self.assertEqual(self.doc, self.AL.render(), "台帳を変えたら python -X utf8 -m ikimonobiyori.ask sources --approval > docs/sources-approval.md")

    def test_each_item_is_in_the_section_of_its_ledger_status(self):
        pending = self.doc.split("## 1. 承認待ち")[1].split("## 2. 承認済み")[0]
        approved = self.doc.split("## 2. 承認済み")[1].split("## 3.")[0]
        for r in self.AL.collect():
            if r["ledger"] == "catalog" and r["status"] == "approved" and r["by"] != "user":
                continue                                          # 仮の承認のカタログは件数だけ
            key = r["name"] if r["ledger"] == "centers" and r["status"] == "pending" else f"（{r['id']}）" if r["ledger"] != "centers" else r["id"]
            if r["status"] == "pending":
                self.assertIn(key, pending, r["id"])
                self.assertNotIn(f"（{r['id']}）", approved, r["id"])
            elif r["status"] == "approved":
                self.assertIn(key, approved, r["id"])
                self.assertNotIn(f"（{r['id']}）", pending, r["id"])

    def test_render_follows_a_changed_status(self):
        rows = [{"ledger": "sources", "file": "x.yaml", "id": "t-src", "name": "試験の協会", "status": "pending", "by": None, "on": None, "url": "https://example.org/",
                 "kind": "status_page", "publisher_kind": "municipality", "reason": "試験", "readable": {}, "terms": {}}]
        a = self.AL.render(rows, {"sources": {}})
        rows[0].update(status="approved", by="user", on="2026-11-09")
        b = self.AL.render(rows, {"sources": {}})
        self.assertIn("試験の協会（t-src）", a.split("## 2. 承認済み")[0])
        self.assertIn("試験の協会（t-src）", b.split("## 2. 承認済み")[1])
        self.assertNotIn("試験の協会（t-src）", b.split("## 2. 承認済み")[0])

    def test_named_items_are_approved_in_the_list(self):
        approved = self.doc.split("## 2. 承認済み")[1].split("## 3.")[0]
        for i in ("nagatoro-kanko-koyo", "chichibu-navi-koyo", "yamanashi-kankou-koyo-csv", "nagatoro-koyo-matsuri-2026", "kanagawa-museum", "kana-garden-news",
                  "kouyou-0063", "kouyou-0064", "kouyou-0065"):
            self.assertIn(f"（{i}）", approved, i)


if __name__ == "__main__":
    unittest.main()
