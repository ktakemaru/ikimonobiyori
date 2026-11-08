"""段階66: 山のカード(花の百名山)。仕組みのテスト(合成カード。本物のカードはリポジトリに入れない)。通信なし。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import highlights as HL

NONE = {"autumn_leaves": [], "flowers": [], "birds": []}


def card(title, place, cat, facts, sites=(), months=(), aliases=()):
    return {"title": title, "category": cat, "place": place, "place_aliases": list(aliases), "sites": list(sites), "facts": list(facts),
            "condition": {"year_dependent": False, "months": list(months)},
            "source": {"name": "試験の自然公園の解説", "title": "試験", "url": "https://example.org/" + title, "checked_on": "2026-11-09"},
            "confidence": "紹介", "rights": "確認済み", "usage": "ガイドの目として1行"}


class MountainCards(unittest.TestCase):
    def test_a_card_is_found_by_the_site_id(self):
        cs = [card("試験の山の森", "試験の山域", "季節の仕組み", ["山麓は落葉広葉樹林"], sites=["m057"])]
        pls = HL.places("筑波山の見どころを教えて", cs)
        self.assertEqual(pls[0]["site_id"], "m057")
        g = HL.gather(pls, date(2026, 11, 9), cards=cs, centers=[], reports=[], cands=NONE, records=NONE)
        self.assertEqual([c["title"] for c in g["cards"]], ["試験の山の森"])

    def test_flower_cards_near_this_month_come_first(self):
        cs = [card("春の花", "筑波山", "見頃の流れ", ["4月に咲く"], months=[4]),
              card("冬の花", "筑波山", "見頃の流れ", ["12月に咲く"], months=[12]),
              card("夏の花", "筑波山", "見頃の流れ", ["7月に咲く"], months=[7])]
        g = HL.gather(HL.places("筑波山の見どころ", cs), date(2026, 11, 9), cards=cs, centers=[], reports=[], cands=NONE, records=NONE)
        self.assertEqual([c["title"] for c in g["cards"]][0], "冬の花")

    def test_answer_starts_with_the_mountain_nature(self):
        cs = [card("試験の山の植生", "筑波山", "季節の仕組み", ["山麓は落葉広葉樹林", "山頂付近にブナ林"], sites=["m057"]),
              card("試験の山の鳥", "筑波山", "出会い方・歩き方", ["冬は林で小鳥の群れに出会える"], sites=["m057"])]
        t = HL.compose("筑波山の見どころを教えて", today=date(2026, 11, 9), cards=cs, centers=[], reports=[], cands=NONE, records=NONE)["text"]
        self.assertIn("筑波山の自然: 山麓は落葉広葉樹林。山頂付近にブナ林。", t)
        self.assertIn("ガイドの目: 冬は林で小鳥の群れに出会える", t)

    def test_a_species_card_is_not_found_by_an_alias_inside_a_spot_name(self):
        cs = [card("試験の外来の鳥", "試験の鳥", "保全・マナー", ["外来の鳥"], aliases=["試験山地"]),
              card("試験の湖の森", "試験山地の湖", "季節の仕組み", ["湖の森"])]
        spot = {"id": "t-1", "name": "大山 試験山地の湖", "city": "伊勢原市", "area": None, "prefecture": "神奈川県", "point": None,
                "typical": [], "events": [], "flower_kinds": []}
        cands = {"autumn_leaves": [spot], "flowers": [], "birds": []}
        g = HL.gather(HL.places("大山の見どころ", cs), date(2026, 11, 9), cards=cs, centers=[], reports=[], cands=cands, records=NONE)
        titles = [c["title"] for c in g["cards"]]
        self.assertIn("大山 試験山地の湖", [s["name"] for s in g["spots"]])
        self.assertNotIn("試験の外来の鳥", titles)
        self.assertIn("試験の湖の森", titles)


if __name__ == "__main__":
    unittest.main()
