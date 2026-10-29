"""段階26: 退役した出どころの URL(船橋市のページ)・追記・対応表。通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import CP, PLACES, item, recs

P = guide.load_policy()
FUNA = "https://www.city.funabashi.lg.jp/kids/facilities/p000586.html"
C1, C2 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/"


class RetiredUrl(unittest.TestCase):
    def test_funabashi_page_is_retired_with_a_reason_without_the_instruction(self):
        r = guide.load_retired(P)["urls"]
        self.assertEqual(r[FUNA], "ページ内に指示文(段階25、2026-10-30)")

    def test_it_is_not_counted_but_other_urls_are(self):
        build = lambda rows: {e["name"]: e for e in guide.build_entries(rows, PLACES, P, CP)}["試験の池"]
        a = build(recs(item(FUNA, name="試験の池", theme="野鳥"), item(C1, name="試験の池", theme="野鳥")))
        self.assertEqual((a["independent_sources"], a["tier"]), (2, "reference"))             # 記録はされるが、定評にはならない
        b = build(recs(item(C2, name="試験の池", theme="野鳥"), item(C1, name="試験の池", theme="野鳥")))
        self.assertEqual(b["tier"], "curated")                                                # 他の URL は今までどおり

    def test_the_funabashi_place_stays_reference(self):
        import yaml
        d = [e for e in guide.committed_entries() if e["name"] == "ふなばし三番瀬海浜公園"][0]
        self.assertEqual(d["tier"], "reference")
