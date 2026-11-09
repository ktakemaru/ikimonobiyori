"""段階72 第4部: 探索範囲全体への見直し(距離の重み・おすすめの分散・「遠くても」の読み取り・棚卸し)。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import coverage as CV


def spot(name, km, pref, state="見頃", city=None):
    city = city or name + "町"
    cur = {"state": state, "state_raw": state, "state_date": "2026-11-09", "publisher": "試験市", "url": f"https://kouyou.example.org/{name}",
           "source_class": "official", "freshness": "fresh", "age_days": 1, "read_at": "2026-11-10T09:00:00+09:00"}
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": pref, "current": cur, "current_unknown": False, "distance_km": km,
            "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak"}


def facts(cands, scope=None):
    d = {"schema": "ikimono-ask-facts/1", "now": "2026-11-10T09:00:00+09:00", "dates": ["2026-11-14"], "origin": "横浜", "region": "全範囲",
         "subjects": {"autumn_leaves": {"subject": "autumn_leaves", "candidates": cands, "avoid": [], "nearby_out_of_region": [], "alternatives": []}},
         "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": "横浜からの距離で選びました。"}, "summary_pages": [], "this_round": {}}
    if scope:
        d["scope"] = scope
    return d


KANAGAWA = [spot("試験A", 10, "神奈川県"), spot("試験B", 20, "神奈川県"), spot("試験C", 30, "神奈川県"), spot("試験D", 40, "神奈川県")]
OTHERS = [spot("試験E", 120, "栃木県"), spot("試験F", 90, "山梨県")]


class ScopeOf(unittest.TestCase):
    def test_words(self):
        self.assertEqual(AP.scope_of("遠くても構いません。今見られる花と場所を教えて", "default"), "wide")
        self.assertEqual(AP.scope_of("エリア全体でおすすめは?", "question"), "wide")
        self.assertEqual(AP.scope_of("今週末のおすすめ", "default"), "no_origin")
        self.assertEqual(AP.scope_of("大宮から行きやすい場所", "question"), "normal")
        self.assertEqual(AP.scope_of("近場で手軽に紅葉を見たい", "default"), "normal")
        self.assertEqual(AP.scope_of("今週末のおすすめ", "default", refine="近場"), "normal")

    def test_policy_is_not_changed_in_place(self):
        pol = AP.load_policy()
        w = pol["distance"]["near"]["weight"]
        p = AP.scope_policy(pol, "no_origin")
        self.assertEqual(pol["distance"]["near"]["weight"], w)
        self.assertLess(p["distance"]["near"]["weight"], w)
        self.assertNotEqual(p["aims"]["labels"]["near"], "近場で手軽に")
        self.assertIs(AP.scope_policy(pol, "normal"), pol)


class Diversity(unittest.TestCase):
    def test_no_origin_picks_not_all_kanagawa(self):
        plan = AP.build(facts(KANAGAWA + OTHERS, "no_origin"), "autumn_leaves")
        prefs = [p["prefecture"] for p in plan["picks"]]
        self.assertEqual(len(prefs), 3)
        self.assertLessEqual(prefs.count("神奈川県"), 2, prefs)
        self.assertNotIn("近場で手軽に", [s["label"] for s in plan["sections"]])

    def test_cap_relaxes_when_no_other_candidates(self):
        plan = AP.build(facts(KANAGAWA, "no_origin"), "autumn_leaves")
        self.assertEqual(len(plan["picks"]), 3)

    def test_normal_scope_keeps_near_frame(self):
        plan = AP.build(facts(KANAGAWA + OTHERS), "autumn_leaves")
        self.assertIn("近場で手軽に", [s["label"] for s in plan["sections"]])


class Wide(unittest.TestCase):
    def test_region_sections(self):
        plan = AP.build(facts(KANAGAWA + OTHERS + [spot("試験G", 200, "福島県")], "wide"), "autumn_leaves")
        labels = [s["label"] for s in plan["sections"]]
        self.assertNotIn("近場で手軽に", labels)
        self.assertIn("東京・神奈川", labels)
        self.assertIn("栃木・群馬", labels)
        self.assertIn("山梨・長野", labels)
        self.assertIn("新潟・南東北", labels)
        prefs = [p["prefecture"] for p in plan["picks"]]
        self.assertLessEqual(prefs.count("神奈川県"), 2)

    def test_far_candidate_is_kept_in_wide(self):
        plan = AP.build(facts([spot("試験H", 230, "長野県")], "wide"), "autumn_leaves")
        self.assertEqual([p["name"] for p in plan["picks"]], ["試験H"])


class Coverage(unittest.TestCase):
    def test_range_prefectures(self):
        prefs = {p for p, _ in CV.range_prefectures()}
        for p in ("東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県", "山梨県", "長野県", "静岡県", "新潟県", "福島県"):
            self.assertIn(p, prefs)
        self.assertNotIn("愛知県", prefs)
        self.assertIn("福島県", CV.partial_prefectures())

    def test_table_has_columns(self):
        t = CV.table(env={"IKIMONOBIYORI_DATA_DIR": "/nonexistent-dir-for-test"}, cards=[], records={})
        head = t.splitlines()[0]
        for col in ("紅葉", "花(春)", "野鳥", "ススキ", "ホタル", "行事", "山のカード", "承認済みの情報源", "ビジターセンター"):
            self.assertIn(col, head)
        self.assertIn("| 神奈川県", t)


if __name__ == "__main__":
    unittest.main()
