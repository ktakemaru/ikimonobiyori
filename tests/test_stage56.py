"""段階56(指示書 docs/stage56-answer-plan-instructions.md): 通信しない。合成データだけ。
第1部: ask plan(点数の並び・狙いの分散・不採用の理由コード・override・答えと計画の照合)。第2部: 節見出しを挟んだ答えの検査。"""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import ask, ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
POL = AP.load_policy()


def cand(name, *, km=None, state=None, sdate=None, age=None, typical=("11-05", "11-25"), rel=None, elev=None, city=None, prefecture="神奈川県",
         festivals=(), practical=(), avoid=None, source="official", closed_on=()):
    cur = None
    if state:
        cur = {"state": state, "state_raw": state, "state_date": sdate, "read_at": "2026-11-06T09:00:00+09:00", "publisher": "試験の観光協会",
               "url": "https://example.org/" + name, "source_class": source, "freshness": "fresh" if (age is not None and age <= 3) else "stale",
               "age_days": age}
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": prefecture, "area": None, "elevation_m": elev, "current": cur,
            "typical": [{"start": typical[0], "end": typical[1], "text": "例年", "publisher": "x", "url": "https://example.org/t"}] if typical else [],
            "relation": rel, "distance_km": km, "avoid": avoid, "festivals": list(festivals), "practical": [{"text": t} for t in practical],
            "closed_on": list(closed_on)}


def facts_of(cands, dates=("2026-11-14", "2026-11-15"), avoid=(), out=()):
    return {"dates": list(dates), "origin": "横浜", "now": "2026-11-07T10:00:00+09:00",
            "subjects": {"autumn_leaves": {"candidates": cands, "avoid": list(avoid), "nearby_out_of_region": list(out)}}}


def lightup_fest(name="試験まつり", line="ライトアップ: 11/14〜11/29 17:00〜20:00"):
    return {"id": "f", "name": name, "start": "2026-10-31", "end": "2026-11-29", "period_line": "主催者が設定した期間: まつり期間中(10/31〜11/29)", "lightup_line": line}


BASE = [
    cand("近場の庭園", km=20, state="色づき始め", sdate="2026-11-05", age=2, typical=("11-01", "12-05"), rel="in_peak"),
    cand("歩く試験山", km=45, state="見頃", sdate="2026-11-05", age=2, typical=("11-01", "11-30"), rel="in_peak", elev=900),
    cand("遠い試験渓谷", km=140, state="色づき始め", sdate="2026-11-04", age=3, typical=("11-05", "11-25"), rel="in_peak", prefecture="栃木県"),
    cand("夜の試験公園", km=22, typical=None, rel="unknown", festivals=[lightup_fest()]),
]


def plan_of(cands=None, **kw):
    return AP.build(facts_of(cands if cands is not None else BASE, **kw), "autumn_leaves", POL)


class Scoring(unittest.TestCase):
    def test_outlook_classes_follow_the_window_and_state(self):
        d = AP._d("2026-11-14")
        o = lambda c: AP.outlook_of(c, d, POL)
        self.assertEqual(o(cand("a", state="見頃", sdate="2026-11-12", age=1, typical=("11-05", "11-30"), rel="in_peak")), "in_peak")
        self.assertEqual(o(cand("a", state="色づき始め", sdate="2026-11-12", age=1, typical=("11-05", "11-30"), rel="in_peak")), "toward")
        self.assertEqual(o(cand("a", typical=("11-05", "11-18"), rel="in_peak")), "late")                 # 終わりまで7日以内
        self.assertEqual(o(cand("a", typical=("11-20", "12-10"), rel="before_peak")), "toward")           # 始まりまで14日以内
        self.assertEqual(o(cand("a", typical=("12-10", "12-25"), rel="before_peak")), "early")
        self.assertEqual(o(cand("a", state="見頃過ぎ", sdate="2026-11-03", age=4, typical=None, rel="after_peak")), "past")
        self.assertEqual(o(cand("a", typical=("10-01", "10-20"), rel="after_peak")), "past")
        self.assertEqual(o(cand("a", typical=None, rel="unknown")), "unknown")

    def test_old_state_alone_does_not_claim_a_week_two_weeks_ahead(self):
        c = cand("a", state="見頃", sdate="2026-10-29", age=9, typical=None, rel="in_peak")                  # 16日前の「見頃」だけ
        self.assertEqual(AP.outlook_of(c, AP._d("2026-11-14"), POL), "unknown")
        c = cand("a", state="見頃", sdate="2026-11-03", age=4, typical=None, rel="in_peak")                  # 11日前
        self.assertEqual(AP.outlook_of(c, AP._d("2026-11-14"), POL), "in_peak")

    def test_higher_outlook_and_fresher_state_score_higher(self):
        a = AP.score_candidate(cand("a", km=30, state="見頃", sdate="2026-11-06", age=1, rel="in_peak"), ["2026-11-14"], POL)
        b = AP.score_candidate(cand("b", km=30, rel="in_peak"), ["2026-11-14"], POL)                    # 例年の窓だけ(現況なし)
        c = AP.score_candidate(cand("c", km=30, state="見頃", sdate="2026-10-20", age=18, rel="in_peak"), ["2026-11-14"], POL)
        self.assertGreater(a["score"], b["score"])
        self.assertGreater(a["score"], c["score"])
        self.assertEqual(a["breakdown"]["freshness"], 15)
        self.assertEqual(c["breakdown"]["freshness"], POL["freshness"]["older"])
        self.assertEqual(b["breakdown"]["freshness"], POL["freshness"]["no_current"])

    def test_distance_weight_depends_on_the_aim(self):
        near = AP.score_candidate(cand("n", km=10, typical=None, rel="unknown"), ["2026-11-14"], POL)
        far = AP.score_candidate(cand("f", km=150, typical=None, rel="unknown"), ["2026-11-14"], POL)
        self.assertEqual((near["aim"], far["aim"]), ("near", "far"))
        self.assertGreater(near["breakdown"]["distance"], far["breakdown"]["distance"])

    def test_festival_adds_points_but_never_replaces_the_current_state(self):
        base = cand("a", km=30, typical=None, rel="unknown")
        fest = dict(base, festivals=[lightup_fest()])
        s0 = AP.score_candidate(base, ["2026-11-14"], POL)
        s1 = AP.score_candidate(fest, ["2026-11-14"], POL)
        self.assertEqual(s1["breakdown"]["festival"] + s1["breakdown"]["lightup"], POL["bonus"]["festival_active"] + POL["bonus"]["lightup_active"])
        self.assertEqual(s1["outlook"], s0["outlook"])                          # まつりがあっても見込みは変わらない
        self.assertEqual(s1["breakdown"]["freshness"], 0)
        off = AP.score_candidate(dict(base, festivals=[lightup_fest(line="ライトアップ: 11/1〜11/8 17:00〜20:00")]), ["2026-11-14"], POL)
        self.assertEqual(off["breakdown"]["lightup"], 0)                         # 対象日がライトアップの期間外

    def test_secondary_source_is_not_dropped_only_scored_lower(self):
        o = AP.score_candidate(cand("o", km=30, state="見頃", sdate="2026-11-06", age=1, rel="in_peak"), ["2026-11-14"], POL)
        s = AP.score_candidate(cand("s", km=30, state="見頃", sdate="2026-11-06", age=1, rel="in_peak", source="secondary"), ["2026-11-14"], POL)
        self.assertEqual(o["score"] - s["score"], POL["bonus"]["source_official"] - POL["bonus"]["source_secondary"])


class PlanShape(unittest.TestCase):
    def test_sections_picks_and_spread(self):
        p = plan_of()
        self.assertEqual([s["aim"] for s in p["sections"]], ["near", "trek", "far", "night"])        # 該当のある狙いだけ(ドライブは無い)
        self.assertTrue(p["use_headings"])
        self.assertEqual(len(p["picks"]), 3)
        self.assertEqual({x["aim"] for x in p["picks"]}, {"near", "trek", "far"})                     # 近場・歩く・遠出に分散
        self.assertEqual([x["name"] for x in p["picks"]], ["歩く試験山", "近場の庭園", "遠い試験渓谷"])    # 見込みの高い順(見頃中 → 向かう)
        self.assertEqual(p["picks"][0]["phrase"], "見頃が続いている可能性があります")
        self.assertEqual(p["picks"][1]["phrase"], "見頃に向かう可能性があります")

    def test_phrases_are_hedged_and_never_trip_the_peak_claim(self):
        rules = V.load_rules()
        for k, ph in list(POL["outlook"]["phrases"].items()) + list(POL["outlook"]["phrases_typical_only"].items()):
            if ph:
                self.assertIsNone(re.search(rules["now_peak_claim"], ph + "。"), ph)
                for pat in rules["peak_claims"]:
                    self.assertIsNone(re.search(pat, ph), (k, ph))
        self.assertIsNone(POL["outlook"]["phrases"]["unknown"])

    def test_typical_only_candidate_does_not_say_it_is_continuing(self):
        p = plan_of([cand("窓だけ", km=20, rel="in_peak", typical=("11-01", "12-05"))])
        self.assertIn("例年の見頃", p["picks"][0]["phrase"])

    def test_same_input_same_plan(self):
        self.assertEqual(json.dumps(plan_of(), ensure_ascii=False), json.dumps(plan_of(), ensure_ascii=False))

    def test_one_section_means_no_headings(self):
        p = plan_of([BASE[0], cand("近場の二", km=25, state="見頃", sdate="2026-11-06", age=1, rel="in_peak")])
        self.assertEqual(len(p["sections"]), 1)
        self.assertFalse(p["use_headings"])

    def test_same_area_picks_are_not_repeated(self):
        c = [cand("箱根A", km=60, state="色づき始め", sdate="2026-11-06", age=1, rel="in_peak", city="箱根町"),
             cand("箱根B", km=61, state="色づき始め", sdate="2026-11-06", age=1, rel="in_peak", city="箱根町", elev=900),
             cand("近場の庭園", km=20, state="見頃", sdate="2026-11-06", age=1, rel="in_peak", city="横浜市")]
        names = [x["name"] for x in plan_of(c)["picks"]]
        self.assertEqual(sum(1 for n in names if n.startswith("箱根")), 1)

    def test_the_length_limit_is_not_used_by_the_plan(self):
        src = (ROOT / "ikimonobiyori" / "answer_plan.py").read_text(encoding="utf-8")
        self.assertNotIn("max_chars", src)
        self.assertNotIn("1500", src)
        many = [cand(f"名所{i}", km=10 + i, state="見頃", sdate="2026-11-06", age=1, rel="in_peak", city=f"市{i}") for i in range(30)]
        self.assertEqual(len(plan_of(many)["picks"]), 3)


class RejectReasons(unittest.TestCase):
    def reasons(self, p):
        return {r["name"]: r["reason"] for r in p["ranking"]}

    def test_codes(self):
        c = BASE + [
            cand("過ぎた滝", km=30, state="見頃過ぎ", sdate="2026-11-03", age=4, typical=None, rel="after_peak"),
            cand("日帰り外", km=240, state="見頃", sdate="2026-11-06", age=1, rel="in_peak", prefecture="長野県"),
            cand("現況なし公園", km=30, typical=None, rel="unknown"),
            cand("古い現況の公園", km=95, state="色づき始め", sdate="2026-10-01", age=37, typical=None, rel="unknown"),
            cand("近場の二番", km=21, state="色づき始め", sdate="2026-11-05", age=2, typical=("11-01", "12-05"), rel="in_peak"),
            cand("箱根 近場の庭園", km=20, state="色づき始め", sdate="2026-11-05", age=2, typical=("11-01", "12-05"), rel="in_peak"),
        ]
        p = plan_of(c, avoid=[dict(cand("避ける池", km=30, state="見頃過ぎ", sdate="2026-11-03", age=4, typical=None, rel="after_peak"), avoid="past")],
                    out=[cand("県外の遠く", km=300, prefecture="福島県")])
        r = self.reasons(p)
        self.assertEqual(r["過ぎた滝"], "past_expected")
        self.assertEqual(r["避ける池"], "past_expected")
        self.assertEqual(r["日帰り外"], "too_far")
        self.assertEqual(r["現況なし公園"], "no_current")
        self.assertEqual(r["古い現況の公園"], "stale_current")
        self.assertEqual(r["県外の遠く"], "out_of_range")
        self.assertEqual(r["箱根 近場の庭園"], "duplicate_spot")
        self.assertEqual(r["近場の庭園"], None)                                            # 採用
        self.assertEqual(r["近場の二番"], None)                                            # 節の中で採用(上位3件)
        for x in p["ranking"]:
            if x["reason"]:
                self.assertIn(x["reason"], POL["reasons"])
                self.assertEqual(x["reason_label"], POL["reasons"][x["reason"]])

    def test_better_candidate_in_the_same_aim_is_named(self):
        c = [cand(f"近場{i}", km=10 + i, state="見頃", sdate="2026-11-06", age=1, rel="in_peak", city=f"市{i}") for i in range(5)]
        p = plan_of(c)
        lost = [x for x in p["ranking"] if x["reason"] == "same_aim_has_better"]
        self.assertEqual(len(lost), 2)
        self.assertTrue(all(x["reason_detail"].get("better") for x in lost))

    def test_past_candidates_are_never_adopted(self):
        p = plan_of(BASE + [cand("過ぎた滝", km=10, state="見頃過ぎ", sdate="2026-11-03", age=4, typical=None, rel="after_peak")])
        for s in p["sections"]:
            self.assertNotIn("過ぎた滝", [i["name"] for i in s["items"]])
        self.assertNotIn("過ぎた滝", [x["name"] for x in p["picks"]])

    def test_explain_shows_rank_and_breakdown(self):
        p = plan_of()
        e = AP.explain(p, "歩く試験山")[0]
        self.assertEqual(e["where"], "pick")
        self.assertIn("outlook", e["breakdown"])
        self.assertEqual(AP.explain(p, "試験山")[0]["name"], "歩く試験山")                   # 名前の一部でも探せる
        self.assertEqual(AP.explain(p, "存在しない"), [])


class Overrides(unittest.TestCase):
    def test_reason_is_required_and_replace_must_be_a_pick(self):
        p = plan_of()
        with self.assertRaises(ValueError):
            AP.add_override(p, "近場の庭園", "  ")
        with self.assertRaises(ValueError):
            AP.add_override(p, "夜の試験公園", "夜に行きたい", replace="計画にない名所")
        AP.add_override(p, "夜の試験公園", "ライトアップがある", replace="遠い試験渓谷", at="2026-11-07T10:00:00+09:00")
        self.assertEqual(p["overrides"][0]["reason"], "ライトアップがある")

    def test_flow_keeps_overrides_across_rebuilds(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "facts.json").write_text(json.dumps(facts_of(BASE), ensure_ascii=False), encoding="utf-8")
            f = ask.Flow(d, now=ask.S.parse_now("2026-11-07T10:00:00+09:00"))
            f.plan(override="夜の試験公園", reason="ライトアップがある", replace="遠い試験渓谷")
            again = ask.Flow(d, now=ask.S.parse_now("2026-11-07T10:00:00+09:00")).plan()
            self.assertEqual([o["name"] for o in again["overrides"]], ["夜の試験公園"])
            self.assertTrue(Path(d, "answer_plan.json").is_file())


# ---- 答えと計画の照合(検査器) ----
from test_stage51 import GOOD51, STRICT          # noqa: E402  (試験の遊水地・試験の森・試験の公園の3件)
from test_stage37 import RULES as R37           # noqa: E402


def plan_for_strict(picks, overrides=()):
    return {"schema": AP.SCHEMA, "picks": [{"name": n} for n in picks], "ranking": [{"name": n} for n in ("試験の遊水地", "試験の森", "試験の公園")],
            "overrides": list(overrides)}


def codes(r):
    return [e["code"] for e in r["answer_errors"]]


class AnswerAgainstPlan(unittest.TestCase):
    def test_matching_answer_passes(self):
        r = V.check(GOOD51, STRICT, R37, plan=plan_for_strict(["試験の遊水地", "試験の森", "試験の公園"]))
        self.assertTrue(r["ok"], V.report_lines(r))

    def test_unplanned_spot_in_the_answer_is_rejected(self):
        r = V.check(GOOD51, STRICT, R37, plan=plan_for_strict(["試験の遊水地", "試験の森"]))
        self.assertIn("plan_unplanned_spot", codes(r))

    def test_missing_pick_is_rejected(self):
        two = "\n".join(l for l in GOOD51.splitlines() if not l.startswith("③"))
        r = V.check(two, STRICT, R37, plan=plan_for_strict(["試験の遊水地", "試験の森", "試験の公園"]))
        self.assertIn("plan_pick_missing", codes(r))

    def test_override_with_a_reason_allows_the_change(self):
        ov = [{"name": "試験の公園", "reason": "休みの日でないため", "replace": "試験の森", "at": None}]
        three = plan_for_strict(["試験の遊水地", "試験の森"], ov)
        r = V.check(GOOD51.replace("② 試験の森", "② 試験の遊水地の隣"), STRICT, R37, plan=three)
        self.assertNotIn("plan_unplanned_spot", codes(r))                       # 試験の公園は理由つきで足されている
        self.assertNotIn("plan_pick_missing", codes(r))                         # 試験の森は差し替えとして記録されている

    def test_no_plan_means_no_comparison(self):
        r = V.check(GOOD51, STRICT, R37)
        self.assertTrue(r["ok"])


HEAD = """明日(11/2)は、試験の遊水地・試験の森・試験の公園で、冬鳥のカモ類が見られそうです。
今回のおすすめ
近場で手軽に
① 試験の遊水地: この時期に見られる鳥は、コガモ・オナガガモが多く記録されています(iNaturalist、神奈川県で一年の平均より多い傾向。公式ではありません)。10/21時点で「冬鳥のコガモが増えて来ました」(試験の遊水地)。

歩いて楽しむ
② 試験の森: この時期に見られる鳥は、コガモ・オナガガモです(iNaturalist、神奈川県の傾向。公式ではありません)。

絶景・遠出
③ 試験の公園: この時期に見られる鳥は、コガモ・オナガガモです。明日(11/2・月)は試験の里が休みです(公園には入れます)。
出典: https://birds.example.org/ https://www.inaturalist.org/
"""


class SectionHeadings(unittest.TestCase):
    def c(self, text):
        return V.check(text, STRICT, R37)

    def test_answer_with_section_headings_passes(self):
        r = self.c(HEAD)
        self.assertTrue(r["ok"], V.report_lines(r))

    def test_answer_without_headings_still_passes(self):
        self.assertTrue(self.c(GOOD51)["ok"])

    def test_lead_mismatch_is_still_found_across_sections(self):
        bad = HEAD.replace("で、冬鳥のカモ類が見られそうです。", "の冬鳥と、少し足を延ばして庭園の紅葉が楽しめます。", 1)
        self.assertIn("lead_mismatch", codes(self.c(bad)))
        # 見出しの後ろ(2つ目・3つ目の節)の候補も、冒頭の照合の対象になる
        third_only = HEAD.replace("で、冬鳥のカモ類が見られそうです。", "で、冬鳥のカモ類と、湿地の鳥が見られそうです。", 1).replace("試験の公園: この時期", "試験の公園: 湿地ではなく、この時期")
        self.assertNotIn("lead_mismatch", codes(self.c(third_only)))

    def test_headings_come_from_the_plan_policy(self):
        self.assertEqual(V.section_headings(), set(POL["aims"]["labels"].values()))


if __name__ == "__main__":
    unittest.main()
