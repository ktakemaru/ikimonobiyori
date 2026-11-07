"""行事の答えに行事用の検査を使う(ikimonobiyori/facility_events.answer_errors・intent.check_event)。通信なし・合成データ。
行事の答えには知識カードの検査と名所の候補数の下限を当てない。行事以外の答えの検査は変えない。"""
import contextlib
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask
from ikimonobiyori import ask_verify as V
from ikimonobiyori import facility_events as FE
from ikimonobiyori import intent

TODAY = date(2026, 11, 8)
Q = "神奈川で、野鳥や地形の観察会はある?"
URL1 = "https://museum.example.org/event/bird.html"
URL2 = "https://museum.example.org/event/geo.html"


def ledger(status="approved", pending_event=False):
    facs = [{"id": "test-museum", "name": "試験県立自然博物館", "prefecture": "神奈川県", "approval": {"status": status}}]
    evs = [
        {"facility": "test-museum", "kind": "講座", "title": "試験の野鳥入門", "topics": ["野鳥"], "date": "2026-12-05", "weekday_text": "土曜",
         "time": "9時30分から16時", "deadline": "2026-11-24", "deadline_weekday_text": "火曜", "capacity": 15, "target": "小学5年生から大学生",
         "place": "当博物館(実習実験室)", "url": URL1},
        {"facility": "test-museum", "kind": "観察会", "title": "試験の地形観察会", "topics": ["地形・地質"], "date": "2026-12-05", "weekday_text": "土曜",
         "time": "10時30分から14時30分", "deadline": "2026-11-24", "deadline_weekday_text": "火曜", "capacity": 25, "target": "中学生から成人",
         "place": "試験川沿い(試験町)", "url": URL2},
        {"facility": "test-museum", "kind": "展示", "label": "特別展", "title": "里山にくらす動物たち", "topics": ["自然"],
         "start": "2026-07-18", "end": "2026-11-08", "url": "https://museum.example.org/ex.html"},
    ]
    if pending_event:
        facs.append({"id": "other-museum", "name": "試験市立資料館", "prefecture": "神奈川県", "approval": {"status": "pending"}})
        evs.append({"facility": "other-museum", "kind": "観察会", "title": "承認待ちの野鳥観察会", "topics": ["野鳥"], "date": "2026-12-06",
                    "weekday_text": "日曜", "url": "https://other.example.org/e.html"})
    return {"facilities": facs, "events": evs}


def answer(doc=None, today=TODAY, q=Q):
    return intent.compose(q, cards=[], today=today, events=doc or ledger())


def codes(errs):
    return {e["code"] for e in errs}


class EventCheck(unittest.TestCase):
    def test_correct_event_answer_passes(self):
        text = answer()
        self.assertIn("2026年12月5日(土)", text)
        self.assertEqual(intent.check_event(text, TODAY, ledger()), [])

    def test_wrong_date_weekday_deadline_capacity_url_fail(self):
        good = answer()
        cases = {
            "event_date_mismatch": good.replace("2026年12月5日(土) 9時", "2026年12月12日(土) 9時"),
            "event_weekday_mismatch": good.replace("2026年12月5日(土) 9時", "2026年12月5日(日) 9時"),
            "event_date_no_year": good.replace("2026年12月5日(土) 9時", "12月5日(土) 9時"),
            "event_capacity_mismatch": good.replace("定員15人", "定員20人"),
            "event_target_mismatch": good.replace("対象は中学生から成人", "対象は成人"),
            "event_time_mismatch": good.replace("9時30分から16時", "9時30分から17時"),
            "event_source_unknown": good + "https://museum.example.org/event/other.html\n",
            "event_source_missing": good.replace(URL1 + "\n", ""),
        }
        for code, text in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, codes(intent.check_event(text, TODAY, ledger())))
        wrong_deadline = good.replace("締め切りは2026年11月24日(火)", "締め切りは2026年11月25日(水)", 1)
        self.assertIn("event_date_mismatch", codes(intent.check_event(wrong_deadline, TODAY, ledger())))
        bad_deadline_wd = good.replace("締め切りは2026年11月24日(火)", "締め切りは2026年11月24日(水)", 1)
        self.assertIn("event_weekday_mismatch", codes(intent.check_event(bad_deadline_wd, TODAY, ledger())))

    def test_facts_not_in_ledger_fail(self):
        good = answer()
        for extra, code in (("駐車場は40台です。", "event_fact_not_in_ledger"),
                            ("試験市立美術館でも同じ講座があります。", "event_fact_not_in_ledger"),
                            ("展示「冬の鳥たち」もあります。", "event_not_in_ledger"),
                            ("https://museum.example.org/event/x.html", "event_source_unknown")):
            with self.subTest(extra=extra):
                self.assertIn(code, codes(intent.check_event(extra + "\n" + good, TODAY, ledger())))

    def test_pending_and_finished_events_are_not_shown(self):
        doc = ledger(pending_event=True)
        text = answer(doc)
        self.assertNotIn("承認待ちの野鳥観察会", text)
        self.assertEqual(intent.check_event(text, TODAY, doc), [])
        leaked = text.replace("出典\n", "試験市立資料館の観察会「承認待ちの野鳥観察会」: 2026年12月6日(日)。\n\n出典\n")
        self.assertIn("event_not_approved", codes(intent.check_event(leaked, TODAY, doc)))
        self.assertIsNone(answer(ledger("pending")))
        q = "神奈川で、自然の展示はある?"
        self.assertIn("里山にくらす動物たち", answer(q=q))                        # 会期の最終日(11/8)までは出る
        self.assertIsNone(answer(today=date(2026, 11, 9), q=q))                  # 終わった展示は出ない
        ex = answer(q=q)
        self.assertEqual(intent.check_event(ex, TODAY, ledger()), [])
        self.assertIn("event_past", codes(intent.check_event(ex, date(2026, 11, 9), ledger())))

    def test_process_terms_and_questions_are_still_checked(self):
        good = answer()
        self.assertTrue(intent.check_event(good + "ほかの日程も調べましょうか?\n", TODAY, ledger()))
        rules = V.load_rules()
        dev = (rules.get("dev_terms") or ["テスト"])[0]
        self.assertTrue(intent.check_event(good.replace("出典\n", dev + "\n出典\n"), TODAY, ledger()))

    def test_event_answer_is_not_held_to_place_candidate_minimum(self):
        text = answer()
        self.assertIn("too_few_candidates", codes(V.generic_check(text)["errors"]))   # 名所の検査は変えない(行事の答えには使わない)
        self.assertEqual(intent.check_event(text, TODAY, ledger()), [])


class NonEventChecksUnchanged(unittest.TestCase):
    CARD = {"title": "試験の鳥", "category": "生態", "place": "試験の鳥", "place_aliases": [], "facts": ["冬に3羽ほど見られる"],
            "condition": {"months": []}, "source": {"name": "試験の研究所", "url": "https://lab.example.org/bird"}}

    def test_knowledge_check_still_uses_cards(self):
        ok = "試験の鳥: 冬に3羽ほど見られる(試験の研究所)。\n\n出典\nhttps://lab.example.org/bird\n"
        self.assertEqual(intent.check(ok, [self.CARD]), [])
        self.assertIn("knowledge_fact_not_in_card", codes(intent.check(ok.replace("3羽", "40羽"), [self.CARD])))
        self.assertIn("knowledge_source_unused", codes(intent.check(ok + "https://other.example.org/x\n", [self.CARD])))

    def test_generic_check_term_lines_unchanged(self):
        rules = V.load_rules()
        dev = (rules.get("dev_terms") or ["テスト"])[0]
        r = V.generic_check("①試験の公園\n②試験の庭園\n" + dev + "\n", rules)
        self.assertIn("dev_term", codes(r["errors"]))
        self.assertTrue(any(e["line"] == 3 for e in r["errors"] if e["code"] == "dev_term"))


class Cli(unittest.TestCase):
    """実際の台帳(承認済みの kanagawa-museum)で、2026-11-08 として。通信しない。"""
    NOW = "2026-11-08T10:00:00+09:00"

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
            os.environ["IKIMONOBIYORI_DATA_DIR"] = td
            try:
                rc = ask.main([x.replace("{td}", td) for x in argv])
            finally:
                if old is None:
                    os.environ.pop("IKIMONOBIYORI_DATA_DIR", None)
                else:
                    os.environ["IKIMONOBIYORI_DATA_DIR"] = old
        return rc, out.getvalue(), err.getvalue()

    def test_knowledge_answer_for_event_passes(self):
        rc, out, err = self._run(["knowledge-answer", "--question", Q, "--now", self.NOW])
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out.count("2026年12月5日(土)"), 2)
        self.assertIn("「バードウォッチング入門」", out)
        self.assertIn("「冬の地形地質観察会―西丹沢の地質と岩石―」", out)
        self.assertNotIn("里山にくらす動物たち", out)

    def test_verify_generic_with_event_question(self):
        _, out, _ = self._run(["knowledge-answer", "--question", Q, "--now", self.NOW])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td, "answer.txt")
            p.write_text(out, encoding="utf-8")
            rc, _, err = self._run(["verify", "--generic", "--text", str(p), "--question", Q, "--now", self.NOW])
            self.assertEqual((rc, err), (0, ""))
            p.write_text(out.replace("定員15人", "定員20人"), encoding="utf-8")
            rc, _, err = self._run(["verify", "--generic", "--text", str(p), "--question", Q, "--now", self.NOW])
            self.assertEqual(rc, 1)
            self.assertIn("event_capacity_mismatch", err)
            self.assertEqual(Path(td, "final.txt").read_text(encoding="utf-8"), out)      # 台帳から作った答え


if __name__ == "__main__":
    unittest.main()
