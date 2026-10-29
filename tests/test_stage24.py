"""段階24: 定評のしきい値のテーマ別化(野鳥・冬鳥は 2 件、ほかは 3 件)・却下/退役した対象の自動昇格の禁止。
通信なし。合成のデータだけ。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import CP, P, PLACES, build, item, recs

A1 = "https://www.city.example.lg.jp/kanko/a.html"                  # A 運営者の発信(自治体)
C1, C2 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/"
D1, D2 = "https://banzokubiology.com/?p=1", "https://4travel.jp/dm/1"


def tier(theme, *urls, name="試験の沼"):
    rows = recs(*[item(u, name=name, theme=theme) for u in urls])
    return build(rows)[name]


class ThemeThreshold(unittest.TestCase):
    def test_threshold_values_come_from_policy(self):
        self.assertEqual(guide.curated_min(P, "野鳥"), 2)
        self.assertEqual(guide.curated_min(P, "冬鳥"), 2)
        for theme in ("花", "桜", "ホタル", "紅葉"):
            self.assertEqual(guide.curated_min(P, theme), 3)
        c = P["tiers"]["curated"]
        self.assertFalse(c["min_independent_by_theme"]["野鳥"]["provisional"])
        self.assertIn("2026-10-30", c["min_independent_by_theme"]["冬鳥"]["source"])

    def test_birds_two_publishers_is_curated(self):
        for theme in ("野鳥", "冬鳥"):
            e = tier(theme, A1, C1)
            self.assertEqual((e["tier"], e["independent_sources"]), ("curated", 2), theme)
            self.assertEqual(e["approval"]["state"], "provisional")

    def test_birds_one_publisher_is_reference(self):
        for theme in ("野鳥", "冬鳥"):
            self.assertEqual(tier(theme, C1)["tier"], "reference", theme)

    def test_same_publisher_two_pages_counts_once(self):
        e = tier("野鳥", C1, "https://kids.rurubu.jp/article/2/")
        self.assertEqual((e["tier"], e["independent_sources"]), ("reference", 1))

    def test_personal_only_is_not_curated(self):
        for theme in ("野鳥", "冬鳥"):
            e = tier(theme, D1, D2)
            self.assertEqual(e["independent_sources"], 2)
            self.assertEqual(e["tier"], "reference", theme)

    def test_other_themes_unchanged(self):
        for theme in ("花", "桜", "ホタル", "紅葉"):
            self.assertEqual(tier(theme, A1, C1)["tier"], "reference", theme)
            self.assertEqual(tier(theme, A1, C1, C2)["tier"], "curated", theme)

    def test_publisher_table_merges_known_hosts(self):
        same = [("https://iko-yo.net/facilities/1", "https://report.iko-yo.net/x"),
                ("https://rurubu.jp/a", "https://kids.rurubu.jp/b")]
        for a, b in same:
            self.assertEqual(guide.classify(a, P)[1], guide.classify(b, P)[1])
        self.assertEqual(guide.classify("https://tabi-mag.jp/x/", P), ("C", "旅行総合研究所タビリス"))
        self.assertNotEqual(guide.classify("https://tabi-mag.jp/x/", P)[1], guide.classify("https://rurubu.jp/a", P)[1])


class RetiredGuard(unittest.TestCase):
    """却下・退役した対象は、件数が足りても自動で定評にしない(古徳沼のデータで確かめる)。"""

    def test_retired_loaded_from_data(self):
        r = guide.load_retired(P)
        self.assertIn("古徳沼", r["names"])
        self.assertIn("https://www.city.naka.lg.jp/event-kankou/kankou-spot/page000276.html", r["urls"])

    def test_retired_name_not_promoted_even_with_enough_publishers(self):
        rows = recs(*[item(u, name="古徳沼", theme="冬鳥") for u in (A1, C1, C2)])
        e = build(rows)["古徳沼"]
        self.assertEqual(e["independent_sources"], 3)
        self.assertEqual(e["tier"], "reference")
        self.assertEqual(e["approval"]["state"], "candidate")
        self.assertTrue(any("却下" in r for r in e["approval"]["reasons"]))

    def test_retired_source_url_not_counted(self):
        naka = "https://www.city.naka.lg.jp/event-kankou/kankou-spot/page000276.html"
        e = tier("冬鳥", naka, C1, name="別の沼")                                    # 退役した出どころ + 1 件 = 数えて 1 件 → 参考
        self.assertEqual(e["tier"], "reference")

    def test_rejected_review_name_not_promoted(self):
        rows = recs(*[item(u, name="外した沼", theme="野鳥") for u in (A1, C1)])
        rv = {"g-x": {"id": "g-x", "state": "rejected", "name": "外した沼", "at": "2026-10-30", "reason": "試験"}}
        e = {x["name"]: x for x in guide.build_entries(rows, PLACES, P, CP, rv)}["外した沼"]
        self.assertEqual(e["tier"], "reference")
        self.assertNotEqual(e["approval"]["state"], "provisional")

    def test_committed_catalog_has_no_retired_promotion(self):
        import yaml
        cat = yaml.safe_load((guide.CATALOG_PATH).read_text(encoding="utf-8"))
        names = {e["name"] for e in (cat.get("entries") or cat.get("catalog") or [])}
        self.assertNotIn("古徳沼", names)


if __name__ == "__main__":
    unittest.main()
