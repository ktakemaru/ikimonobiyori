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

    def test_rule_text_matches_the_plan_in_all_three_files(self):
        for f in ("CLAUDE.md", "AGENTS.md", ".claude/skills/ikimono-weekend/SKILL.md"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("節が2つ以上のときだけ", t, f)
            self.assertIn("plan の `sections` に従う", t, f)
            self.assertNotIn("該当がない狙いは作らない)で", t, f)             # 計画と矛盾する古い文面は残さない

    def test_headings_come_from_the_plan_policy(self):
        self.assertEqual(V.section_headings(), set(POL["aims"]["labels"].values()))


if __name__ == "__main__":
    unittest.main()


# ---- 第3部: 例年の見頃の補完 ----
class TypicalWindows(unittest.TestCase):
    def test_three_spots_have_a_secondary_typical_window(self):
        import yaml
        spots = {s["name"]: s for s in yaml.safe_load((ROOT / "ikimonobiyori" / "data" / "observations" / "spots.yaml").read_text(encoding="utf-8"))["spots"]}
        want = {"町田薬師池公園": "11月中旬～11月下旬", "高尾山": "11月中旬～12月上旬", "御岳山": "10月下旬～11月中旬"}
        for name, text in want.items():
            t = spots[name]["typical"]
            self.assertEqual([x["text"] for x in t], [text], name)
            self.assertEqual(t[0]["source_class"], "secondary")               # 紹介サイト。公式でないことを答えに添える
            self.assertTrue(t[0]["url"].startswith("https://"))
            self.assertNotIn("tenki.jp", t[0]["url"])
        from ikimonobiyori import observations as O
        for name, text in want.items():
            self.assertIsNotNone(O.parse_typical(text, O.load_policy()), name)   # 窓として読める

    def test_festival_period_is_not_used_as_the_typical_window(self):
        import yaml
        from ikimonobiyori import observations as O
        fest = {f["name"]: f for f in yaml.safe_load((ROOT / "ikimonobiyori" / "data" / "observations" / "festivals.yaml").read_text(encoding="utf-8"))["festivals"]}
        pol = O.load_policy()
        w = O.parse_typical("10月下旬～11月中旬", pol)
        f = fest["御岳山 天空もみじまつり"]
        self.assertNotEqual((w[0], w[1]), (f["start"][5:], f["end"][5:]))


# ---- 第4部: 答えの文面の不具合 ----
class TextDefects(unittest.TestCase):
    def test_1_past_window_gets_no_late_phrase(self):
        # 例年の見頃が 10/1〜10/20 で、対象日が 11/14 → 過ぎている見込み。「終盤の可能性」と書かない
        c = cand("終わった花畑", km=60, typical=("10-01", "10-20"), rel="after_peak")
        p = plan_of([c, BASE[0]])
        row = next(r for r in p["ranking"] if r["name"] == "終わった花畑")
        self.assertEqual(row["outlook"], "past")
        self.assertEqual(POL["outlook"]["phrases"]["past"], "見頃を過ぎている可能性が高いです")
        names_of = V.short_names
        bad = "避けたほうがよい場所: 終わった花畑は、例年の見頃が10/1〜10/20で、今週末は終盤の可能性があります。"
        self.assertEqual([e["code"] for e in AP.outlook_conflicts(bad, p, names_of)], ["outlook_conflict"])
        ok = "避けたほうがよい場所: 終わった花畑は、例年の見頃が10/1〜10/20で、見頃を過ぎている可能性が高いです。"
        self.assertEqual(AP.outlook_conflicts(ok, p, names_of), [])

    def test_1b_a_sentence_with_two_spots_is_not_judged(self):
        c = cand("終わった花畑", km=60, typical=("10-01", "10-20"), rel="after_peak")
        p = plan_of([c, BASE[0]])
        text = "終わった花畑は見頃を過ぎ、近場の庭園は終盤の可能性があります。"
        self.assertEqual(AP.outlook_conflicts(text, p, V.short_names), [])

    def test_2_single_day_festival_has_no_period_label(self):
        from datetime import date
        from ikimonobiyori import festivals as FE
        f = {"id": "one", "name": "試験の一日行事", "start": "2026-11-29", "end": "2026-11-29", "organizer": "試験センター", "organizer_class": "official",
             "url": "https://example.org/e", "publisher": "試験センター", "taken_on": "2026-11-06"}
        r = FE.festival_row(f, date(2026, 11, 7))
        self.assertEqual(r["period_line"], "11/29（日）に開催（あと22日）")
        self.assertNotIn("主催者が設定した期間", r["period_line"])
        self.assertNotIn("11/29〜11/29", r["period_line"])
        self.assertTrue(r["single_day"])
        self.assertEqual(FE.festival_row(f, date(2026, 11, 29))["period_line"], "本日11/29（日）に開催")
        rng = FE.festival_row(dict(f, end="2026-11-30"), date(2026, 11, 7))
        self.assertEqual(rng["period_line"], "主催者が設定した期間: あと22日で開始(11/29〜11/30)")       # 期間があるものは従来どおり
        self.assertFalse(rng["single_day"])

    def test_3_inat_source_is_the_search_not_the_top_page(self):
        from ikimonobiyori import observations as O
        api = "https://api.inaturalist.org/v1/observations/species_counts?lat=35.4&lng=139.6&radius=2&d1=2025-10-25&d2=2025-11-08&iconic_taxa=Aves&quality_grade=research&per_page=200&locale=ja"
        u = O.human_inat_url(api)
        self.assertTrue(u.startswith("https://www.inaturalist.org/observations?"))
        for k in ("lat=35.4", "lng=139.6", "radius=2", "d1=2025-10-25", "iconic_taxa=Aves", "view=species"):
            self.assertIn(k, u)
        for k in ("per_page", "locale"):
            self.assertNotIn(k, u)
        self.assertIsNone(O.human_inat_url(None))
        self.assertIsNone(O.human_inat_url("https://example.org/v1/observations/species_counts?lat=1"))
        self.assertIsNone(O.human_inat_url("https://api.inaturalist.org/v1/observations/species_counts?radius=2"))

    def test_3b_verifier_wants_the_search_url_when_the_facts_have_it(self):
        facts = copy.deepcopy(STRICT)
        src = "https://www.inaturalist.org/observations?lat=35.4&lng=139.6&radius=2&view=species"
        for c in facts["subjects"]["birds"]["candidates"]:
            c["inat"] = dict(c["inat"], source_url=src)
        top_only = V.check(GOOD51, facts, R37)
        self.assertIn("source_missing", [e["code"] for e in top_only["answer_errors"]])
        with_search = V.check(GOOD51.replace("https://www.inaturalist.org/", src), facts, R37)
        self.assertNotIn("source_missing", [e["code"] for e in with_search["answer_errors"]])
        self.assertNotIn("source_unused", [e["code"] for e in with_search["answer_errors"]])

    def test_4_no_double_nenrei(self):
        from ikimonobiyori import observations as O
        pol = O.load_policy()
        dup = O.typical_line({"text": "神奈川の秋バラは例年10月中旬～11月上旬頃のスポットが多く"}, {}, [], pol)
        self.assertEqual(dup.count("例年"), 1)
        self.assertEqual(dup, "例年の見頃: 神奈川の秋バラは10月中旬～11月上旬頃のスポットが多く")
        self.assertEqual(O.typical_line({"text": "公式: 例年10月上旬〜10月中旬"}, {}, [], pol), "例年の見頃: 公式: 10月上旬〜10月中旬")
        self.assertEqual(O.typical_line({"text": "11月上旬～11月下旬"}, {}, [], pol), "例年の見頃: 11月上旬～11月下旬")      # 重なりのないものは変えない


# ---- 第5部: 再調査で足したもの ----
class Recheck(unittest.TestCase):
    def test_new_centers_are_pending_and_valid(self):
        from ikimonobiyori import visitor_centers as VC
        import yaml
        cs = {c["id"]: c for c in yaml.safe_load((ROOT / "ikimonobiyori" / "data" / "visitor_centers" / "centers.yaml").read_text(encoding="utf-8"))["centers"]}
        from test_stage55 import APPROVED_IDS
        for cid in ("okutama-vc", "yatsuhigata-nature-center"):
            self.assertIn(cid, cs)
            self.assertEqual(VC.validate_center(cs[cid]), [])
            # 谷津干潟は本人が承認した12施設に入る（approved_by: user）。奥多摩は承認待ちのまま。承認待ちは答えの材料にしない
            self.assertEqual(cs[cid]["approval"]["status"], "approved" if cid in APPROVED_IDS else "pending")
            self.assertEqual("approved_by" in cs[cid]["approval"], cid in APPROVED_IDS)
        self.assertTrue(cs["okutama-vc"]["terms"]["reprint_banned"])                       # 複製・転用の無断禁止（『転載』の語ではないが禁止として扱う）
        # 段階67: 奥多摩も本人の承認(2026-11-09。承認欄 E)で承認済み。承認待ちの一覧に入らないことを id で確かめる
        self.assertEqual([c["id"] for c in VC.pending_centers() if c["id"] in ("okutama-vc", "yatsuhigata-nature-center")], [])
        self.assertEqual((cs["okutama-vc"]["approval"]["approved_by"], cs["okutama-vc"]["approval"]["approved_on"]), ("user", "2026-11-09"))
        from datetime import date as _d
        self.assertEqual({c["id"] for c in VC.approved_centers(_d(2026, 11, 7))}, set(APPROVED_IDS))      # 承認済みは本人が承認した12施設だけ

    def test_new_events_are_usable_with_year_and_weekday(self):
        from datetime import date
        from ikimonobiyori import festivals as FE
        doc = FE.load()
        self.assertEqual(FE.dropped(date(2026, 11, 7), doc), {})
        sayama = FE.for_spot("obs-kouyou-0092", date(2026, 11, 7), doc)
        self.assertEqual(sayama[0]["period_line"], "11/15（日）に開催（あと8日）")          # 1日だけの行事の書式
        fuji = FE.for_spot("kouyou-0012", date(2026, 11, 14), doc)
        self.assertEqual(fuji[0]["period_line"], "主催者が設定した期間: まつり期間中(11/7〜11/29)")
        self.assertEqual(fuji[0]["lightup_line"], "ライトアップ: 日没〜21:00")             # 期間が書かれていないので日にちを足さない


# ---- 第6部: 承認待ちの一覧 ----
class ApprovalList(unittest.TestCase):
    def test_every_pending_center_is_in_the_list_with_a_recommendation(self):
        import yaml
        doc = (ROOT / "docs" / "sources-approval.md").read_text(encoding="utf-8")
        cs = yaml.safe_load((ROOT / "ikimonobiyori" / "data" / "visitor_centers" / "centers.yaml").read_text(encoding="utf-8"))["centers"]
        for c in cs:
            line = next((l for l in doc.splitlines() if l.startswith("| " + c["name"] + " |")), None)
            self.assertIsNotNone(line, c["name"])
            self.assertTrue(any(f"**{r}**" in line for r in ("承認してよい", "要判断", "保留")), c["name"])
            from test_stage55 import APPROVED_IDS
            self.assertEqual(c["approval"]["status"], "approved" if c["id"] in APPROVED_IDS else "pending")

    def test_the_list_has_no_yamakei_url_and_keeps_the_user_decision(self):
        doc = (ROOT / "docs" / "sources-approval.md").read_text(encoding="utf-8")
        self.assertNotIn("yamakei-online", doc)
        self.assertIn("承認は本人が行う", doc)


# ---- 第7部の動作確認で見つかった不具合の修正 ----
class LiveCheckFixes(unittest.TestCase):
    def test_a_facility_that_is_open_that_day_is_not_excluded(self):
        # 休みの規則を調べて「休みの日ではありません」(closed: false)の結果が付いているだけでは、除かない
        open_day = [{"date": "2026-11-14", "closed": False, "line": "11/14(土)は試験の施設の休みの日ではありません。"}]
        shut = [{"date": "2026-11-14", "closed": True, "line": "11/14(土)は試験の施設が休みです。"}]
        c1 = cand("開いている公園", km=20, state="見頃", sdate="2026-11-12", age=1, rel="in_peak", closed_on=open_day)
        c2 = cand("休みの公園", km=21, state="見頃", sdate="2026-11-12", age=1, rel="in_peak", closed_on=shut)
        p = plan_of([c1, c2], dates=("2026-11-14",))
        r = {x["name"]: x["reason"] for x in p["ranking"]}
        self.assertIsNone(r["開いている公園"])
        self.assertEqual(r["休みの公園"], "closed_that_day")

    def test_birds_are_scored_by_the_park_records(self):
        def bird(name, kind, date_, older=False):
            return {"name": name, "kind": kind, "date": date_, "older": older}
        recent = dict(cand("新しい記録の公園", km=20, typical=None, rel=None), park_birds=[bird("カルガモ", "recent", "2026-11-06")])
        old = dict(cand("古い記録の公園", km=20, typical=None, rel=None), park_birds=[bird("サシバ", "recent", "2026-10-12", True)])
        none = dict(cand("記録なしの公園", km=20, typical=None, rel=None), park_birds=[])
        f = {"dates": ["2026-11-07"], "origin": "横浜", "now": "2026-11-07T10:00:00+09:00",
             "subjects": {"birds": {"candidates": [recent, old, none], "avoid": [], "nearby_out_of_region": []}}}
        p = AP.build(f, "birds", POL)
        by = {x["name"]: x for x in p["ranking"]}
        self.assertEqual(by["新しい記録の公園"]["outlook"], "in_peak")
        self.assertEqual(by["古い記録の公園"]["outlook"], "toward")
        self.assertEqual(by["記録なしの公園"]["outlook"], "unknown")
        self.assertGreater(by["新しい記録の公園"]["score"], by["古い記録の公園"]["score"])
        self.assertTrue(all(x["phrase"] is None for x in p["picks"]))              # 野鳥に『見頃』の言い回しは付けない

    def test_all_subjects_plan_takes_one_pick_from_each_subject(self):
        f = facts_of(BASE)
        flower = [cand("花の試験園", km=30, state="見頃", sdate="2026-11-12", age=1, rel="in_peak", city="花市")]
        bird = [dict(cand("鳥の試験園", km=25, typical=None, rel=None, city="鳥市"),
                     park_birds=[{"name": "カルガモ", "kind": "recent", "date": "2026-11-06", "older": False}])]
        f["subjects"]["flowers"] = {"candidates": flower, "avoid": [], "nearby_out_of_region": []}
        f["subjects"]["birds"] = {"candidates": bird, "avoid": [], "nearby_out_of_region": []}
        p = AP.build_all(f, POL)
        self.assertEqual(p["subject"], "all")
        self.assertEqual({x["subject"] for x in p["picks"]}, {"autumn_leaves", "flowers", "birds"})
        self.assertEqual(len(p["picks"]), 3)
        self.assertEqual({r["subject"] for r in p["ranking"]}, {"autumn_leaves", "flowers", "birds"})
        with tempfile.TemporaryDirectory() as d:                                         # ask plan は、対象が複数なら all で作る
            Path(d, "facts.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
            doc = ask.Flow(d, now=ask.S.parse_now("2026-11-07T10:00:00+09:00")).plan()
            self.assertEqual(doc["subject"], "all")
