"""段階28: 栃木市の資料(404)の URL を退役にし、同じ栃木市の別のページに差し替えた(渡良瀬遊水地)。
退役した出どころで独立した発行元が下限(野鳥 2 件)を割れば、自動で参考・候補に戻る(勝手に昇格・載せ直しをしない)。通信なし。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import P, item, recs, build

DEAD = "https://www.city.tochigi.lg.jp/uploaded/attachment/42210.pdf"
MOVED = "https://www.city.tochigi.lg.jp/site/watarase-heartland/2875.html"
GUNMA = "https://www.gmnh.pref.gunma.jp/wp-content/uploads/report2015_15.pdf"


def watarase(*urls):
    return build(recs(*[item(u, name="試験の遊水地", theme="野鳥") for u in urls]))["試験の遊水地"]


class RetiredDeadUrl(unittest.TestCase):
    def test_the_dead_url_is_retired_with_the_reason_and_date(self):
        row = next(r for r in P["retired_guard"]["urls"] if r["url"] == DEAD)
        self.assertIn("404", row["reason"])
        self.assertIn("2026-10-30", row["reason"])
        self.assertIn(DEAD, guide.load_retired(P)["urls"])

    def test_real_catalog_does_not_count_the_dead_url_but_keeps_the_place_curated_by_others(self):
        e = next(x for x in guide.committed_entries() if x["name"] == "渡良瀬遊水地" and x["theme"] == "野鳥")
        srcs = e["sources"]
        self.assertIn(MOVED, [s["url"] for s in srcs])
        live = [s for s in srcs if s["url"] not in guide.load_retired(P)["urls"]]
        self.assertGreaterEqual(len(guide.independent_groups(live)), guide.curated_min(P, "野鳥"))     # 死んだ URL を除いても下限以上
        self.assertEqual((e["tier"], e["approval"]["state"]), ("curated", "provisional"))

    def test_the_replacement_is_the_same_publisher_so_it_counts_once(self):
        both = watarase(DEAD, MOVED)
        self.assertEqual(both["independent_sources"], 1)                       # 同じ栃木市は 1 件(段階の判定も 1 件)

    def test_dropping_below_the_floor_returns_to_reference_automatically(self):
        # 退役した出どころ + 1 件 = 1 件(野鳥の下限 2 件を割る)→ 参考・候補。人が戻さない限り、自動では昇格しない
        e = watarase(DEAD, GUNMA)
        self.assertEqual((e["tier"], e["approval"]["state"]), ("reference", "candidate"))
        found = guide.find([e], themes={"野鳥"}, on=date(2026, 10, 30), policy=P)
        self.assertEqual((len(found["recommend"]), len(found["reference"])), (0, 1))

    def test_two_other_publishers_keep_it_curated(self):
        e = watarase(DEAD, GUNMA, MOVED)
        self.assertEqual(e["tier"], "curated")
