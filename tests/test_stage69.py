"""段階69: 最終メッセージの検査・質問の振り分け・記録がないときの調べ・データの汚れ。合成データ(通信しない)。"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 9, 21, 0, tzinfo=JST)

ANSWER = """**2026年11月14日(土)の紅葉**

今回のおすすめ
① 試験の渓谷 約40km
・今の状況は色づき始め(11/6時点、試験町)

写真つきのページにもできます。

出典
https://example.org/a
"""

ZERO = """この条件で今年の情報が確認できた候補はありません。
対象の日は11/14・11/15です。

この地域で今年の情報が確認できた候補は0件です。

ここまでの候補は表にして比べられます。
"""


class Part1FinalCheck(unittest.TestCase):
    """第1部: 最終メッセージの検査。11/9 の会話の実際の文を入力にして、消えることを確かめる。"""

    def setUp(self):
        from ikimonobiyori import final_check as FC
        self.FC = FC
        self.dir = tempfile.mkdtemp()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.dir}

    def check(self, msg, answer=ANSWER):
        return self.FC.check(msg, answer)

    def test_work_notes_around_the_answer_are_removed(self):
        msg = ("この出力は答えとして出しません。関東全体の一覧が返ったので、高尾山の部分を手で抜き出しました。\n\n" + ANSWER +
               "\n作業メモ(答えの外)\n・小田原フラワーガーデンの記録は event の書式のエラーで保存できませんでした\n・読むページが新たに3件出ました\n\n"
               "やり直しは1回までの決まりなので、ここで止めます。\n")
        r = self.check(msg)
        for w in ("この出力は答えとして出しません", "作業メモ", "event の書式", "読むページが新たに", "やり直しは1回まで", "手で抜き出し"):
            self.assertNotIn(w, r["text"], w)
        self.assertIn("試験の渓谷", r["text"])
        self.assertIn("https://example.org/a", r["text"])
        self.assertIn("写真つきのページにもできます。", r["text"])          # コードが条件を満たして出した案内は残す
        self.assertTrue(r["removed"])

    def test_offers_and_questions_added_by_the_agent_are_removed(self):
        for extra in ("答え直すこともできます。", "どちらでも進められます。", "公式ページを読んで記録しましょうか。", "やりますか。",
                      "ご希望なら、写真つきのページも作ります。", "ほかの地域も調べますか？", "調べることもできます。"):
            r = self.check(ANSWER + "\n" + extra + "\n")
            self.assertNotIn(extra.rstrip("。？"), r["text"], extra)
            self.assertIn("試験の渓谷", r["text"])

    def test_refusal_and_record_words_are_removed(self):
        msg = "記録にないため、お答えできません。\n記録にある内容では書けません。\n状態: DEGRADED(段 4)\n検査の結果、1行を外しました。\nCLAUDE.md の決まりにより書きません。\n" + ANSWER
        r = self.check(msg)
        for w in ("記録にないため", "記録にある内容では書けません", "DEGRADED", "検査の結果", "CLAUDE.md"):
            self.assertNotIn(w, r["text"], w)
        self.assertIn("試験の渓谷", r["text"])

    def test_zero_candidate_answer_has_no_table_or_page_offer(self):
        r = self.check(ZERO, ZERO)
        self.assertNotIn("表にして比べられます", r["text"])
        self.assertIn("候補は0件", r["text"])

    def test_empty_after_removal_returns_the_answer_as_is(self):
        r = self.check("作業メモ(答えの外)\n・ask record が失敗\n", ANSWER)
        self.assertTrue(r["fallback"])
        self.assertEqual(r["text"].strip(), ANSWER.strip())

    def test_removed_sentences_are_logged_not_shown(self):
        old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.dir
        try:
            self.FC.remember_answer(ANSWER, "今週末の紅葉", NOW)
            r = self.FC.run(ANSWER + "\nやりますか。\n", now=NOW + timedelta(minutes=1))
            self.assertNotIn("やりますか", r["text"])
            rows = [json.loads(l) for l in Path(self.dir, "logs", "answers.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[-1]["kind"], "final_check")
            self.assertIn("やりますか。", rows[-1]["removed"])
            from ikimonobiyori import answer_run as AR
            self.assertIn("記録がまだありません", AR.report(AR.read_log()))      # 検査の記録は答えの数に入れない
        finally:
            if old is None:
                os.environ.pop("IKIMONOBIYORI_DATA_DIR", None)
            else:
                os.environ["IKIMONOBIYORI_DATA_DIR"] = old

    def test_cli_reads_stdin_and_prints_only_the_allowed_text(self):
        d = tempfile.mkdtemp()
        Path(d, "a.txt").write_text(ANSWER, encoding="utf-8")
        Path(d, "m.txt").write_text(ANSWER + "\nどちらでも進められます。\n", encoding="utf-8")
        import sys
        out = H.run_child([sys.executable, "-X", "utf8", "-m", "ikimonobiyori.ask", "final-check", "--text", str(Path(d, "m.txt")),
                           "--answer", str(Path(d, "a.txt"))], capture_output=True, text=True, encoding="utf-8",
                          cwd=str(Path(__file__).resolve().parents[1]))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("進められます", out.stdout)
        self.assertIn("試験の渓谷", out.stdout)

    def test_skill_says_to_send_final_check_output_verbatim(self):
        root = Path(__file__).resolve().parents[1]
        s = (root / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ask final-check", s)
        self.assertIn("一字一句そのまま", s)


if __name__ == "__main__":
    unittest.main()
