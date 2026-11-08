"""段階62 第1部: 内部用語・作業の事情を答えに出さない(ask_verify.internal_word_errors)・範囲の限界を利用者の語で書く・
利用者向けの情報源の一覧(source_list・`ask sources`)。通信なし・合成データ。"""
import contextlib
import io
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask
from ikimonobiyori import ask_verify as V
from ikimonobiyori import intent
from ikimonobiyori import source_list as SL

import test_event_verify as EV

TODAY = date(2026, 11, 8)


def codes(errs):
    return {e["code"] for e in errs}


class InternalWords(unittest.TestCase):
    BAD = [
        "横浜自然観察の森は、まだ台帳に入っていません。",
        "承認済みの施設の行事だけを出しています。",
        "この施設は承認待ちです。",
        "行事用の検査を通しています。",
        "通常の検査は「候補が3件未満」で不合格でしたが、行事用の検査の結果を採りました。",
        "骨組みのとおりに書きました。",
        "答えの計画どおりに選びました。",
        "記録を読んだ範囲では、見頃です。",
        "ask plan で選びました。",
        "この答えは決まりで省いています。",
        "この答えは行事の照合を通しています。",
        "データ置き場の記録です。",
    ]
    GOOD = [
        "ほかの施設の観察会は、確認できていません。",
        "確認できている公式ページの範囲では、今日の観察会は見つかりませんでした。",
        "11/6時点の観察の記録では、ジョウビタキの名があります。",
        "一年を通して見られる鳥です。",
        "尾瀬を守った計画の中止の歴史があります。",
        "植物(plant)の名前です。",
    ]

    def test_bad_sentences_fail(self):
        for s in self.BAD:
            with self.subTest(s=s):
                self.assertIn("internal_word", codes(V.internal_word_errors(s)))

    def test_good_sentences_pass(self):
        for s in self.GOOD:
            with self.subTest(s=s):
                self.assertEqual(V.internal_word_errors(s), [])

    def test_source_section_and_urls_are_not_counted(self):
        text = "試験の森の観察会があります。\n\n出典\n試験県 公園の計画のページ\nhttps://example.org/plan/verify.html\n"
        self.assertEqual(V.internal_word_errors(text), [])
        self.assertIn("internal_word", codes(V.internal_word_errors("台帳の記載です。\n出典\nhttps://example.org/\n")))

    def test_generic_and_event_checks_fail_on_internal_words(self):
        good = EV.answer()
        self.assertEqual(intent.check_event(good, TODAY, EV.ledger()), [])
        bad = good.replace("ほかの施設の観察会は、確認できていません。", "ほかの施設は、まだ台帳に入っていません。")
        self.assertIn("internal_word", codes(intent.check_event(bad, TODAY, EV.ledger())))
        gen = "①試験の森\n②試験の湖\n③試験の谷\n行事用の検査を通しています。\n"
        self.assertIn("internal_word", codes(V.generic_check(gen)["errors"]))


class ScopeLimitLines(unittest.TestCase):
    def test_event_answer_has_user_scope_line(self):
        text = EV.answer()
        self.assertIn("ほかの施設の観察会は、確認できていません。", text)
        self.assertEqual(V.internal_word_errors(text), [])

    def test_no_event_line_uses_user_words(self):
        line = intent.event_none_line("今週末の観察会はある?")
        self.assertEqual(line, "確認できている公式ページの範囲では、今週末の観察会・行事は見つかりませんでした。")
        self.assertEqual(V.internal_word_errors(line), [])
        self.assertIn("これから", intent.event_none_line("観察会はある?"))

    def test_policy_lines_have_no_internal_words(self):
        for k, v in V.load_rules()["scope_limit_lines"].items():
            with self.subTest(k=k):
                self.assertEqual(V.internal_word_errors(v.format(name="試験の森", when="今日")), [])


def fake_inputs():
    centers = [{"id": "a", "name": "試験ビジターセンター", "approval": {"status": "approved"}},
               {"id": "b", "name": "試験自然館", "approval": {"status": "pending"}}]
    events = {"facilities": [{"id": "m", "name": "試験博物館", "approval": {"status": "approved"}}], "events": []}
    cards = [{"title": "x"}, {"title": "y"}]
    normals = {"entries": [{"station": "東京"}, {"station": "横浜"}, {"station": "東京"}]}
    return dict(centers=centers, events=events, cards=cards, normals=normals)


class SourceList(unittest.TestCase):
    def test_kinds_counts_and_no_internal_words(self):
        text = SL.text(**fake_inputs())
        self.assertIn("施設の発信(ビジターセンターなど): 1か所(試験ビジターセンター)", text)
        self.assertIn("行事・観察会の公式ページ: 1か所(試験博物館)", text)
        self.assertIn("ネイチャーガイドの知識(出典つきの短いまとめ): 2枚", text)
        self.assertIn("気象庁の平年の目安(標本木などの観測): 3項目(2地点)", text)
        self.assertIn("今の様子を読む公式ページ(紅葉)", text)
        self.assertNotIn("確認している", text)                          # 確認中の件数は聞かれたときだけ
        self.assertEqual(V.internal_word_errors(text), [])
        self.assertEqual(V.term_errors(text), [])

    def test_review_counts_only_when_asked_and_in_user_words(self):
        text = SL.text(with_review=True, **fake_inputs())
        self.assertIn("使ってよいか確認している情報源", text)
        self.assertIn("- 施設の発信(ビジターセンターなど): 1か所", text.split("確認している情報源")[1])
        self.assertNotIn("承認", text)
        self.assertEqual(V.internal_word_errors(text), [])

    def test_explanations_use_user_words(self):
        for w in ("台帳ってなに?", "承認って?"):
            with self.subTest(w=w):
                t = SL.explain(w)
                self.assertNotIn("台帳", t)
                self.assertNotIn("承認済み", t)
                self.assertEqual(V.internal_word_errors(t), [])
        self.assertIn("公式ページ", SL.explain("台帳"))

    def test_cli_sources(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ask.main(["sources"])
        self.assertEqual(rc, 0)
        self.assertIn("イキモノビヨリが答えに使っている情報源です。", buf.getvalue())
        self.assertEqual(V.internal_word_errors(buf.getvalue()), [])


if __name__ == "__main__":
    unittest.main()
