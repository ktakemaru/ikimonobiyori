"""段階62 第6部: 行事・観察会の索引(行事の台帳 + 記録済みの行事のうち、使ってよい施設のもの)・期間と地域の絞り込み・検査。
通信なし・合成データ。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import event_index as EI
from ikimonobiyori import facility_events as FE
from ikimonobiyori import intent

import test_event_verify as EV

TODAY = date(2026, 11, 8)
CENTERS = [{"id": "t-forest", "name": "試験自然観察の森", "prefecture": "神奈川県", "approval": {"status": "approved"}},
           {"id": "t-park", "name": "試験県自然学習センター・試験自然観察公園", "prefecture": "埼玉県", "approval": {"status": "approved"}}]


def fest(**kw):
    base = {"id": "x", "name": "試験の森の生きもの学会", "organizer": "試験自然観察の森自然観察センター", "organizer_class": "official",
            "start": "2026-11-29", "end": "2026-11-29", "venue": "試験の森のホール(試験市)", "url": "https://forest.example.org/40th.html",
            "raw": ["2026年11月29日（日）"]}
    return {**base, **kw}


def index(fests, events=None):
    return EI.build(TODAY, events=events if events is not None else {"facilities": [], "events": []}, festivals_doc={"festivals": fests}, centers=CENTERS)


class Index(unittest.TestCase):
    def test_recorded_events_of_approved_centers_are_included(self):
        doc = index([fest(), fest(id="y", name="試験のバードウォッチング（試験自然観察公園）", organizer="試験県自然学習センター", start="2026-11-14",
                              end="2026-11-14", url="https://park.example.org/e.html", raw=["2026年11月14日（土）"])])
        titles = {e["title"]: e for e in doc["events"]}
        self.assertEqual(set(titles), {"試験の森の生きもの学会", "試験のバードウォッチング（試験自然観察公園）"})
        self.assertEqual(titles["試験の森の生きもの学会"]["kind"], "講座")
        self.assertEqual(titles["試験のバードウォッチング（試験自然観察公園）"]["kind"], "観察会")
        self.assertEqual(FE.validate(doc), [])

    def test_unapproved_ended_secondary_and_bad_weekday_are_excluded(self):
        doc = index([fest(organizer="どこかの団体", venue="どこか"), fest(id="e", start="2026-11-01", end="2026-11-01", raw=["2026年11月1日（日）"]),
                     fest(id="s", organizer_class="secondary"), fest(id="w", start="2026-11-29", end="2026-11-29", raw=["11月29日（土）"])])
        self.assertEqual(doc["events"], [])

    def test_note_in_brackets_does_not_decide_the_kind(self):
        doc = index([fest(name="秋のクイズラリー（試験自然観察の森）", start="2026-11-21", end="2026-11-23", raw=["11月21日（土）～23日（月）"])])
        self.assertEqual(doc["events"][0]["kind"], "イベント")


class Answer(unittest.TestCase):
    def doc(self):
        return index([fest(), fest(id="y", name="試験の観察会（試験自然観察公園）", organizer="試験県自然学習センター", start="2026-11-21", end="2026-11-23",
                               url="https://park.example.org/e.html", raw=["2026年11月21日（土）～23日（月）"])], events=EV.ledger())

    def test_answer_mixes_ledger_and_recorded_events_and_passes(self):
        doc = self.doc()
        text = intent.compose("観察会はある?", cards=[], today=TODAY, events=doc)
        self.assertIn("試験の森の生きもの学会", text)
        self.assertIn("2026年11月21日(土)〜2026年11月23日(月)", text)
        self.assertIn("試験の野鳥入門", text)
        self.assertEqual(intent.check_event(text, TODAY, doc), [])
        bad = text.replace("2026年11月29日(日)", "2026年11月29日(土)")
        self.assertIn("event_weekday_mismatch", {e["code"] for e in intent.check_event(bad, TODAY, doc)})

    def test_region_and_period_filters(self):
        doc = self.doc()
        sai = intent.compose("埼玉の観察会は?", cards=[], today=TODAY, events=doc)
        self.assertIn("試験の観察会", sai)
        self.assertNotIn("試験の森の生きもの学会", sai)
        both = intent.compose("神奈川か埼玉の観察会は?", cards=[], today=TODAY, events=doc)
        self.assertIn("試験の観察会", both)
        self.assertIn("試験の森の生きもの学会", both)
        dec = intent.compose("12月の観察会は?", cards=[], today=TODAY, events=doc)
        self.assertIn("試験の地形観察会", dec)
        self.assertNotIn("試験の森の生きもの学会", dec)

    def test_period_of(self):
        self.assertEqual(FE.period_of("今週末の観察会", date(2026, 11, 9)), (date(2026, 11, 14), date(2026, 11, 15)))
        self.assertEqual(FE.period_of("来週末の観察会", date(2026, 11, 9)), (date(2026, 11, 21), date(2026, 11, 22)))
        self.assertEqual(FE.period_of("12月の講座", TODAY), (date(2026, 12, 1), date(2026, 12, 31)))
        self.assertEqual(FE.period_of("今月の講座", TODAY), (TODAY, date(2026, 11, 30)))
        self.assertIsNone(FE.period_of("観察会はある?", TODAY))

    def test_no_false_scope_explanation(self):
        text = intent.compose("観察会はある?", cards=[], today=TODAY, events=self.doc())
        self.assertNotIn("台帳", text)
        self.assertNotIn("入っていません", text)


if __name__ == "__main__":
    unittest.main()
