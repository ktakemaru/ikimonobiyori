"""段階63a(指示書 docs/stage63a-answer-gates-instructions.md): 答えが必ず出る仕組み。通信しない。合成データ・一時フォルダだけ。"""
import io
import json
import re
import tempfile
import time
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP, answer_run as AR, ask
from ikimonobiyori import ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=JST)
CANNOT = "答えを用意できません"
REAL_QUESTIONS = ["今日お出かけするならどこ?", "イキモノビヨリを使って、今日お出かけするならどこ?", "埼玉と神奈川で紅葉",
                  "今週末と来週末のおすすめ", "大宮から近場で手軽に", "今週末のおすすめを教えて。東京か神奈川で", "箱根の紅葉はどう?",
                  "神奈川で、野鳥や地形の観察会はある?", "冬桜について教えて", "渡り鳥が来ているとききました。どこで見られる?",
                  "高山植物と見頃を教えて", "11/15に桜を見たい"]


def answer_ok(tc, res, q):
    t = res["text"]
    tc.assertTrue(t.strip(), q)
    tc.assertNotIn(CANNOT, t, q)
    tc.assertEqual(V.question_errors(t, V.load_rules()), [], q)              # 利用者への質問がない
    tc.assertEqual(V.internal_word_errors(t), [], q)                        # 内部用語がない
    tc.assertIn(res["status"], (AR.STATUS_PASS, AR.STATUS_DEGRADED, AR.STATUS_BLOCKED), q)
    tc.assertIn(res["stage"], (1, 2, 3, 4), q)


class AlwaysAnswers(unittest.TestCase):
    """第1部: 一発コマンドは、必ず空でない答えの本文を出す(記録がまったくない一時フォルダでも)。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.p = unittest.mock.patch.dict("os.environ", self.env)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_real_failed_questions_get_non_empty_answers_within_the_budget(self):
        for q in REAL_QUESTIONS:
            t0 = time.monotonic()
            res = AR.run(q, now=NOW, env=self.env)
            self.assertLess(time.monotonic() - t0, AP.load_policy()["answer_run"]["budget_s"]["value"], q)
            answer_ok(self, res, q)

    def test_cli_prints_the_answer_and_exits_zero(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = ask.main(["answer", "--question", "今日お出かけするならどこ?", "--now", NOW.isoformat()])
        self.assertEqual(rc, 0)
        self.assertTrue(out.getvalue().strip())
        self.assertNotIn(CANNOT, out.getvalue())
        self.assertIn("状態: ", err.getvalue())
        self.assertNotIn("状態: ", out.getvalue())                           # 状態は答えの本文に混ぜない

    def test_each_question_gets_its_own_work_folder(self):
        a = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env)
        b = AR.run("箱根の紅葉はどう?", now=NOW, env=self.env)
        self.assertNotEqual(a["workdir"], b["workdir"])

    def test_falls_back_to_the_minimal_answer_when_every_check_fails(self):
        with unittest.mock.patch.object(AR, "gate_check", lambda text, *a, **k: {"ok": False, "text": text, "errors": [{"code": "x", "detail": "x", "gate": "fact"}], "warnings": []}):
            res = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env)
        self.assertEqual(res["stage"], 4)
        self.assertEqual(res["status"], AR.STATUS_DEGRADED)
        self.assertNotIn("internal_error", [w["code"] for w in res["warnings"]])      # 例外ではなく、決まった段で最低限の答えになる
        answer_ok(self, res, "fallback")
        self.assertIn(AP.load_policy()["answer_run"]["minimal"]["how_heading"], res["text"])

    def test_internal_error_still_gives_an_answer(self):
        with unittest.mock.patch.object(AR, "_plan_route", side_effect=RuntimeError("boom")):
            res = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env)
        answer_ok(self, res, "error")
        self.assertIn("internal_error", [w["code"] for w in res["warnings"]])

    def test_polished_text_that_changes_a_fact_is_not_used(self):
        res = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env)
        sk = Path(res["workdir"], "skeleton.txt").read_text(encoding="utf-8")
        bad = sk + "\n11/30時点で見頃です。\n"                                   # 骨組みにない日付を足した
        res2 = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env, polished=bad)
        self.assertNotEqual(res2["stage"], 1)
        self.assertNotIn("11/30時点", res2["text"])


class Conditions(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(AR.resolve_dates("今日お出かけするならどこ?", NOW), ([[date(2026, 11, 8)]], False))
        self.assertEqual(AR.resolve_dates("明日は?", NOW), ([[date(2026, 11, 9)]], False))
        self.assertEqual(len(AR.resolve_dates("今週末と来週末のおすすめ", NOW)[0]), 2)
        self.assertEqual(AR.resolve_dates("11/15に桜", NOW), ([[date(2026, 11, 15)]], False))
        ds, defaulted = AR.resolve_dates("紅葉のおすすめ", NOW)
        self.assertTrue(defaulted)
        self.assertTrue(ds)

    def test_regions_and_origin(self):
        self.assertEqual(AR.resolve_region("今週末のおすすめを教えて。東京か神奈川で"), "東京か神奈川")
        self.assertEqual(AR.resolve_region("埼玉と神奈川で紅葉"), "埼玉か神奈川")
        self.assertEqual(AR.resolve_region("箱根の紅葉はどう?"), "箱根")
        self.assertIsNone(AR.resolve_region("今日お出かけするならどこ?"))
        self.assertIsNone(AR.resolve_region("東京から近場で"))                    # 出発地の語は地域にしない

    def test_routes(self):
        self.assertEqual(AR.resolve("冬桜について教えて", NOW)["route"], "knowledge")
        self.assertEqual(AR.resolve("神奈川で、野鳥や地形の観察会はある?", NOW)["route"], "event")
        self.assertEqual(AR.resolve("高山植物と見頃を教えて", NOW)["route"], "wildflower")
        self.assertEqual(AR.resolve("11/15に桜を見たい", NOW)["route"], "guide")
        c = AR.resolve("今日お出かけするならどこ?", NOW)
        self.assertEqual((c["route"], c["subjects"]), ("plan", ["autumn_leaves", "flowers", "birds"]))
        self.assertEqual(AR.resolve("箱根の紅葉はどう?", NOW)["subjects"], ["autumn_leaves"])
        self.assertEqual(AP.refine_rule(AR.resolve("大宮から近場で手軽に", NOW)["refine"])["aims"], ["near"])


class MinimalAnswer(unittest.TestCase):
    def test_minimal_answer_without_any_candidate(self):
        f = {"now": NOW.isoformat(), "dates": ["2026-11-08"], "subjects": {"autumn_leaves": {"candidates": []}}, "lines": {}}
        t = AR.minimal_answer(f, {"subject": "autumn_leaves", "picks": []})
        self.assertTrue(t.strip())
        self.assertNotIn(CANNOT, t)
        self.assertEqual(V.internal_word_errors(t), [])

    def test_the_old_one_line_refusal_is_gone_from_the_code(self):
        for f in list((ROOT / "ikimonobiyori").rglob("*.py")) + list((ROOT / "ikimonobiyori" / "data").rglob("*.yaml")):
            self.assertNotIn(CANNOT, f.read_text(encoding="utf-8"), str(f))

    def test_drop_picks_removes_names_everywhere(self):
        plan = {"picks": [{"name": "a"}, {"name": "b"}], "sections": [{"items": [{"name": "a"}]}],
                "segments": [{"plan": {"picks": [{"name": "a"}, {"name": "c"}]}}], "region_parts": [{"picks": ["a", "b"]}]}
        got = AR.drop_picks(plan, {"a"})
        self.assertEqual([p["name"] for p in got["picks"]], ["b"])
        self.assertEqual(got["sections"][0]["items"], [])
        self.assertEqual([p["name"] for p in got["segments"][0]["plan"]["picks"]], ["c"])
        self.assertEqual(got["region_parts"][0]["picks"], ["b"])
        self.assertEqual([p["name"] for p in plan["picks"]], ["a", "b"])        # 元の計画は変えない


def spot(name, km=20, state="見頃", date_="2026-11-07", city="試験町", subject="autumn_leaves", **kw):
    cur = {"state": state, "state_raw": state, "display": state, "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{name}",
           "source_class": "official", "freshness": "fresh", "age_days": 1, "read_at": "2026-11-07T09:00:00+09:00"} if state else None
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": "神奈川県", "current": cur, "current_unknown": cur is None, "distance_km": km,
            "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak",
            "subject": subject, **kw}


def facts_doc(subjects, dates=("2026-11-08",)):
    return {"schema": "ikimono-ask-facts/1", "now": NOW.isoformat(), "dates": list(dates), "origin": "横浜", "region": "全範囲", "subjects": subjects,
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": "横浜からの距離で選びました。"},
            "summary_pages": [], "this_round": {}}


def subj(sj, *cands):
    return {"subject": sj, "candidates": list(cands), "avoid": [], "nearby_out_of_region": [], "alternatives": []}


class FourGates(unittest.TestCase):
    """第2部: 必須の検査は 4 つ。品質・表現は自動修正か警告。"""

    def test_every_check_id_in_the_code_is_classified(self):
        from ikimonobiyori import answer_gates as AG
        c = AG.contract()
        known = {x for g in AG.GATES for x in c["gates"][g]["codes"]} | set(c["warn"]["codes"]) | {x for k in ("delete_sentence", "rebuild_sources", "reduce_candidates")
                                                                                                    for x in c["autofix"][k]}
        found = set()
        for f in ("ask_verify", "answer_plan", "polish", "intent", "knowledge", "jma_normals", "facility_events"):
            found |= set(re.findall(r'"code":\s*"([a-z_]+)"', (ROOT / "ikimonobiyori" / f"{f}.py").read_text(encoding="utf-8")))
        found |= {"no_typical_in_candidate", "process_phrase"}                     # 条件式で作る ID
        found -= {"no_this_year", "out_of_range"}                                  # 計画の不採用の理由(検査ではない)
        self.assertEqual(sorted(found - known), [])

    def test_warnings_do_not_block(self):
        from ikimonobiyori import answer_gates as AG
        for code in ("too_few_candidates", "fetch_skipped", "practical_missing", "plan_pick_missing", "repeated_phrase"):
            self.assertEqual(AG.gate_of(code), "warn", code)
        for code, g in (("unknown_date", "fact"), ("closed_not_stated", "safety"), ("lead_mismatch", "consistency"), ("question_in_answer", "output")):
            self.assertEqual(AG.gate_of(code), g)
        self.assertEqual(AG.gate_of("a_new_check_nobody_classified"), "fact")       # 分類のない ID は事実の検査(緩めない)

    def test_sources_follow_the_same_map_as_the_checker(self):
        """衝突1: 「今年の情報が確認できていない候補」の欄に名前だけ出た候補の現況のページを、出典に載せない。"""
        from ikimonobiyori import skeleton as SK
        a, b = spot("試験の谷"), spot("試験の丘")
        b["current"]["url"] = "https://intro.example.org/oka"
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", a, b), "birds": subj("birds", spot("鳥の沼", subject="birds"))})
        plan = AP.build_all(f)
        plan["no_this_year"] = [{"name": "試験の丘", "typical_line": "例年の見頃: 11月"}]
        for s in plan.get("subjects", {}).values():
            s["picks"] = [p for p in s["picks"] if p["name"] != "試験の丘"]
        plan["picks"] = [p for p in plan["picks"] if p["name"] != "試験の丘"]
        text = SK.compose(f, plan)
        self.assertIn("試験の丘", text)
        self.assertNotIn("https://intro.example.org/oka", text)
        codes = [e["code"] for e in V.check(text, f, plan=plan)["answer_errors"]]
        self.assertNotIn("source_unused", codes)
        self.assertNotIn("source_missing", codes)

    def test_rebuild_sources_adds_missing_and_removes_unused(self):
        from ikimonobiyori import answer_gates as AG
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷"))})
        plan = AP.build(f, "autumn_leaves")
        text = "見頃です。\n今回のおすすめ\n① 試験の谷: 今の状況は見頃(11/7時点、試験市)。例年の見頃: 11月。\n\n出典\nhttps://unused.example.org/x\n"
        fixed, how = AG.rebuild_sources(text, f, plan)
        self.assertIn("https://kouyou.example.org/試験の谷", fixed)
        self.assertNotIn("unused.example.org", fixed)
        codes = [e["code"] for e in V.check(fixed, f, plan=plan)["answer_errors"]]
        self.assertNotIn("source_unused", codes)
        self.assertNotIn("source_missing", codes)

    def test_notice_line_with_a_festival_word_is_not_a_mix(self):
        """衝突2: 「行く前に確認すること」のお知らせの行(○/○時点の公式のお知らせ)は、まつりと現況を混ぜた行として数えない。"""
        c = spot("試験の花園", subject="flowers", festivals=[{"name": "コスモスまつり", "url": "https://kouyou.example.org/f", "period_line": "主催者が設定した期間: まつり期間中(11/1〜11/30)"}])
        f = facts_doc({"flowers": subj("flowers", c)})
        text = ("① 試験の花園: 今の状況は見頃(11/7時点、試験市)。例年の見頃: 11月。\n\n行く前に確認すること\n"
                "試験の花園: コスモスまつり期間中の無料バスを運行(11/6時点の公式のお知らせ)\n")
        self.assertNotIn("festival_mixed_with_state", [e["code"] for e in V.check(text, f)["answer_errors"]])
        bad = "① 試験の花園: 主催者が設定した期間: まつり期間中(11/1〜11/30)で、11/7時点で見頃です。\n"
        self.assertIn("festival_mixed_with_state", [e["code"] for e in V.check(bad, f)["answer_errors"]])

    def test_birds_festival_candidate_without_state_has_no_koyo_word(self):
        """衝突7: 野鳥の候補に「色づき状況」と書かない。「今年の状況は確認できていません」で未確認を示せる。"""
        from ikimonobiyori import skeleton as SK
        c = spot("鳥の森", state=None, subject="birds", festivals=[{"name": "森の行事", "url": "https://kouyou.example.org/m", "period_line": "主催者が設定した期間: あと3日で開始(11/11〜11/12)"}])
        line = SK.current_line(c, AP.load_policy()["skeleton"], {}, None, "birds")
        self.assertNotIn("色づき", line)
        f = facts_doc({"birds": subj("birds", c)})
        text = f"① 鳥の森: {line}。\n"
        self.assertNotIn("festival_no_state_missing", [e["code"] for e in V.check(text, f)["answer_errors"]])

    def test_autofix_deletes_internal_and_question_sentences(self):
        from ikimonobiyori import answer_gates as AG
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷"))})
        plan = AP.build(f, "autumn_leaves")
        text = ("見頃に向かう可能性があります。骨組みの文を出し直します。\n今回のおすすめ\n① 試験の谷: 今の状況は見頃(11/7時点、試験市)。例年の見頃: 11月。\n"
                "どちらにしますか?\n")
        fixed, how = AG.delete_bad_sentences(text, f, plan)
        self.assertNotIn("骨組み", fixed)
        self.assertNotIn("どちらにしますか", fixed)
        self.assertIn("① 試験の谷", fixed)
        self.assertEqual(len(how), 2)

    def test_length_limit_grows_with_segments_and_regions(self):
        from ikimonobiyori import answer_gates as AG
        L = AG.contract()["length"]
        self.assertEqual(AG.length_limit({"segments": []}), L["base"])
        self.assertEqual(AG.length_limit({"segments": [{}, {}, {}]}), L["base"] + 2 * L["per_segment"])
        self.assertEqual(AG.length_limit({"segments": [], "region_parts": [{}, {}]}), L["base"] + L["per_region"])

    def test_too_long_is_not_a_gate(self):
        from ikimonobiyori import answer_gates as AG
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷"))})
        plan = AP.build(f, "autumn_leaves")
        from ikimonobiyori import skeleton as SK
        text = SK.compose(f, plan) + ("補足の文です。" * 400) + "\n"
        ev = AG.evaluate(text, f, plan)
        self.assertNotIn("too_long", [e["code"] for g in AG.GATES for e in ev["gates"][g]])
        self.assertIn("too_long", [e["code"] for e in ev["warnings"]])

    def test_lead_does_not_confuse_spots_with_a_shared_area_name(self):
        a, b = spot("箱根(芦ノ湖)"), spot("箱根 仙石原(長安寺)")
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", a, b)})
        plan = AP.build(f, "autumn_leaves")
        plan["picks"] = [p for p in plan["picks"] if p["name"] == "箱根 仙石原(長安寺)"]
        text = "箱根 仙石原(長安寺)は見頃の可能性があります。\n今回のおすすめ\n① 箱根 仙石原(長安寺): 今の状況は見頃(11/7時点、試験市)。例年の見頃: 11月。\n"
        details = [e["detail"] for e in V.check(text, f, plan=plan)["answer_errors"] if e["code"] == "lead_mismatch"]
        self.assertFalse(any("芦ノ湖" in d for d in details), details)



NL = "\n"


class Localize(unittest.TestCase):
    """第3部: 問題は候補(場所)ごと・主張(文)ごとに外し、ほかは残す。"""

    def setUp(self):
        from ikimonobiyori import skeleton as SK
        self.SK = SK
        self.f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷", 10, city="試験町"), spot("試験の滝", 60, city="滝村"),
                                                  spot("試験の湖", 150, city="湖市"))})
        self.plan = AP.build(self.f, "autumn_leaves")
        self.names = [p["name"] for p in self.plan["picks"]]
        self.assertGreaterEqual(len(self.names), 2)

    def broken(self, name, extra):
        text = self.SK.compose(self.f, self.plan)
        return NL.join(l + extra if l.startswith(("①", "②", "③")) and name in l else l for l in text.splitlines()) + NL

    def test_one_candidate_with_a_wrong_fact_is_removed_and_the_rest_kept(self):
        bad = self.names[1]
        g = AR.gate_check(self.broken(bad, "11/30時点で見頃です。"), self.f, self.plan, ())
        self.assertFalse(g["ok"])
        got = AR.partial_answer(self.f, self.plan, g, [], False, ())
        self.assertIsNotNone(got)
        self.assertEqual(got["status"], AR.STATUS_DEGRADED)
        self.assertEqual(got["removed"], [bad])
        self.assertNotIn(bad, got["text"].split("出典")[0])
        for n in self.names:
            if n != bad:
                self.assertIn(n, got["text"])

    def test_dangerous_claim_is_removed_and_marked_blocked(self):
        bad = self.names[0]
        phrase = V.load_rules()["stage51"]["assertive_phrases"][0]               # 見込みを言い切る(不確かなことの断定)
        g = AR.gate_check(self.broken(bad, f"今週末は{phrase}。"), self.f, self.plan, ())
        self.assertIn("safety", {e["gate"] for e in g["errors"]})
        got = AR.partial_answer(self.f, self.plan, g, [], False, ())
        self.assertEqual(got["status"], AR.STATUS_BLOCKED)
        self.assertIn(bad, got["removed"])

    def test_all_candidates_bad_gives_none_then_minimal(self):
        g = {"ok": False, "text": self.SK.compose(self.f, self.plan), "errors": [{"code": "unknown_date", "gate": "fact", "detail": n} for n in self.names]}
        self.assertIsNone(AR.partial_answer(self.f, self.plan, g, [], False, ()))
        t = AR.minimal_answer(self.f, self.plan)
        self.assertTrue(t.strip())

    def test_a_wrong_sentence_outside_the_candidates_is_removed_alone(self):
        text = self.SK.compose(self.f, self.plan).replace(NL + "出典", NL + "この谷の標高は1234mです。" + NL + NL + "出典", 1)
        g = AR.gate_check(text, self.f, self.plan, ())
        self.assertFalse(g["ok"])
        got = AR.partial_answer(self.f, self.plan, g, [], False, ())
        self.assertIsNotNone(got)
        self.assertNotIn("1234", got["text"])
        self.assertEqual(got["removed"], [])
        self.assertTrue(got["removed_lines"])

    def test_record_and_now_visible_are_different_claims(self):
        def codes(text, f):
            return [e["code"] for s in V.check(text + NL, f)["sentences"] for e in s["errors"]]
        old = spot("鳥の沼", subject="birds")
        old["current"]["freshness"] = "stale"
        f = facts_doc({"birds": subj("birds", old)})
        self.assertIn("now_visible_unsupported", codes("鳥の沼では今もカモが見られます。", f))
        self.assertNotIn("now_visible_unsupported", codes("鳥の沼では、この時期にカモの観察の記録があります。", f))
        fresh = facts_doc({"birds": subj("birds", spot("鳥の沼", subject="birds"))})
        self.assertNotIn("now_visible_unsupported", codes("鳥の沼では今もカモが見られます。", fresh))


class PolishedMatch(unittest.TestCase):
    """第4部: 骨組みの事実を構造化して持ち、整えた文章と照合する。食い違ったら骨組みが正しい。整えてよいのは冒頭の文とガイドの目だけ。"""

    def setUp(self):
        from ikimonobiyori import polish as PL, skeleton as SK
        self.PL = PL
        self.f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷", 10, city="試験町"), spot("試験の滝", 60, city="滝村"))})
        self.plan = AP.build(self.f, "autumn_leaves")
        self.sk = SK.compose(self.f, self.plan)
        self.names = ask.polish_names(self.f)

    def test_skeleton_facts_are_structured(self):
        rows = self.PL.skeleton_facts(self.sk, self.names)
        cand = [r for r in rows if r["text"].startswith("①")]
        self.assertTrue(cand and cand[0]["fixed"])
        self.assertIn("date", cand[0]["facts"])
        self.assertIn("name", cand[0]["facts"])
        lead = rows[0]
        self.assertFalse(lead["fixed"])                                      # 冒頭の決まり文は整えてよい

    def test_rewording_the_lead_is_fine(self):
        lines = self.sk.splitlines()
        lines[0] = "今週末は、色づきの様子を確かめながら出かけられそうです。"
        self.assertEqual(self.PL.fixed_line_errors(self.sk, NL.join(lines) + NL, self.names), [])

    def test_changing_a_fact_line_is_caught_and_the_skeleton_wins(self):
        bad = self.sk.replace("11/7時点", "11/6時点", 1)
        r = self.PL.check_structured(self.sk, bad, self.names)
        self.assertFalse(r["ok"])
        self.assertIn("polish_fixed_line_changed", [e["code"] for e in r["errors"]])

    def test_dropping_a_candidate_line_is_caught(self):
        bad = NL.join(l for l in self.sk.splitlines() if not l.startswith("②")) + NL
        self.assertTrue(self.PL.fixed_line_errors(self.sk, bad, self.names))

    def test_polished_answer_with_a_changed_fact_falls_back_to_the_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            with unittest.mock.patch.dict("os.environ", env):
                res = AR.run("今日お出かけするならどこ?", now=NOW, env=env)
                sk = Path(res["workdir"], "skeleton.txt").read_text(encoding="utf-8")
                facts = json.loads(Path(res["workdir"], "skeleton_facts.json").read_text(encoding="utf-8"))
                self.assertTrue(any(r["fixed"] for r in facts))
                changed = sk.replace("今回のおすすめ", "今回のおすすめ!", 1)
                res2 = AR.run("今日お出かけするならどこ?", now=NOW, env=env, polished=changed)
                self.assertNotEqual(res2["stage"], 1)
                self.assertNotIn("今回のおすすめ!", res2["text"])
                same = sk
                res3 = AR.run("今日お出かけするならどこ?", now=NOW, env=env, polished=same)
                self.assertIn(res3["stage"], (1, 2, 3, 4))


if __name__ == "__main__":
    unittest.main()
