"""段階81 の続き(本人が Sonnet で写真つきページを試した結果 2026-11-12 からの直し)。合成データ(通信しない)。
1. ページを頼まれたときの最後の文は、決まった短い案内とページのリンク(ask page-reply)。合格した答えからページを作ったときだけ受け入れる
2. ページの見出し・箇条を Markdown として読む(「##」を文字のまま出さない)
4. 写真を、種の名前が出る段落のそばに置く(どの段落にもない種はまとめて本文の前)
5. ページの題は資料から決める(質問の文そのままにしない)"""
import json
import tempfile
import unittest
from datetime import datetime

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_page as APG
from ikimonobiyori import guide_answer_page as GAP
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import final_check as FC
from ikimonobiyori import stop_hook as SH

NOW = datetime.fromisoformat("2026-11-12T10:00:00+09:00")
TEXT = ("今週末の試験山は、紅葉が見どころです。\n\n## 試験の谷で\n谷ではカワヅザクラの並木が見られます。\n\n"
        "## 注意\n- **試験の道**は一方通行です。\n\n出典\n・試験町観光協会 https://example.org/a")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, text=TEXT, question="今週末、試験山の見どころを教えて", bid="b20261112-test0002", saved="2026-11-12T09:00:00+09:00",
             cands=None, subjects=None):
        p = GV.last_guide_path(self.env)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"saved_at": saved, "brief": bid, "question": question, "text": text}, ensure_ascii=False), encoding="utf-8")
        d = GB.brief_dir(self.env)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{bid}.json").write_text(json.dumps({"id": bid, "question": question, "subjects": subjects or ["autumn_leaves"],
                                                   "candidates": cands if cands is not None else [{"name": "試験山"}]}, ensure_ascii=False), encoding="utf-8")
        return GAP.newest(NOW, self.env)


class Markdown(Base):
    def test_headings_and_lists_are_rendered(self):
        from pathlib import Path
        r = GAP.make(self.save(), NOW, self.env, fetch=False)
        html = Path(r["path"]).read_text(encoding="utf-8")
        self.assertIn("<h2>試験の谷で</h2>", html)
        self.assertNotIn("##", html)
        self.assertNotIn("**", html)
        self.assertIn("<li><strong>試験の道</strong>は一方通行です。</li>", html)     # 太字は太字で表示(本人の判断 2026-11-12)
        self.assertIn('<a href="https://example.org/a"', html)

    def test_blocks(self):
        b = APG.md_blocks("## 見出し\n### 小見出し\n段落の文。\n- 一つ目\n・二つ目\n\n出典")
        self.assertEqual([x["kind"] for x in b], ["h2", "h3", "p", "ul", "h2"])
        self.assertEqual(b[3]["texts"], ["一つ目", "二つ目"])


class InlinePhotos(Base):
    def photo_for(self, name):
        return ({"image_type": "jpeg", "author": "A", "license": "cc-by"}, name.encode("utf-8") * 10)

    def build(self, text, names, words=None):
        doc = {"route": "guide", "text": text, "species": names, "markdown": True, "title": "題", "species_words": words or {},
               "stop_headings": ["出典"]}
        return APG.build(doc, photo_for=self.photo_for, photo_credit=lambda m: "撮影 A", csp="default-src 'none'", max_bytes=None)

    def test_photo_follows_the_paragraph_with_the_name(self):
        html, _l, shown = self.build("はじめの文。\n\n## 谷\n谷ではコガモが見られます。\n\n## 次\n次の文。", ["コガモ", "ブナ"])
        i_para, i_card, i_next = html.index("谷ではコガモ"), html.index('aria-label="コガモ"'), html.index("<h2>次</h2>")
        self.assertTrue(i_para < i_card < i_next)                       # コガモの写真は、その段落のすぐ後ろ
        self.assertLess(html.index('aria-label="ブナ"'), html.index("はじめの文"))   # どの段落にもない種は本文の前にまとめて
        self.assertEqual([n for n, _ in shown], ["コガモ", "ブナ"])

    def test_words_found_in_text_place_the_photo(self):
        html, _l, _s = self.build("はじめ。\n\nもみじ台ではモミジがすばらしい。", ["イロハモミジ"], {"イロハモミジ": ["イロハモミジ", "モミジ"]})
        self.assertLess(html.index("モミジがすばらしい"), html.index('aria-label="イロハモミジ"'))

    def test_names_after_the_sources_heading_do_not_place(self):
        html, _l, _s = self.build("はじめ。\n\n出典\n・コガモの会 https://example.org/a", ["コガモ"])
        self.assertLess(html.index('aria-label="コガモ"'), html.index("はじめ"))


class Title(Base):
    def test_place_date_topic(self):
        self.assertEqual(GAP.title_for(self.save(), self.env), "試験山 今週末の見どころ")

    def test_single_subject_without_place(self):
        g = self.save(question="野鳥のおすすめを教えて", cands=[], subjects=["birds"])
        self.assertEqual(GAP.title_for(g, self.env), "野鳥のおすすめ")

    def kind(self, q, intent, route=None, subjects=None, cands=(), origin=None):
        g = self.save(question=q, cands=list(cands), subjects=subjects or ["autumn_leaves", "flowers", "birds"])
        p = GB.brief_dir(self.env) / f"{g['brief']}.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d.update({"intent": intent, "route": route or intent, "origin": origin or "横浜", "origin_source": "question" if origin else "default"})
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return GAP.title_for(g, self.env)

    def test_titles_by_question_type(self):                                # 段階81 の続き 2(本人の指示 2026-11-12)
        self.assertEqual(self.kind("冬桜と寒桜の違いを教えて", "difference"), "冬桜と寒桜の違い")
        self.assertEqual(self.kind("試験浦にはどんな野鳥がいるの?", "knowledge", "unknown_place", ["birds"]), "試験浦の野鳥")
        self.assertEqual(self.kind("試験県で、野鳥や地形の観察会はある?", "event", subjects=["birds"]), "試験県 野鳥・地形の観察会")
        self.assertEqual(self.kind("桜の見られる時期と場所を教えて", "normal", "season_place"), "桜の名所と時期")
        self.assertEqual(self.kind("試験浜で見られる花を教えて", "plan", subjects=["flowers"]), "試験浜で見られる花")
        self.assertEqual(self.kind("今の見頃のものを教えて", "now", "plan"), "今の見頃")
        self.assertEqual(self.kind("試験岳の見どころを教えて", "knowledge", "highlights"), "試験岳の見どころ")
        self.assertEqual(self.kind("来週末、試験宮から行きやすい場所でおすすめある?", "plan", origin="試験宮"), "試験宮から 来週末のおすすめ")

    def test_subject_word_when_question_has_none(self):
        g = self.save(question="おすすめを教えて", cands=[], subjects=["birds"])
        self.assertEqual(GAP.title_for(g, self.env), "野鳥のおすすめ")


class Reply(Base):
    def test_reply_after_page(self):
        g = self.save()
        with self.assertRaises(GAP.ReplyError):
            GAP.page_reply(None, NOW, self.env)                         # ページを作る前は出さない
        GAP.make(g, NOW, self.env, fetch=False)
        t = GAP.page_reply("https://claude.ai/artifact/AbC_12-x", NOW, self.env)
        self.assertEqual(t, "「試験山 今週末の見どころ」の写真つきページです。答えの内容と写真を、このページにまとめています。\nhttps://claude.ai/artifact/AbC_12-x")
        self.assertTrue(GAP.accepts_reply(t, NOW, self.env))
        self.assertFalse(GAP.accepts_reply(t + "\n公開しました。", NOW, self.env))
        self.assertEqual(FC.run(t, now=NOW, env=self.env)["text"], t + "\n")
        for w in ("検査", "資料", "記録", "コマンド", "合格"):
            self.assertNotIn(w, t)

    def test_bad_url_is_refused(self):
        GAP.make(self.save(), NOW, self.env, fetch=False)
        with self.assertRaises(GAP.ReplyError):
            GAP.page_reply("https://example.org/x", NOW, self.env)

    def test_newer_answer_voids_the_page(self):
        GAP.make(self.save(), NOW, self.env, fetch=False)
        t = GAP.page_reply(None, NOW, self.env)
        self.save(text="別の答え。", saved="2026-11-12T09:30:00+09:00")   # ページのあとに別の答えが合格した
        self.assertFalse(GAP.accepts_reply(t, NOW, self.env))
        with self.assertRaises(GAP.ReplyError):
            GAP.page_reply(None, NOW, self.env)


class Hook(unittest.TestCase):
    def turn(self, *cmds):
        return {"prompt": "今週末の紅葉を教えて。artifactにして", "calls": [{"name": "Bash", "input": {"command": c}, "result": ""} for c in cmds]}

    BRIEF = 'python -X utf8 -m ikimonobiyori.ask brief "q"'
    VERIFY = "python -X utf8 -m ikimonobiyori.ask verify d.txt --brief b1"
    PAGE = "python -X utf8 -m ikimonobiyori.ask page"
    REPLY = "python -X utf8 -m ikimonobiyori.ask page-reply --url https://claude.ai/artifact/x"

    def test_reply_passes_only_with_a_page_after_verify(self):
        msg = {"last_assistant_message": "案内の文"}
        ok = SH.decide(msg, self.turn(self.BRIEF, self.VERIFY, self.PAGE, self.REPLY), None, guide_ok=lambda m: False, page_ok=lambda m: m == "案内の文")
        self.assertEqual((ok["block"], ok["why"]), (False, "guide_page"))
        no_page = SH.decide(msg, self.turn(self.BRIEF, self.VERIFY, self.REPLY), None, guide_ok=lambda m: False, page_ok=lambda m: True)
        self.assertEqual((no_page["block"], no_page["why"]), (True, "guide_mismatch"))     # page-reply だけではページを作ったことにならない
        before = SH.decide(msg, self.turn(self.BRIEF, self.PAGE, self.VERIFY), None, guide_ok=lambda m: False, page_ok=lambda m: True)
        self.assertTrue(before["block"])                                                   # ページが ask verify より前
        other = SH.decide({"last_assistant_message": "書き足した文"}, self.turn(self.BRIEF, self.VERIFY, self.PAGE), None,
                          guide_ok=lambda m: False, page_ok=lambda m: m == "案内の文")
        self.assertEqual((other["block"], other["why"]), (True, "guide_mismatch"))

    def test_full_answer_still_passes(self):
        d = SH.decide({"last_assistant_message": "合格した文"}, self.turn(self.BRIEF, self.VERIFY, self.PAGE), None,
                      guide_ok=lambda m: m == "合格した文", page_ok=lambda m: False)
        self.assertEqual((d["block"], d["why"]), (False, "guide_checked"))


if __name__ == "__main__":
    unittest.main()
