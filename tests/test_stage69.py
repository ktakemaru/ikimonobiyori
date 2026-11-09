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


def _card(title, place, cat, facts):
    return {"title": title, "category": cat, "place": place, "place_aliases": [], "facts": list(facts), "condition": {"year_dependent": False},
            "source": {"name": "試験の自然博物館", "title": "試験の資料", "url": "https://example.org/" + title, "checked_on": "2026-11-01"},
            "confidence": "紹介", "rights": "確認済み", "usage": "ガイドの目として1行"}


def _hcand(cid, name, city, start, end, kind=None, events=()):
    return {"id": cid, "name": name, "city": city, "area": None, "prefecture": "神奈川県", "point": None, "flower_kinds": [kind] if kind else [],
            "typical": [{"start": start, "end": end, "text": "例年", "url": "https://example.org/w-" + cid, "kind": kind, "source_class": "official"}],
            "events": list(events)}


class Part2Routing(unittest.TestCase):
    """第2部: 「何について」×「日付」の振り分け。"""

    def route(self, q):
        from ikimonobiyori import answer_run as R
        return R.resolve(q, NOW)["route"]

    def test_place_with_date_is_highlights_not_the_kanto_list(self):
        for q in ("今週末、高尾山の見どころを教えて", "今週末の陣馬山のみどころを教えて", "今週末、神奈川 大山の見どころ"):
            self.assertEqual(self.route(q), "highlights_dated", q)
        self.assertEqual(self.route("高尾山の見どころを教えて"), "highlights")       # 日付なしはこれまでどおり

    def test_area_with_date_is_highlights(self):
        """段階69 の続き(本人の指示 2026-11-09): エリア + 日付も見どころ + その日の見込み。都県・関東だけなら計画のまま。"""
        for q in ("今週末の日光の見どころは?", "今週末、箱根の見どころを教えて", "来週末の鎌倉の見どころ"):
            self.assertEqual(self.route(q), "highlights_dated", q)
        for q in ("今週末の神奈川の見どころ", "今週末、関東の見どころは?", "今週末の日光の紅葉は?"):
            self.assertEqual(self.route(q), "plan", q)

    def test_species_with_date(self):
        self.assertEqual(self.route("今週末、カワセミを見たいのだけど。"), "species_dated")
        self.assertEqual(self.route("今週末の紅葉"), "plan")                           # テーマの総称は計画
        self.assertEqual(self.route("今週末、見られる花を紹介して"), "plan")
        self.assertEqual(self.route("11/15に桜を見たい"), "guide")                     # 桜は日付つきのガイド型のまま

    def test_combination(self):
        from ikimonobiyori import combo
        self.assertEqual(self.route("冬の渡り鳥と紅葉を見られる場所はある?"), "combo")
        self.assertEqual([w for w, _ in combo.topics_of("冬の渡り鳥と紅葉を見られる場所はある?")], ["冬の渡り鳥", "紅葉"])
        self.assertFalse(combo.is_combo_question("紅葉の名所を教えて"))

    def test_area_alias_kaiwai(self):
        from ikimonobiyori import areas as A
        self.assertEqual(A.from_question("今週末、富士山界隈で見られる花を紹介して"), ["富士山"])
        self.assertEqual(A.resolve("富士山界隈")["name"], "富士五湖")

    def test_region_word_next_to_a_place_is_not_a_place(self):
        from ikimonobiyori import highlights as HL
        cards = [_card("試験山の森", "試験山", "季節の仕組み", ["試験山はブナの森"]), _card("県の話", "神奈川", "季節の仕組み", ["関係のない事実"])]
        self.assertEqual([p["name"] for p in HL.places("神奈川 試験山の見どころ", cards)], ["試験山"])


class Part2DatedPlace(unittest.TestCase):
    """第2部 2: 場所 + 日付 → 見どころ + その日の見込み + 行く前に確認すること。"""

    def compose(self, q, on):
        from datetime import date
        from ikimonobiyori import highlights as HL
        cards = [_card("試験山の森", "試験山", "季節の仕組み", ["試験山はブナの森", "秋は黄葉が美しい"]),
                 _card("試験山のクマ", "試験山", "安全", ["クマに注意して歩く"])]
        cands = {"autumn_leaves": [_hcand("t-1", "試験山", "試験町", "11-10", "11-30")],
                 "flowers": [_hcand("t-2", "試験山の草原", "試験町", "06-01", "06-20", kind="ニッコウキスゲ",
                                    events=[{"name": "試験の山まつり", "start": "2026-11-01", "end": "2026-11-23", "url": "https://example.org/ev",
                                             "source_class": "official"}])],
                 "birds": []}
        return HL.compose(q, today=date(2026, 11, 9), cards=cards, centers=[], reports=[], cands=cands,
                          records={"autumn_leaves": [], "flowers": [], "birds": []}, on=on)

    def test_outlook_follows_the_highlights(self):
        from datetime import date
        t = self.compose("今週末、試験山の見どころ", [date(2026, 11, 14), date(2026, 11, 15)])["text"]
        self.assertTrue(t.startswith("**試験山の見どころと11/14・11/15の見込み**"))
        self.assertIn("## 11/14・11/15の見込み", t)
        self.assertIn("・試験山: 紅葉は例年11月上旬〜11月下旬で、11/14・11/15は例年の時期に入ります", t)
        self.assertIn("・試験山の草原: 試験の山まつりの期間中です(11/1〜11/23)", t)
        self.assertNotIn("ニッコウキスゲは例年", t.split("## 11/14")[1])        # 時期の外の花は見込みに書かない
        self.assertLess(t.index("### 秋"), t.index("### 夏"))                    # 季節はその日の月を先に
        self.assertLess(t.index("## 11/14"), t.index("## 行く前に確認すること"))
        self.assertNotIn("今回のおすすめ", t)

    def test_no_record_says_so_in_one_line(self):
        from datetime import date
        t = self.compose("試験山の見どころ", [date(2027, 2, 6)])["text"]
        self.assertIn("2/6の今年の様子は、確認できている公式ページの範囲ではまだ分かりません。", t)


class Part2DatedSpecies(unittest.TestCase):
    """第2部 3: 種 + 日付。野鳥は観察記録・施設の発信に種の名があれば日付つき。"""

    def test_bird_records_with_the_species_name(self):
        from datetime import date
        from ikimonobiyori import season_place as SP
        sp = {"name": "カワセミ", "match": ["カワセミ"], "words": ["カワセミ"], "includes": []}
        recs = [{"name": "試験の池(試験の会)", "publisher": "試験の会", "source_class": "official", "species": ["カワセミ", "コガモ"],
                 "state_date": "2026-11-07", "url": "https://example.org/pond"},
                {"name": "古い池", "publisher": "試験", "source_class": "official", "species": ["カワセミ"], "state_date": "2026-09-01",
                 "url": "https://example.org/old"},
                {"name": "紹介の池", "publisher": "紹介", "source_class": "secondary", "species": ["カワセミ"], "state_date": "2026-11-08",
                 "url": "https://example.org/sec"}]
        vcs = [{"name": "試験のセンター", "species": ["カワセミ"], "state": "池にカワセミ", "date": "2026-11-06", "url": "https://example.org/vc"}]
        got = SP.species_records(sp, [date(2026, 11, 14)], records=recs, vc_rows=vcs, today=date(2026, 11, 9))
        self.assertEqual([x[1] for x in got], ["試験の池(試験の会)", "試験のセンター"])

    def test_is_species_dated(self):
        from ikimonobiyori import season_place as SP
        self.assertTrue(SP.is_species_dated("今週末、カワセミを見たい"))
        self.assertFalse(SP.is_species_dated("カワセミが見られる場所"))
        self.assertFalse(SP.is_species_dated("今週末、紅葉とカワセミ"))


class Part2Combo(unittest.TestCase):
    def test_same_and_near_pairs_come_first(self):
        from ikimonobiyori import combo
        a = [{"name": "試験の森", "point": {"lat": 35.0, "lon": 139.0}}, {"name": "試験の寺", "point": {"lat": 35.05, "lon": 139.0}}]
        b = [{"name": "試験の森", "point": {"lat": 35.0, "lon": 139.0}}, {"name": "試験の沼", "point": {"lat": 35.06, "lon": 139.01}},
             {"name": "遠い沼", "point": {"lat": 37.0, "lon": 139.0}}]
        r = combo.find("autumn_leaves", "birds", cand_a=a, cand_b=b)
        self.assertEqual(r["same"], ["試験の森"])
        self.assertEqual([(p["a"], p["b"]) for p in r["near"]], [("試験の寺", "試験の沼")])


class Part2FitLength(unittest.TestCase):
    """第2部 6: 字数の上限で候補を減らすとき、狙い別の節を 1 件ずつ残せる数(3)は残す(「紅葉やススキ、そのほか秋」が 1 件になっていた)。"""

    def test_min_picks_kept(self):
        from unittest import mock
        from ikimonobiyori import answer_run as AR
        from ikimonobiyori import answer_gates as AG
        from ikimonobiyori import skeleton as SK
        plan = {"picks": [{"name": n, "score": s} for n, s in (("A", 5), ("B", 4), ("C", 3), ("D", 2), ("E", 1))]}
        with mock.patch.object(SK, "compose", lambda f, p, o, defaulted_date=False: "あ" * 5000), \
                mock.patch.object(AG, "length_limit", lambda p, t=None: 10):
            _text, plan2, dropped = AR.fit_length({}, plan, [], False)
        self.assertEqual([p["name"] for p in plan2["picks"]], ["A", "B", "C"])
        self.assertEqual(dropped, ["E", "D"])
        self.assertEqual(AR.cfg()["min_picks_kept"]["value"], 3)


class Part3Research(unittest.TestCase):
    """第3部: 記録がないときは「調べる対象」を構造化して返し、記録したあとは答えが出る。名所の登録は今の状態なしでよい。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.dir}

    REC = {"subject": "flowers", "name": "試験のホタルの里", "city": "あきる野市", "prefecture": "東京都", "kind": "ホタル",
           "typical": "例年6月上旬〜6月下旬", "url": "https://www.city.akiruno.tokyo.jp/test.html", "source_class": "official", "basis": "page",
           "publisher": "あきる野市"}

    def test_registration_without_state(self):
        from ikimonobiyori import observations as O
        pol = O.load_policy()
        self.assertEqual(O.validate(dict(self.REC), pol), [])
        self.assertIn("state がない", O.validate({**self.REC, "kind": None}, pol))          # 種と時期のない記録は今の状態が要る

    def test_event_format_error_is_explained(self):
        from ikimonobiyori import observations as O
        errs = O.validate({"subject": "flowers", "name": "試験の園", "url": "https://example.org/", "source_class": "official",
                           "state": "バラが見ごろ", "event": "バラが咲いている"}, O.load_policy())
        self.assertTrue(any("event を省き" in e for e in errs), errs)

    def test_place_filter(self):
        from ikimonobiyori import season_place as SP
        self.assertEqual(SP.place_filter("あきる野市でホタルが見られるところと時期は?")["cities"], ["あきる野市"])
        self.assertEqual(SP.place_filter("箱根にススキの名所はない?")["cities"], ["箱根町"])
        self.assertIsNone(SP.place_filter("ホタルが見られる場所"))

    def test_needs_research_then_answer_after_recording(self):
        from ikimonobiyori import observations as O
        from ikimonobiyori import season_place as SP
        from datetime import date
        q = "あきる野市でホタルが見られるところと時期は?"
        before = SP.compose(q, today=date(2026, 11, 9), origin="横浜", env=self.env, place=SP.place_filter(q))
        self.assertEqual(before["research"], [{"what": "ホタル", "where": "あきる野市", "search": "あきる野市 ホタル 公式"}])
        self.assertIn("あきる野市のホタルは、公式の情報では確かめられませんでした。", before["text"])
        self.assertNotIn("お答えできません", before["text"])
        out = O.record([dict(self.REC)], env=self.env)
        self.assertFalse(out.get("rejected"), out)
        after = SP.compose(q, today=date(2026, 11, 9), origin="横浜", env=self.env, place=SP.place_filter(q))
        self.assertEqual(after["research"], [])
        self.assertIn("試験のホタルの里", after["text"])
        self.assertNotIn("確かめられませんでした", after["text"])

    def test_stderr_line_and_not_in_the_answer(self):
        import io
        from ikimonobiyori import answer_run as AR
        res = {"text": "答え\n", "status": "DEGRADED", "stage": 3, "elapsed_s": 0.1, "workdir": "x",
               "research_targets": [{"what": "ホタル", "where": "あきる野市", "search": "あきる野市 ホタル 公式"}]}
        out, err = io.StringIO(), io.StringIO()
        AR.print_result(res, out, err)
        self.assertNotIn("調べる", out.getvalue())
        self.assertIn('調べる: [{"what": "ホタル", "where": "あきる野市"', err.getvalue())


if __name__ == "__main__":
    unittest.main()
