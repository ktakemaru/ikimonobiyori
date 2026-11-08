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
        with unittest.mock.patch.object(AR, "gate_check", lambda *a, **k: {"ok": False, "errors": [{"code": "x", "detail": "x"}], "warnings": []}):
            res = AR.run("今日お出かけするならどこ?", now=NOW, env=self.env)
        self.assertEqual(res["stage"], 4)
        self.assertEqual(res["status"], AR.STATUS_DEGRADED)
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


if __name__ == "__main__":
    unittest.main()
