"""段階72 第1部: 送る前の検査を Stop フックで強制する。合成の応答の文と合成の会話の記録で、止める/通すを確かめる(通信しない)。"""
import io
import json
import os  # noqa: F401
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import stop_hook as SH

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)

ANSWER = """**2026年11月14日(土)の紅葉**

今回のおすすめ
① 試験の渓谷 約40km
・今の状況は色づき始め(11/6時点、試験町)

出典
https://example.org/a
"""


def prompt(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


_N = [0]


def call(name, inp, result=""):
    _N[0] += 1
    tid = f"t{_N[0]}"
    return [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": result}]}}]


def bash(cmd, result=""):
    return call("Bash", {"command": cmd}, result)


ASK = 'python -X utf8 -m ikimonobiyori.ask answer --question "今週末の紅葉は?"'
FINAL = "python -X utf8 -m ikimonobiyori.ask final-check --text a.txt"


def transcript(*parts):
    rows = []
    for p in parts:
        rows.extend(p if isinstance(p, list) else [p])
    return [json.dumps(r, ensure_ascii=False) + "\n" for r in rows]


class Decide(unittest.TestCase):
    def d(self, lines, msg, answer=ANSWER):
        turn = SH.read_turn(lines)
        return SH.decide({"last_assistant_message": msg}, turn, answer)

    def test_clean_answer_after_final_check_passes(self):
        lines = transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER + "状態: PASS"), bash(FINAL, ANSWER))
        self.assertFalse(self.d(lines, ANSWER)["block"])

    def test_question_to_user_blocks(self):
        lines = transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER), bash(FINAL, ANSWER))
        for tail in ("公式ページを調べますか?", "3件とも読んでよければ、やりますか。", "探して、記録することもできます。", "今は答えを用意できていません。"):
            d = self.d(lines, ANSWER + "\n" + tail)
            self.assertTrue(d["block"], tail)
            self.assertIn("利用者に聞かずに", " ".join(d["reasons"]))

    def test_research_targets_not_followed_blocks(self):
        res = ANSWER + '調べる: [{"what": "ホタル", "where": "あきる野市"}]'
        lines = transcript(prompt("あきる野市でホタルが見られるところと時期は?"), bash(ASK, res), bash(FINAL, ANSWER))
        d = self.d(lines, ANSWER)
        self.assertTrue(d["block"])
        self.assertIn("公式ページを探して読み", " ".join(d["reasons"]))
        self.assertIn("ask answer を 1 回だけ呼び直して", " ".join(d["reasons"]))

    def test_research_done_passes(self):
        res = ANSWER + '調べる: [{"what": "ホタル"}]'
        lines = transcript(prompt("あきる野市でホタルが見られるところと時期は?"), bash(ASK, res), call("WebSearch", {"query": "あきる野 ホタル 公式"}),
                           bash("python -X utf8 -m ikimonobiyori.ask record --batch reads.json"), bash(ASK, ANSWER), bash(FINAL, ANSWER))
        self.assertFalse(self.d(lines, ANSWER)["block"])

    def test_second_answer_with_targets_is_accepted(self):       # 調べたあとの 2 回目にまだ対象が残っても、やり直しは 1 回まで
        res = ANSWER + '調べる: [{"what": "ホタル"}]'
        lines = transcript(prompt("ホタルは?"), bash(ASK, res), bash(ASK, res), bash(FINAL, ANSWER))
        self.assertFalse(self.d(lines, ANSWER)["block"])

    def test_missing_final_check_blocks(self):
        lines = transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER))
        d = self.d(lines, ANSWER)
        self.assertTrue(d["block"])
        self.assertIn("ask final-check", " ".join(d["reasons"]))

    def test_no_tool_ikimono_answer_blocks(self):
        lines = transcript(prompt("今週末の紅葉のおすすめは?"))
        d = self.d(lines, "高尾山がおすすめです。")
        self.assertTrue(d["block"])
        self.assertIn("ask answer", d["reasons"][0])

    def test_exception_without_ikimonobiyori(self):
        lines = transcript(prompt("イキモノビヨリを使わずに、紅葉の名所を教えて"))
        d = self.d(lines, "イキモノビヨリの記録は使っていません。高尾山などがあります。調べますか?")
        self.assertFalse(d["block"])
        self.assertEqual(d["why"], "skip_word")

    def test_exception_mechanism_question(self):
        lines = transcript(prompt("台帳ってなに?"), bash(ASK, ANSWER))
        d = self.d(lines, "台帳は情報源の一覧です。ask answer が読みます。")
        self.assertFalse(d["block"])
        self.assertEqual(d["why"], "mechanism")

    def test_development_turn_is_not_checked(self):
        lines = transcript(prompt("ファイルを整理して"), bash("git status"))
        self.assertFalse(self.d(lines, "整理しました。続けますか?")["block"])

    def test_turn_starts_at_last_prompt_and_skips_hook_feedback(self):
        lines = transcript(prompt("前の質問"), bash(ASK, ANSWER + '調べる: [{"what": "x"}]'),
                           prompt("今週末の紅葉は?"), bash(ASK, ANSWER), bash(FINAL, ANSWER),
                           prompt(SH.cfg()["reason_marker"] + " 最終メッセージを ask final-check に通してください。"))
        turn = SH.read_turn(lines)
        self.assertEqual(turn["prompt"], "今週末の紅葉は?")
        self.assertEqual(len(turn["calls"]), 2)
        self.assertFalse(SH.decide({"last_assistant_message": ANSWER}, turn, ANSWER)["block"])


class RunAndLimit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.tp = Path(self.tmp.name) / "t.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, lines):
        self.tp.write_text("".join(lines), encoding="utf-8")

    def test_blocks_at_most_twice_per_turn(self):
        self.write(transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER), bash(FINAL, ANSWER)))
        payload = {"session_id": "s1", "transcript_path": str(self.tp), "last_assistant_message": ANSWER + "\n調べますか?"}
        outs = [SH.run(dict(payload, stop_hook_active=i > 0), env=self.env, now=NOW) for i in range(4)]
        self.assertEqual([o is not None for o in outs], [True, True, False, False])
        self.assertEqual(outs[0]["decision"], "block")
        self.assertTrue(outs[0]["reason"].startswith(SH.cfg()["reason_marker"]))

    def test_new_prompt_resets_the_count(self):
        self.write(transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER)))
        p = {"session_id": "s1", "transcript_path": str(self.tp), "last_assistant_message": ANSWER}
        SH.run(p, env=self.env, now=NOW), SH.run(p, env=self.env, now=NOW)
        self.assertIsNone(SH.run(p, env=self.env, now=NOW))
        self.write(transcript(prompt("今週末の野鳥は?"), bash(ASK, ANSWER)))
        self.assertIsNotNone(SH.run(p, env=self.env, now=NOW))

    def test_unreadable_transcript_passes(self):
        p = {"session_id": "s", "transcript_path": str(Path(self.tmp.name) / "none.jsonl"), "last_assistant_message": "調べますか?"}
        self.assertIsNone(SH.run(p, env=self.env, now=NOW))

    def test_main_never_fails(self):
        for raw in (b"", b"not json", b"[1,2]", json.dumps({"transcript_path": 3}).encode()):
            stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
            out = io.StringIO()
            self.assertEqual(SH.main(stdin, out), 0)
            self.assertEqual(out.getvalue(), "")

    def test_hook_script_blocks_via_child_process(self):
        self.write(transcript(prompt("今週末の紅葉は?"), bash(ASK, ANSWER), bash(FINAL, ANSWER)))
        payload = json.dumps({"session_id": "c1", "transcript_path": str(self.tp), "last_assistant_message": ANSWER + "\nやりますか。"}, ensure_ascii=False)
        cmd = [sys.executable, "-X", "utf8", str(ROOT / ".claude" / "hooks" / "stop_check.py")]
        kw = dict(capture_output=True, text=True, encoding="utf-8")
        r = H.run_child_env(cmd, self.env, input=payload, **kw)
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertEqual(out["decision"], "block")
        r2 = H.run_child_env(cmd, self.env, input="{broken", **kw)
        self.assertEqual((r2.returncode, r2.stdout.strip()), (0, ""))


class Settings(unittest.TestCase):
    def test_project_settings_register_the_stop_hook(self):
        s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hooks = s["hooks"]["Stop"][0]["hooks"]
        self.assertTrue(any("stop_check.py" in h["command"] and "-X utf8" in h["command"] for h in hooks))
        self.assertNotIn("matcher", s["hooks"]["Stop"][0])

    def test_skill_size_limit(self):
        p = ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md"
        self.assertLessEqual(len(p.read_bytes()), 15000)


if __name__ == "__main__":
    unittest.main()
