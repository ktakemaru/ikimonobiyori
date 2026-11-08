"""段階62 第2部: 複数の都県の指定(都県の OR)・地域外の地点を入れない・地域ごとの行・ページの題名。通信なし・合成データ。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import observations as O
from ikimonobiyori import plan_page as PP
from ikimonobiyori import skeleton as SK

import test_stage34 as T34

P = O.load_policy()


class ResolveMulti(unittest.TestCase):
    def test_or_and_list_forms(self):
        for q in ("東京か神奈川", "東京か神奈川で", "東京と神奈川", "神奈川・埼玉", "東京、神奈川"):
            with self.subTest(q=q):
                r = O.resolve(q, "横浜", P)
                self.assertTrue(r["resolved"])
                self.assertEqual(len(r["parts"]), 2)
        r = O.resolve("東京か神奈川で", "横浜", P)
        self.assertEqual(r["prefectures"], ["東京都", "神奈川県"])
        self.assertEqual(r["name"], "東京・神奈川")

    def test_single_and_unknown_are_unchanged(self):
        self.assertNotIn("parts", O.resolve("東京", "横浜", P))
        self.assertFalse(O.resolve("東京か試験の国", "横浜", P)["resolved"])         # どれかが一致しなければ推測しない

    def test_prefecture_from_text(self):
        self.assertEqual(O.prefecture_from_text("神奈川県"), "神奈川県")
        self.assertEqual(O.prefecture_from_text("", "東京都八王子市"), "東京都")
        self.assertIsNone(O.prefecture_from_text("試験町", None))


class OutOfRegion(T34.Base):
    def outside(self):
        self.write([{"subject": "autumn_leaves", "name": "試験の県の山", "city": "神奈川県", "state": "見ごろ", "state_date": "2026-10-31",
                     "url": "https://pref.example.jp/leaves", "publisher": "神奈川県", "source_class": "official"}])

    def test_outside_list_record_of_another_prefecture_is_not_in_tokyo(self):
        self.outside()
        tokyo = [c["name"] for c in self.facts(region="東京")["candidates"]]
        self.assertNotIn("試験の県の山", tokyo)                                          # 東京の計画に神奈川の山を入れない
        self.assertIn("試験の県の山", [c["name"] for c in self.facts(region="神奈川")["candidates"]])

    def test_multi_region_facts_cover_both_prefectures(self):
        self.outside()
        f = self.facts(region="東京か神奈川")
        names = [c["name"] for c in f["candidates"]]
        self.assertIn("試験の都の庭", names)
        self.assertIn("試験の湖", names)
        self.assertIn("試験の県の山", names)
        self.assertTrue(all(c["prefecture"] in ("東京都", "神奈川県") for c in f["candidates"]))


def fake(picks_by_pref):
    cands = [{"name": n, "prefecture": p} for p, ns in picks_by_pref.items() for n in ns]
    facts = {"region": "東京か神奈川", "subjects": {"autumn_leaves": {"candidates": cands}}}
    plan = {"picks": [{"name": c["name"]} for c in cands]}
    return facts, plan


class RegionParts(unittest.TestCase):
    def test_parts_and_area_names(self):
        facts, plan = fake({"東京都": ["試験の都の庭"], "神奈川県": ["試験の湖", "試験の峠"]})
        AP.attach_region_parts(plan, facts)
        self.assertEqual([(p["name"], p["picks"]) for p in plan["region_parts"]], [("東京", ["試験の都の庭"]), ("神奈川", ["試験の湖", "試験の峠"])])
        self.assertEqual(plan["area_names"], ["東京", "神奈川"])
        self.assertEqual(AP.area_errors("神奈川の候補だけ", plan), [{"code": "area_missing", "detail": "東京"}])

    def test_single_region_is_unchanged(self):
        facts, plan = fake({"神奈川県": ["試験の湖"]})
        facts["region"] = "神奈川"
        AP.attach_region_parts(plan, facts)
        self.assertNotIn("region_parts", plan)

    def test_skeleton_lines_including_shortage(self):
        facts, plan = fake({"神奈川県": ["試験の湖"]})
        AP.attach_region_parts(plan, facts)
        t = SK.cfg()
        lines = [t["region_part"].format(name=p["name"], names="、".join(p["picks"])) if p["picks"] else t["region_part_few"].format(name=p["name"], n=0)
                 for p in plan["region_parts"]]
        self.assertEqual(lines, ["東京で今年の情報が確認できた候補は0件です。", "神奈川の候補は、試験の湖です。"])


class PageTitle(unittest.TestCase):
    def test_title_has_region_dates_and_theme(self):
        self.assertEqual(PP._region_label({"region": "東京か神奈川", "origin": "横浜"}), "東京・神奈川")
        self.assertEqual(PP._region_label({"region": "神奈川", "origin": "横浜"}), "神奈川県")
        self.assertIsNone(PP._region_label({"region": "全範囲", "origin": "横浜"}))
        import yaml
        from pathlib import Path
        pol = yaml.safe_load((Path(PP.__file__).parent / "data" / "ask" / "policy.yaml").read_text(encoding="utf-8"))["plan_page"]["text"]
        self.assertEqual(pol["title_region"].format(dates="11/8(日)", region="東京・神奈川", labels="紅葉・花・野鳥"), "11/8(日) 東京・神奈川の紅葉・花・野鳥のおすすめ")


if __name__ == "__main__":
    unittest.main()
