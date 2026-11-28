"""状態の日付の無い現況は、ガイドの資料の候補の順位では「例年の目安」と同じに数える(指示書 open-question-breadth の続き 第2部。
本人の返事 3、2026-11-28)。今までの形の ask answer の順位は変えない。通信しない。合成データだけ。"""
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=JST)


def spot(name, km, date_):
    cur = {"state": "見頃", "state_raw": "見頃", "display": "見頃", "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{name}",
           "source_class": "official", "freshness": "fresh", "age_days": 1, "read_at": "2026-11-07T09:00:00+09:00"}
    return {"id": "t-" + name, "name": name, "city": name + "町", "prefecture": "神奈川県", "current": cur, "current_unknown": False, "distance_km": km,
            "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak",
            "subject": "autumn_leaves"}


def facts():
    sub = {"subject": "autumn_leaves", "candidates": [spot("試験の谷", 10, None), spot("試験の湖", 150, "2026-11-07")], "avoid": [],
           "nearby_out_of_region": [], "alternatives": []}
    return {"schema": "ikimono-ask-facts/1", "now": NOW.isoformat(), "dates": ["2026-11-08"], "origin": "横浜", "region": "全範囲",
            "subjects": {"autumn_leaves": sub}, "lines": {}, "summary_pages": [], "this_round": {}, "knowledge_cards": []}


def row(plan, name):
    for s in plan.get("sections") or []:
        for it in s["items"]:
            if it["name"] == name:
                return it
    return None


class UndatedRank(unittest.TestCase):
    def test_policy_is_guide_only(self):
        self.assertEqual(AP.load_policy()["undated_current"]["as_typical"], "guide")

    def test_classic_plan_is_unchanged(self):
        plan = AP.build(facts(), "autumn_leaves")
        self.assertIsNotNone(row(plan, "試験の谷"))                          # 日付の無い公式の「見頃」も、今までどおり候補に残る

    def test_guide_plan_counts_undated_as_typical(self):
        tok = AP.GUIDE_RANK.set(True)
        try:
            plan = AP.build(facts(), "autumn_leaves")
        finally:
            AP.GUIDE_RANK.reset(tok)
        self.assertIsNone(row(plan, "試験の谷"))                             # 今年の情報がない候補として外れる(例年の目安と同じ)
        self.assertIsNotNone(row(plan, "試験の湖"))
        self.assertIn("試験の谷", [x["name"] if isinstance(x, dict) else x for x in plan.get("no_this_year") or []])

    def test_view_keeps_dated_and_birds(self):
        pol = {"undated_current": {"as_typical": True}}
        dated = spot("試験の湖", 150, "2026-11-07")
        self.assertIs(AP._rank_view(dated, pol, "autumn_leaves"), dated)
        undated = spot("試験の谷", 10, None)
        self.assertIsNone(AP._rank_view(undated, pol, "autumn_leaves")["current"])
        self.assertIs(AP._rank_view(undated, pol, "birds"), undated)
        self.assertIs(AP._rank_view(undated, {"undated_current": {"as_typical": False}}, "autumn_leaves"), undated)


if __name__ == "__main__":
    unittest.main()
