"""段階75: ガイドの資料(ask brief)と裏取り(ask verify --brief)。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import final_check as FC
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import stop_hook as SH

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)


def fact(fid, kind, content, url="https://example.org/a", source="試験町観光協会", cls="official", observed=None, place="試験の渓谷"):
    c = GB.cfg()
    return {"id": fid, "kind": kind, "kind_label": c["kinds"][kind], "place": place, "content": content, "values": GB.values(content),
            "source": source, "source_class": cls, "url": url, "observed": observed, "read_at": "2026-11-10T08:00:00+09:00"}


def brief(question="今週末の紅葉の情報は?"):
    return {
        "id": "b20261110-test0001", "question": question, "now": NOW.isoformat(),
        "dates": {"today": "2026-11-10", "this_weekend": ["2026-11-14", "2026-11-15"], "next_weekend": ["2026-11-21", "2026-11-22"],
                  "periods": [["2026-11-14", "2026-11-15"]]},
        "candidates": [{"rank": 1, "name": "試験の渓谷", "chosen": True}],
        "facts": [fact("F001", "current", "試験の渓谷: 見頃(11/9時点、試験町観光協会)", observed="2026-11-09"),
                  fact("F002", "event", "試験の渓谷: 試験もみじまつり(まつり期間中(11/1〜11/30)。ライトアップ 16:00〜21:00)", url="https://example.org/fes"),
                  fact("F003", "typical", "試験の渓谷: 例年 11月中旬〜下旬", url="https://example.org/typ"),
                  fact("F004", "facility", "試験の渓谷: 案内所 0123-45-6789。入園料 500円", url="https://example.org/fac"),
                  fact("F005", "safety", "試験の渓谷: 11/1〜11/30 林道が通行止め", url="https://example.org/road")],
        "cards": [{"id": "K001", "title": "色づく条件", "facts": ["寒暖差が大きいと赤い色素が濃くなる"], "values": GB.values("寒暖差が大きいと赤い色素が濃くなる"),
                   "source": "試験の研究所", "url": "https://example.org/card", "checked_on": "2026-11-07", "source_class": None, "place": None}],
        "missing": [], "rules": [], "fallback": {"text": "今の形の答え\n", "stage": 2, "status": "PASS"},
    }


PLACES = "\n\n[場所]\n記録: 試験の渓谷\n知識: なし\n"


class Values(unittest.TestCase):
    def test_extracts_dates_times_money_phone(self):
        v = GB.values("11月9日と11/14〜11/15、2026-11-21。16:00〜21:00、9時30分。500円・無料。0123-45-6789。11月中旬 https://example.org/x")
        self.assertEqual(v["dates"], ["11/14", "11/15", "11/21", "11/9"])
        self.assertEqual(v["times"], ["16:00", "21:00", "9:30"])
        self.assertEqual(sorted(v["money"]), ["500", "無料"])
        self.assertEqual(v["phones"], ["0123456789"])
        self.assertIn("11月中旬", v["jun"])
        self.assertEqual(v["urls"], ["https://example.org/x"])

    def test_state_words_are_normalized(self):
        self.assertIn("見頃", GB.values("見ごろです")["states"])
        self.assertIn("色づき始め", GB.values("色づきはじめ")["states"])

    def test_full_width_digits(self):
        self.assertEqual(GB.values("１１/９時点")["dates"], ["11/9"])


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def codes(self, body, b=None, places=PLACES):
        return [e["code"] for e in GV.check(body + places, b or brief(), env=self.env)["errors"]]

    def test_marked_matching_values_pass(self):
        r = GV.check("試験の渓谷は11/9時点で見頃です。[F001]\n寒暖差が大きいと赤が濃くなります。[K001]" + PLACES, brief(), env=self.env)
        self.assertEqual(r["errors"], [])
        self.assertTrue(r["ok"])

    def test_marker_at_line_head_belongs_to_previous_sentence(self):
        self.assertEqual(self.codes("試験の渓谷は11/9時点で見頃です。\n[F001]"), [])
        self.assertEqual(self.codes("試験の渓谷は11/9時点で見頃です。"), ["unmarked_value", "unmarked_now_state"])
        self.assertEqual(self.codes("試験の渓谷は11/9時点で見頃です。[F001] 色づきは山から下ります。"), [])

    def test_marked_date_mismatch_fails(self):
        self.assertIn("value_mismatch", self.codes("試験の渓谷は11/10時点で見頃です。[F001]"))

    def test_marked_time_money_phone_mismatch_fails(self):
        self.assertIn("value_mismatch", self.codes("ライトアップは17:00からです。[F002]"))
        self.assertIn("value_mismatch", self.codes("入園料は600円です。[F004]"))
        self.assertIn("value_mismatch", self.codes("案内所は0123-45-0000です。[F004]"))
        self.assertEqual(self.codes("入園料は500円、案内所は0123-45-6789です。[F004]"), [])

    def test_event_capacity_must_match(self):
        b = brief()
        b["facts"].append(fact("F006", "event", "試験の森の観察会: 2026年12月5日(土) 10時から。定員25人", url="https://example.org/ev"))
        self.assertIn("value_mismatch", self.codes("試験の森の観察会は12月5日で、定員は30人です。[F006]", b))
        self.assertEqual(self.codes("試験の森の観察会は12月5日10時からで、定員は25人です。[F006]", b), [])

    def test_unknown_id_fails(self):
        self.assertIn("unknown_id", self.codes("試験の渓谷は見頃です。[F099]"))

    def test_event_period_as_now_state_fails(self):
        self.assertIn("now_state_not_current", self.codes("試験の渓谷は今、見頃です。[F002]"))
        self.assertIn("now_state_not_current", self.codes("試験の渓谷は今年は見頃です。[F003]"))

    def test_now_state_word_must_match_current_fact(self):
        self.assertIn("state_mismatch", self.codes("試験の渓谷は11/9時点で落葉しています。[F001]"))

    def test_month_must_match(self):
        self.assertIn("month_mismatch", self.codes("試験の渓谷は例年12月上旬が見頃です。[F003]"))
        self.assertEqual(self.codes("試験の渓谷は例年11月中旬から下旬が見頃です。[F003]"), [])

    def test_event_needs_event_fact(self):
        self.assertIn("event_not_event_fact", self.codes("試験もみじまつりは11月中旬に開催されます。[F003]"))
        self.assertEqual(self.codes("試験もみじまつりは11/1〜11/30に開催です。[F002]"), [])

    def test_unmarked_values_fail(self):
        for body in ("案内所は0123-45-6789です。", "入園料は500円です。", "開園は9:00です。", "11/9に見頃でした。", "詳しくは https://example.org/x を。"):
            self.assertIn("unmarked_value", self.codes(body), body)

    def test_target_weekend_dates_are_allowed_unmarked(self):
        self.assertEqual(self.codes("今週末(11/14・11/15)は、山から里へ紅葉が下りてくるころです。"), [])

    def test_unmarked_now_state_fails(self):
        self.assertIn("unmarked_now_state", self.codes("今ちょうど見頃です。"))

    def test_honest_and_typical_sentences_pass(self):
        self.assertEqual(self.codes("今年の飛来・観察の記録は多くありません。"), [])
        self.assertEqual(self.codes("今年の色づきは確かめられていません。"), [])
        self.assertEqual(self.codes("試験の渓谷は例年11月中旬から下旬が見頃で、今週末はその入り口です。[F003]"), [])
        self.assertEqual(self.codes("印象に残る景色です。"), [])
        self.assertEqual(self.codes("横浜の街なかの公園は、今年の色づきの様子はまだ分かっていません。"), [])
        self.assertEqual(self.codes("## 今の色づき\n今週末(11月14日・15日)の試験の渓谷は、歩いて楽しい道です。"), [])

    def test_place_from_card_is_known(self):
        b = brief()
        b["cards"][0]["facts"].append("試験の池の周りの原生林はコケの森")
        self.assertEqual(self.codes("森を歩きます。", b, places="\n\n[場所]\n記録: 試験の池\n"), [])

    def test_unmarked_event_and_closure_fail(self):
        self.assertIn("unmarked_event", self.codes("もみじまつりが月末まで開催されています。"))
        self.assertIn("unmarked_closure", self.codes("林道が通行止めです。"))

    def test_unmarked_place_with_month_or_state_fails(self):
        self.assertIn("unmarked_place_month", self.codes("試験の渓谷は11月中旬がきれいです。"))
        self.assertIn("unmarked_place_state", self.codes("試験の渓谷は見頃を過ぎています。"))

    def test_general_seasonal_sentence_passes(self):
        self.assertEqual(self.codes("冬鳥は秋に渡ってきて、春に北へ帰ります。カエデは11月に赤くなることが多い木です。"), [])

    def test_places_list(self):
        self.assertIn("places_list_missing", self.codes("色づきは山から下ります。", places=""))
        self.assertIn("unknown_record_place", self.codes("色づきは山から下ります。", places="\n\n[場所]\n記録: 架空の試験峡谷ではない場所XYZ\n"))
        many = "\n\n[場所]\n記録: 試験の渓谷\n知識: 御岳山(東京都)、筑波山(茨城県)、大山(神奈川県)、宝登山(埼玉県)\n"
        self.assertIn("too_many_knowledge_places", self.codes("色づきは山から下ります。", places=many))
        self.assertIn("knowledge_place_invalid", self.codes("色づきは山から下ります。", places="\n\n[場所]\n記録: 試験の渓谷\n知識: 試験の名古屋の森(愛知県)\n"))
        self.assertIn("knowledge_place_no_prefecture", self.codes("色づきは山から下ります。", places="\n\n[場所]\n記録: 試験の渓谷\n知識: 御岳山\n"))

    def test_knowledge_place_needs_unverified_wording(self):
        pl = "\n\n[場所]\n記録: 試験の渓谷\n知識: 御岳山(東京都)\n"
        self.assertIn("knowledge_place_not_marked", self.codes("御岳山も紅葉の名所として知られます。", places=pl))
        self.assertEqual(self.codes("御岳山も紅葉の名所として知られますが、今年の状況は確かめていません。", places=pl), [])

    def test_common_checks_are_reused(self):
        self.assertIn("internal_word", self.codes("資料によると、色づきは山から下ります。"))
        self.assertTrue(set(self.codes("色づきは山から下ります。ほかの場所も調べますか?")) & {"question_in_answer", "question_to_user", "ask_back"}
                        or any("question" in x for x in self.codes("色づきは山から下ります。ほかの場所も調べますか?")))
        self.assertTrue({"unused_source", "blocked_source"} & set(self.codes("ウェザーニュースの予想では色づきは早めです。")))
        self.assertIn("out_of_range", self.codes("北海道の大雪山は早く色づきます。"))

    def test_place_swap_fails(self):
        b = brief("霞ヶ浦にはどんな野鳥がいるの?")
        self.assertIn("place_swap", self.codes("手賀沼には冬鳥が多く集まります。", b))
        self.assertNotIn("place_swap", self.codes("霞ケ浦には冬鳥が多く集まります。", b))

    def test_final_text_removes_markers_and_adds_sources(self):
        r = GV.check("試験の渓谷は11/9時点で見頃です。[F001]\n寒暖差で赤が濃くなります。[K001]" + PLACES, brief(), env=self.env)
        self.assertNotIn("[F001]", r["final"])
        self.assertNotIn("[場所]", r["final"])
        self.assertIn("\n出典\n・試験町観光協会(11/9時点、公式) https://example.org/a", r["final"])
        self.assertIn("・試験の研究所(11/7に確認、公式ではありません) https://example.org/card", r["final"])

    def test_deterministic(self):
        d = "試験の渓谷は11/9時点で見頃です。[F001]" + PLACES
        self.assertEqual(GV.check(d, brief(), env=self.env), GV.check(d, brief(), env=self.env))


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.b = brief()
        d = GB.brief_dir(self.env)
        d.mkdir(parents=True)
        (d / f"{self.b['id']}.json").write_text(json.dumps(self.b, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pass_is_logged_and_accepted_by_final_check(self):
        r = GV.run("試験の渓谷は11/9時点で見頃です。[F001]" + PLACES, self.b["id"], now=NOW, env=self.env)
        self.assertEqual(r["status"], "PASS")
        rows = [json.loads(x) for x in (GB.brief_dir(self.env).parent / "logs" / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((rows[-1]["kind"], rows[-1]["form"], rows[-1]["brief"], rows[-1]["rewrites"]), ("guide", "guide", self.b["id"], 0))
        got = FC.run(r["text"], now=NOW, env=self.env)
        self.assertEqual(got["text"], r["text"])
        self.assertTrue(got.get("guide"))
        self.assertTrue(GV.accepts(r["text"], NOW, self.env))
        self.assertFalse(GV.accepts(r["text"] + "ほかにも探せます。", NOW, self.env))

    def test_two_rewrites_then_fallback(self):
        bad = "試験の渓谷は11/10時点で見頃です。[F001]" + PLACES
        self.assertEqual(GV.run(bad, self.b["id"], now=NOW, env=self.env)["status"], "FAIL")
        self.assertEqual(GV.run(bad, self.b["id"], now=NOW, env=self.env)["status"], "FAIL")
        r = GV.run(bad, self.b["id"], now=NOW, env=self.env)
        self.assertEqual((r["status"], r["text"], r["rewrites"]), ("FALLBACK", "今の形の答え\n", 2))
        self.assertTrue(GV.accepts("今の形の答え\n", NOW, self.env))

    def test_knowledge_places_are_recorded_as_unverified(self):
        from ikimonobiyori import unverified as U
        pl = "\n\n[場所]\n記録: 試験の渓谷\n知識: 御岳山(東京都)\n"
        r = GV.run("御岳山も紅葉の名所として知られますが、今年の状況は確かめていません。" + pl, self.b["id"], now=NOW, env=self.env)
        self.assertEqual(r["status"], "PASS")
        self.assertIn(("御岳山", "東京都"), [(x["name"], x["prefecture"]) for x in U.load(self.env)])


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def turn(self, *cmds):
        calls = [{"name": "Bash", "input": {"command": c}, "result": ""} for c in cmds]
        return {"prompt": "今週末の紅葉の情報は?", "calls": calls}

    def test_brief_without_verify_blocks(self):
        d = SH.decide({"last_assistant_message": "答え"}, self.turn('python -X utf8 -m ikimonobiyori.ask brief "今週末の紅葉の情報は?"'), None,
                      guide_ok=lambda m: False)
        self.assertEqual((d["block"], d["why"]), (True, "guide_no_verify"))

    def test_verified_text_passes_and_other_text_blocks(self):
        t = self.turn('python -X utf8 -m ikimonobiyori.ask brief "q"', "python -X utf8 -m ikimonobiyori.ask verify d.txt --brief b1")
        ok = SH.decide({"last_assistant_message": "合格した文"}, t, None, guide_ok=lambda m: m == "合格した文")
        self.assertEqual((ok["block"], ok["why"]), (False, "guide_checked"))
        ng = SH.decide({"last_assistant_message": "書き足した文"}, t, None, guide_ok=lambda m: m == "合格した文")
        self.assertEqual((ng["block"], ng["why"]), (True, "guide_mismatch"))

    def test_classic_turn_is_unchanged(self):
        t = self.turn('python -X utf8 -m ikimonobiyori.ask answer --question "q"')
        self.assertNotEqual(SH.decide({"last_assistant_message": "x"}, t, "x", guide_ok=lambda m: True)["why"], "guide_checked")


class Brief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_question_same_now_same_brief(self):
        a = GB.build("今週末の紅葉の情報は?", now=NOW, env=self.env)
        b = GB.build("今週末の紅葉の情報は?", now=NOW, env=self.env)
        self.assertEqual(json.dumps(a, ensure_ascii=False, sort_keys=True), json.dumps(b, ensure_ascii=False, sort_keys=True))
        self.assertEqual(a["dates"]["this_weekend"], ["2026-11-14", "2026-11-15"])
        self.assertEqual(a["dates"]["next_weekend"], ["2026-11-21", "2026-11-22"])
        self.assertTrue(a["rules"])
        self.assertTrue(a["fallback"]["text"].strip())

    def test_quiet_run_leaves_no_answer_record(self):
        GB.build("冬桜と寒桜の違いを教えて", now=NOW, env=self.env)
        self.assertFalse((GB.brief_dir(self.env).parent / "logs" / "answers.jsonl").exists())
        self.assertIsNone(FC.load_answer(NOW, self.env))

    def test_save_and_prev(self):
        a = GB.build("今週末、高尾山の見どころを教えて", now=NOW, env=self.env)
        GB.save(a, self.env)
        b = GB.build("枯れた茎に氷ができる。なんというの?", now=NOW, env=self.env, prev=a["id"])
        self.assertEqual(b["previous"], {"id": a["id"], "question": a["question"]})
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len({f["id"] for f in b["facts"]}), len(b["facts"]))
        jp, mp = GB.save(b, self.env)
        self.assertTrue(jp.exists() and mp.exists())
        self.assertIn("## 確かめた事実", mp.read_text(encoding="utf-8"))

    def test_pending_and_unused_sources_are_left_out(self):
        F = GB._Facts(GB.cfg(), {"https://pending.example.org/p"})
        self.assertIsNone(F.add("current", "試験の渓谷: 見頃(11/9時点)", url="https://pending.example.org/p"))
        self.assertIsNone(F.add("current", "試験の渓谷: 見頃(11/9時点)", url="https://weathernews.jp/koyo/"))
        self.assertIsNotNone(F.add("current", "試験の渓谷: 見頃(11/9時点)", url="https://example.org/ok"))
        self.assertEqual(F.rows[0]["id"], "F001")

    def test_line_facts_skip_outlook_and_label_no_info_as_typical(self):
        F = GB._Facts(GB.cfg(), set())
        text = "見頃に向かう可能性がある場所を選びました。\n・試験の庭園: 例年の見頃: 11月中旬(今年の情報は確認できていません)\n・試験の森 開館 9:00〜16:00(試験町)\n\n出典\nhttps://example.org/a\nhttps://example.org/b\n"
        GB._line_facts(F, text, GB.cfg(), {"試験町": "https://example.org/a"})
        self.assertEqual([(f["kind"], f["url"]) for f in F.rows], [("typical", None), ("facility", "https://example.org/a")])


if __name__ == "__main__":
    unittest.main()
