"""段階58(指示書 docs/stage58-area-and-official-fetch-instructions.md): エリア・場所の質問の堅牢化。通信しない。合成データだけ。"""
import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP, ask, areas as AR, skeleton as SK
from ikimonobiyori import ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
RULES = V.load_rules()
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def spot(name, km=20, state="見頃", date_="2026-11-05", window=("11-01", "11-30"), city="試験町", source_class="official", **kw):
    cur = {"state": state, "state_raw": state, "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{city}", "source_class": source_class,
           "freshness": "fresh", "age_days": 2, "read_at": "2026-11-07T09:00:00+09:00"} if state else None
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": "埼玉県", "current": cur, "current_unknown": cur is None, "distance_km": km,
            "typical": [{"text": "例年11月", "start": window[0], "end": window[1], "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak", **kw}


def facts_doc(subjects, dates=("2026-11-08",), now="2026-11-07T12:00:00+09:00", origin="横浜", **lines):
    return {"schema": "ikimono-ask-facts/1", "now": now, "dates": list(dates), "origin": origin, "region": "全範囲", "subjects": subjects,
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": f"{origin}からの距離で選びました。", **lines}, "summary_pages": [], "this_round": {}}


def subject(*cands):
    return {"subject": "autumn_leaves", "candidates": list(cands), "avoid": [], "nearby_out_of_region": [], "alternatives": []}


class Part1Area(unittest.TestCase):
    def test_question_forms(self):
        self.assertEqual(AR.from_question("秩父・長瀞のエリアで紅葉のおすすめを教えて"), ["秩父", "長瀞"])
        self.assertEqual(AR.from_question("飯能あたりの紅葉はどう?"), ["飯能"])
        self.assertEqual(AR.from_question("箱根周辺の紅葉"), ["箱根"])
        self.assertEqual(AR.from_question("明日 紅葉を見に行きたい"), [])

    def test_resolve_does_not_mistake_names(self):
        self.assertEqual(AR.resolve("奥秩父")["name"], "秩父")
        self.assertEqual(AR.resolve("富士山")["name"], "富士五湖")
        self.assertIsNone(AR.resolve("高尾山口駅前"))
        self.assertIsNone(AR.resolve("軽井"))                                   # 一部だけでは決めない
        d = AR.describe(["秩父市の山奥", "ありえない郷"])
        self.assertEqual(d["found"], [])
        self.assertEqual(d["unknown"][1], "ありえない郷のエリアの範囲を特定できませんでした。")
        self.assertIn("秩父", d["unknown"][0])                                  # 確実に近い名前だけ示す

    def test_members_by_city_or_radius(self):
        a = AR.resolve("秩父")
        cands = [{"name": "中津峡", "city": "秩父市中津川"}, {"name": "横浜の庭", "city": "横浜市"}, {"name": "座標の渓谷", "city": "どこか", "point": {"lat": 35.96, "lon": 138.95}},
                 {"name": "遠い山", "city": "どこか", "point": {"lat": 36.7, "lon": 139.7}}]
        self.assertEqual([c["name"] for c in AR.members(a, cands)], ["中津峡", "座標の渓谷"])

    def test_area_plan_contains_area_spots_and_passes(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"), spot("三峰山", 95, city="秩父市", elevation_m=1000), spot("宝登山", 80, city="長瀞町"),
                                                  spot("横浜の庭", 5, city="横浜市"))})
        plan = AP.build_areas(f, [AR.resolve("秩父"), AR.resolve("長瀞")], "autumn_leaves")
        self.assertEqual([s["heading"] for s in plan["segments"]], ["秩父", "長瀞"])
        names = [p["name"] for s in plan["segments"] for p in s["plan"]["picks"]]
        self.assertTrue({"中津峡", "三峰山"} & set(names))
        self.assertIn("宝登山", names)
        self.assertNotIn("横浜の庭", names)
        text = SK.compose(f, plan)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))

    def test_area_without_spot_still_gets_a_line_and_missing_area_fails(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"))})
        plan = AP.build_areas(f, [AR.resolve("秩父"), AR.resolve("飯能")], "autumn_leaves")
        text = SK.compose(f, plan)
        self.assertIn("飯能は、今年の情報が確認できていません。", text)
        self.assertTrue(V.check(text, f, RULES, plan=plan)["ok"])
        codes = [e["code"] for e in V.check("① 中津峡: 例年の見頃です。\n", f, RULES, plan=plan)["answer_errors"]]
        self.assertIn("area_missing", codes)


if __name__ == "__main__":
    unittest.main()
