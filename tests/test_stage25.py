"""段階25: 市区町村の代表点を取って範囲を確かめた地点・古徳沼の承認・横浜自然観察の森・却下/退役の保証。通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide

P = guide.load_policy()


def entry(name, theme):
    return next(e for e in guide.committed_entries() if e["name"] == name and e["theme"] == theme)


class Phase1Range(unittest.TestCase):
    def test_places_now_checked_are_provisional_curated_in_range(self):
        for name in ("渡良瀬遊水地", "秋ヶ瀬公園", "泉の森", "奥日光(戦場ヶ原・中禅寺湖)"):
            e = entry(name, "野鳥")
            self.assertEqual((e["tier"], e["range"]["status"], e["approval"]["state"], e["approval"]["by"]), ("curated", "in_range", "provisional", "auto-rule"), name)
            self.assertGreaterEqual(e["independent_sources"], 2)
            self.assertEqual(set(e["range"]["by_origin"]), {"東京", "横浜"})

    def test_one_source_places_stay_reference_even_in_range(self):
        for name in ("ふなばし三番瀬海浜公園",):                                  # 彩湖はフェーズ3 で 2 件になり定評(Phase3 のテスト)
            e = entry(name, "野鳥")
            self.assertEqual((e["tier"], e["range"]["status"], e["approval"]["state"]), ("reference", "in_range", "candidate"), name)

    def test_unknown_municipality_stays_unconfirmed(self):
        # 妙岐ノ鼻・和田公園は段階26 の追記で市区町村(稲敷市)が付いた。市区町村のない記録は今までどおり「範囲は未確認」(合成の記録で確かめる)
        from test_stage23 import CP, PLACES, item, recs
        rows = recs(item("https://rurubu.jp/andmore/spot/9", name="市のない池", theme="野鳥", muni=None), item("https://www.walkerplus.com/article/9/", name="市のない池", theme="野鳥", muni=None))
        e = {x["name"]: x for x in guide.build_entries(rows, PLACES, guide.load_policy(), CP)}["市のない池"]
        self.assertEqual((e["range"]["status"], e["approval"]["state"]), ("pending", "candidate"))


from test_stage23 import CP, PLACES, build, item, recs  # noqa: E402

NAKA = "https://www.city.naka.lg.jp/event-kankou/kankou-spot/page000276.html"
C1, C2 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/"


class KotokuNuma(unittest.TestCase):
    """承認 D: 古徳沼はユーザーの承認で載る。那珂市のページは数えない。ほかの退役・却下の保証は今までどおり。"""

    def test_real_data_kotoku_is_approved_by_user_without_naka(self):
        e = entry("古徳沼", "冬鳥")
        self.assertEqual((e["tier"], e["independent_sources"], e["approval"]["state"], e["approval"]["by"]), ("curated", 2, "approved", "user"))
        self.assertNotIn(NAKA, [s["url"] for s in e["sources"]])
        rv = guide.load_reviews(include_runtime=False)[e["id"]]
        self.assertEqual((rv["state"], str(rv["at"]), rv["by"]), ("approved", "2026-10-30", "user"))

    def test_kotoku_is_shown_in_the_answer_with_count(self):
        found = guide.find(guide.committed_entries(), themes={"冬鳥"}, names=["古徳沼"], policy=P)
        text = guide.render_answer(found, P)
        self.assertIn("古徳沼", text)
        self.assertIn("（参照数 2）", text)

    def test_the_retired_catalog_record_is_kept(self):
        r = guide.load_retired(P)
        self.assertIn("古徳沼", r["names"])
        self.assertIn(NAKA, r["urls"])

    def test_user_approval_lifts_only_that_places_name_guard(self):
        rows = recs(*[item(u, name="古徳沼", theme="冬鳥") for u in (C1, C2)] + [item(u, name="別の池", theme="冬鳥") for u in (C1, C2)])
        retired = {"names": {"古徳沼": "退役", "別の池": "退役"}, "urls": {}}
        kid = guide.entry_id("冬鳥", "東京都", "古徳沼")
        rv = {kid: {"id": kid, "state": "approved", "at": "2026-10-30", "by": "user"}}
        es = {e["name"]: e for e in guide.build_entries(rows, PLACES, P, CP, rv, retired)}
        self.assertEqual(es["古徳沼"]["approval"]["state"], "approved")
        self.assertEqual(es["別の池"]["approval"]["state"], "candidate")           # 承認していない退役の名前は今までどおり
        self.assertTrue(any("退役" in r for r in es["別の池"]["approval"]["reasons"]))

    def test_the_retired_source_url_is_still_not_counted_after_approval(self):
        rows = recs(item(NAKA, name="古徳沼", theme="冬鳥"), item(C1, name="古徳沼", theme="冬鳥"))
        kid = guide.entry_id("冬鳥", "東京都", "古徳沼")
        rv = {kid: {"id": kid, "state": "approved", "at": "2026-10-30", "by": "user"}}
        e = {x["name"]: x for x in guide.build_entries(rows, PLACES, P, CP, rv, {"names": {"古徳沼": "退役"}, "urls": {NAKA: "退役"}})}["古徳沼"]
        self.assertEqual(e["tier"], "reference")                                  # 数えられるのは 1 件だけ

    def test_no_season_places_are_rendered(self):
        found = {"recommend": [], "no_season": [entry("古徳沼", "冬鳥")]}
        self.assertIn(P["answer"]["headings"]["no_season"], guide.render_answer(found, P))


class YokohamaForest(unittest.TestCase):
    """承認 C: 横浜自然観察の森(野鳥)。現況の名所カタログ(yacho-0004)と同じ名前で、現況の答えにも参照数が付く。"""

    def test_curated_and_provisional_with_three_publishers(self):
        e = entry("横浜自然観察の森", "野鳥")
        self.assertEqual((e["tier"], e["independent_sources"], e["range"]["status"], e["approval"]["state"], e["approval"]["by"]),
                         ("curated", 3, "in_range", "provisional", "auto-rule"))
        self.assertTrue(set(e["classes"]) & {"A", "B", "C"})

    def test_the_name_matches_the_status_catalog_so_the_status_answer_gets_a_count(self):
        from ikimonobiyori import catalog
        names = {x["id"]: x["name"] for x in catalog.approved_entries(catalog.load_catalog("birds"))}
        self.assertEqual(names["yacho-0004"], "横浜自然観察の森")
        counts = guide.reference_counts()
        self.assertEqual(guide.reference_count_for(counts, "birds", names["yacho-0004"], P), 3)

    def test_a_retired_naka_style_guard_does_not_touch_it(self):
        self.assertNotIn("横浜自然観察の森", guide.load_retired(P)["names"])


class Phase3(unittest.TestCase):
    def test_promoted_in_phase3(self):
        for name, theme, n in (("大塚池公園", "冬鳥", 3), ("五行川白鳥飛来地", "冬鳥", 2), ("越辺川(川島町)", "冬鳥", 2), ("彩湖", "野鳥", 2)):
            e = entry(name, theme)
            self.assertEqual((e["tier"], e["independent_sources"], e["range"]["status"], e["approval"]["state"]), ("curated", n, "in_range", "provisional"), name)

    def test_one_source_places_stay_candidates(self):
        for name, theme in (("稲波干拓", "冬鳥"), ("行徳鳥獣保護区", "野鳥")):
            e = entry(name, theme)
            self.assertEqual((e["tier"], e["approval"]["state"]), ("reference", "candidate"), name)

    def test_search_cap_is_140_and_fetch_cap_unchanged(self):
        b = P["budget"]["collect"]
        self.assertEqual((b["search"], b["fetch"]), (140, 60))

    def test_places_added_have_wikidata_ids(self):
        import yaml
        pl = yaml.safe_load(guide.PLACES_PATH.read_text(encoding="utf-8"))["places"]
        want = {("栃木県", "栃木市"), ("埼玉県", "さいたま市"), ("埼玉県", "戸田市"), ("栃木県", "日光市"), ("神奈川県", "大和市"), ("千葉県", "船橋市"), ("茨城県", "稲敷市")}
        have = {(p["prefecture"], p["municipality"]) for p in pl}
        self.assertTrue(want <= have)
        for p in pl:
            if (p["prefecture"], p["municipality"]) in want:
                self.assertTrue(p["qid"].startswith("Q"))
