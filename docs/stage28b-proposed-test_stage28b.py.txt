"""段階28b: 退役した出どころ(retired の URL)を、段階だけでなく、参照数・種名・時期の「表示してよい」の件数からも除く。
承認(reviews)の扱いは変えない。参考へ戻った名所を承認なしに上げる処理は足さない。通信なし。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import P, CP, PLACES, item, recs, build

DEAD = "https://www.city.tochigi.lg.jp/uploaded/attachment/42210.pdf"
MOVED = "https://www.city.tochigi.lg.jp/site/watarase-heartland/2875.html"
GUNMA = "https://www.gmnh.pref.gunma.jp/wp-content/uploads/report2015_15.pdf"
RURU = "https://rurubu.jp/andmore/spot/1"
WALKER = "https://www.walkerplus.com/article/1/"
WINTER = {"text": "11月〜2月", "from": "11月", "to": "2月末"}


def entry(urls, theme="野鳥", name="試験の遊水地", **extra):
    rows = recs(*[item(u, name=name, theme=theme, **(extra.get(u) or {})) for u in urls])
    return build(rows)[name]


class RetiredSourcesAreNotCounted(unittest.TestCase):
    def test_reference_count_leaves_the_retired_publisher_out(self):
        e = entry([DEAD, GUNMA])
        self.assertEqual(e["independent_sources"], 1)                           # 旧: 2(段階の判定は 1 件、参照数は 2 件で食い違った)
        self.assertEqual(e["tier"], "reference")
        self.assertEqual(len(e["sources"]), 2)                                  # 出どころの一覧には残す(消さない)

    def test_a_kind_said_by_a_retired_source_and_one_live_source_is_not_shown(self):
        e = entry([DEAD, GUNMA], **{DEAD: {"kinds": ["チュウヒ"]}, GUNMA: {"kinds": ["チュウヒ"]}})
        k = next(x for x in e["kinds"] if x["kind"] == "チュウヒ")
        self.assertEqual((k["independent_sources"], k["shown"]), (1, False))

    def test_a_kind_said_by_two_live_sources_is_still_shown(self):
        e = entry([DEAD, GUNMA, MOVED], **{DEAD: {"kinds": ["チュウヒ"]}, GUNMA: {"kinds": ["チュウヒ"]}, MOVED: {"kinds": ["チュウヒ"]}})
        k = next(x for x in e["kinds"] if x["kind"] == "チュウヒ")
        self.assertEqual((k["independent_sources"], k["shown"]), (2, True))

    def test_a_kind_only_a_retired_source_says_stays_listed_but_unshown(self):
        e = entry([DEAD, GUNMA], **{DEAD: {"kinds": ["コミミズク"]}})
        k = next(x for x in e["kinds"] if x["kind"] == "コミミズク")
        self.assertEqual((k["independent_sources"], k["shown"]), (0, False))

    def test_a_season_said_by_a_retired_source_and_one_live_source_is_not_shown(self):
        e = entry([DEAD, GUNMA], **{DEAD: {"season": WINTER}, GUNMA: {"season": WINTER}})
        self.assertEqual((e["season"]["independent_sources"], e["season"]["shown"]), (1, False))

    def test_a_season_said_by_two_live_sources_is_still_shown(self):
        e = entry([DEAD, GUNMA, MOVED], **{DEAD: {"season": WINTER}, GUNMA: {"season": WINTER}, MOVED: {"season": WINTER}})
        self.assertEqual((e["season"]["independent_sources"], e["season"]["shown"]), (2, True))

    def test_all_sources_retired_does_not_break(self):
        e = entry([DEAD], **{DEAD: {"kinds": ["チュウヒ"], "season": WINTER}})
        self.assertEqual((e["independent_sources"], e["tier"]), (0, "reference"))
        self.assertEqual((e["kinds"][0]["shown"], e["season"]["shown"]), (False, False))
        self.assertEqual(len(e["sources"]), 1)

    def test_the_answer_shows_the_live_count_and_no_hidden_kind(self):
        e = entry([DEAD, GUNMA, MOVED], **{DEAD: {"kinds": ["チュウヒ", "コミミズク"]}, GUNMA: {"kinds": ["チュウヒ"]}})
        found = guide.find([e], themes={"野鳥"}, on=date(2026, 10, 30), policy=P)
        text = guide.render_answer(found, P)
        self.assertIn("（参照数 2）", text)                                       # 栃木市(DEAD は数えない)と群馬県立自然史博物館
        self.assertNotIn("コミミズク", text)


class NothingElseChanged(unittest.TestCase):
    def test_an_unretired_place_counts_every_source(self):
        e = entry([RURU, WALKER])
        self.assertEqual((e["independent_sources"], e["tier"]), (2, "curated"))

    def test_the_user_approval_is_untouched_and_nothing_is_promoted(self):
        # 退役した名前でも、ユーザーが承認した場所は承認のまま(段階25)。数え方だけが変わる
        rows = recs(*[item(u, name="古徳沼", theme="冬鳥") for u in (RURU, WALKER, MOVED)])
        kid = guide.entry_id("冬鳥", "東京都", "古徳沼")
        rv = {kid: {"id": kid, "state": "approved", "at": "2026-10-30", "by": "user"}}
        retired = {"names": {"古徳沼": "退役"}, "urls": {WALKER: "退役"}}
        e = {x["name"]: x for x in guide.build_entries(rows, PLACES, P, CP, rv, retired)}["古徳沼"]
        self.assertEqual(e["approval"]["state"], "approved")
        self.assertEqual(e["independent_sources"], 2)                           # 退役した WALKER は数えない(旧: 3)
        # 退役した名前に承認がなければ、自動では昇格しない
        e2 = {x["name"]: x for x in guide.build_entries(rows, PLACES, P, CP, {}, retired)}["古徳沼"]
        self.assertEqual((e2["tier"], e2["approval"]["state"]), ("reference", "candidate"))
        # 退役した出どころを除いて下限を割れば、承認があっても自動で上がらない(従来どおり。段階の理由が残る)
        e3 = {x["name"]: x for x in guide.build_entries(rows[:2], PLACES, P, CP, rv, retired)}["古徳沼"]
        self.assertEqual((e3["independent_sources"], e3["tier"], e3["approval"]["state"]), (1, "reference", "candidate"))

    def test_real_catalog_counts_are_the_same_as_before_for_the_named_places(self):
        es = {(e["theme"], e["name"]): e for e in guide.committed_entries()}
        w = es[("野鳥", "渡良瀬遊水地")]
        self.assertEqual((w["independent_sources"], w["tier"]), (4, "curated"))
        self.assertEqual([k["kind"] for k in w["kinds"] if k["shown"]], ["チュウヒ"])
        k = es[("冬鳥", "古徳沼")]
        self.assertEqual((k["independent_sources"], k["approval"]["state"]), (2, "approved"))
        self.assertEqual([x["kind"] for x in k["kinds"] if x["shown"]], ["オオハクチョウ"])


if __name__ == "__main__":
    unittest.main()
