"""開いた質問でも、手元の今年の現況を並べ、広く探す対象を出す(指示書 open-question-breadth 第 1 部。2026-11-28)。通信しない。
記録はすべて作り物(出どころの名前に「作り物」・ホストは example)。一時のデータ置き場にだけ書く。"""
import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_run as AR
from ikimonobiyori import current_status as CS
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import observations as O
from ikimonobiyori import research as RS

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
Q = "ツバキやサザンカが見られるところを教えて"
HOST = "sazanka-test.example.jp"
URL = f"https://{HOST}/news"
RECS = [
    {"subject": "flowers", "name": "試験のさざんか園(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "サザンカ",
     "state": "サザンカが見ごろ", "state_date": "2026-11-26", "url": URL, "publisher": "試験の運営者(作り物)", "source_class": "official"},
    {"subject": "flowers", "name": "試験の古い園(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "サザンカ",
     "state": "サザンカが咲き始め", "state_date": "2026-10-20", "url": URL + "/old", "publisher": "試験の運営者(作り物)", "source_class": "official"},
    {"subject": "flowers", "name": "試験の椿の丘(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "ツバキ", "part": "椿の小径",
     "state": "ツバキが咲き始め", "state_date": "2026-11-25", "url": URL + "/tsubaki", "publisher": "試験の運営者(作り物)", "source_class": "official"},
    {"subject": "flowers", "name": "試験の紹介の園(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "サザンカ",
     "state": "サザンカが見頃", "state_date": "2026-11-26", "url": "https://intro-test.example.com/sazanka", "publisher": "試験の紹介サイト(作り物)", "source_class": "secondary"},
    {"subject": "flowers", "name": "試験のばら園(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "バラ",
     "state": "秋バラが見ごろ", "state_date": "2026-11-26", "url": URL + "/rose", "publisher": "試験の運営者(作り物)", "source_class": "official"},
]
FOOT = "\n[場所]\n記録: 試験のさざんか園(作り物)\n知識: なし\n"

_ORIG = GB.cfg


def _on():
    c = copy.deepcopy(_ORIG())
    c["official_hosts"] = list(c.get("official_hosts") or []) + [HOST]
    return c


def _open_off():
    c = _on()
    c["current_status"]["open"]["enabled"] = False
    return c


class OpenQuestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-open-question-")
        GB._HOSTS = None
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        with mock.patch.object(GB, "cfg", _on):
            cls.rec = O.record(RECS, now=NOW - timedelta(hours=1))
            cls.doc = GB.build(Q, now=NOW)
            GB.save(cls.doc)
            cls.md = GB.render_md(cls.doc)
            cls.named = GB.build("今週末、筑波山で紅葉を見たい", now=NOW)
        with mock.patch.object(GB, "cfg", _open_off):
            cls.off = GB.build(Q, now=NOW)
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def check(self, text, doc=None):
        with mock.patch.object(GB, "cfg", _on):
            return GV.check(text + FOOT, doc or self.doc)

    def test_records_written(self):
        self.assertEqual(self.rec["written"], len(RECS))

    def test_known_current_in_brief(self):
        ob = self.doc["current_status"]["open"]
        names = [k["name"] for k in ob["known"]]
        self.assertIn("試験のさざんか園(作り物)", names)
        self.assertNotIn("試験の古い園(作り物)", names)          # 状態の日付が open.recent_days より前
        self.assertNotIn("試験のばら園(作り物)", names)          # 聞かれた種(ツバキ・サザンカ)の語が無い
        self.assertEqual(ob["what"], "ツバキ・サザンカ")
        fact = next(f for f in self.doc["facts"] if f["id"] == ob["known"][0]["fact"])
        self.assertEqual(fact["kind"], "current")
        self.assertIn("11/26時点", fact["content"])

    def test_part_record_shown_with_part(self):
        ob = self.doc["current_status"]["open"]
        self.assertIn("試験の椿の丘(作り物)", [k["name"] for k in ob["known"]])
        self.assertIn("試験の椿の丘(作り物)(椿の小径): ツバキが咲き始め(11/25時点", self.md)
        self.assertNotIn("試験の椿の丘(作り物)", [r["name"] for r in self.doc["candidates"]])     # part の記録だけの名所は候補にしない

    def test_same_day_other_state_not_hidden(self):
        """同じ名所・同じ URL・同じ日付でも、状態の文が違う記録は、前の事実で隠さない(第5部の試し 質問 4)。"""
        F = GB._Facts(_on(), set())
        F.add("current", "試験のさざんか園(作り物): 前に読んだ別の文(11/26時点)", place="試験のさざんか園(作り物)", url=URL, observed="2026-11-26")
        with mock.patch.object(GB, "cfg", _on):
            ob = CS.add_open_facts(F, Q, {"subjects": ["flowers"], "origin": "横浜"}, [], NOW, None, _on())
        fid = next(k["fact"] for k in ob["known"] if k["name"] == "試験のさざんか園(作り物)")
        self.assertIn("サザンカが見ごろ", next(f for f in F.rows if f["id"] == fid)["content"])

    def test_secondary_not_known(self):
        self.assertNotIn("試験の紹介の園(作り物)", [k["name"] for k in self.doc["current_status"]["open"]["known"]])

    def test_legend_word(self):
        pol = O.load_policy()
        pub, legend = next(iter(((pol.get("state_symbols") or {}).get("by_publisher") or {}).items()))
        sym = next(iter(legend))
        self.assertEqual(CS._legend_state({"state": sym, "publisher": pub}, pol), f"{sym}(凡例: {legend[sym]})")
        self.assertEqual(CS._legend_state({"state": "見ごろ", "publisher": pub}, pol), "見ごろ")

    def test_known_place_is_candidate(self):
        c = next(r for r in self.doc["candidates"] if r["name"] == "試験のさざんか園(作り物)")
        self.assertEqual(c["basis"], "current")
        self.assertTrue(c.get("distance_text"))

    def test_open_target(self):
        t = [x for x in self.doc["research"]["targets"] if x.get("kind") == "open_breadth"]
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["where"], self.doc["current_status"]["open"]["where"])
        self.assertIn("tenki.jp", t[0]["blocked_domains"])
        self.assertIn("weathernews.jp", t[0]["blocked_domains"])
        self.assertTrue(t[0]["max_searches"] and t[0]["max_pages"])

    def test_markdown(self):
        self.assertIn("## 聞かれた対象の今年の現況(手元の記録・新しい順)", self.md)
        self.assertIn("試験のさざんか園(作り物): サザンカが見ごろ(11/26時点", self.md)
        self.assertIn("ask research searched --brief " + self.doc["id"], self.md)
        self.assertIn("blocked_domains", self.md)

    def test_named_question_unchanged(self):
        self.assertNotIn("open", self.named.get("current_status") or {})
        self.assertFalse([t for t in self.named["research"]["targets"] if t.get("kind") == "open_breadth"])

    def test_off_switch(self):
        self.assertNotIn("open", self.off.get("current_status") or {})
        self.assertFalse([t for t in self.off["research"]["targets"] if t.get("kind") == "open_breadth"])
        self.assertNotIn("試験のさざんか園(作り物)", [r["name"] for r in self.off["candidates"] if r.get("basis") == "current"])

    def test_skipped_then_searched(self):
        text = "試験のさざんか園(作り物)では、11月26日時点でサザンカが見ごろです [F%s]。\n" % self.doc["current_status"]["open"]["known"][0]["fact"][1:]
        codes = {e["code"] for e in self.check(text)["errors"]}
        self.assertIn("current_research_skipped", codes)
        with mock.patch.object(GB, "cfg", _on):
            CS.note_searched(self.doc["id"], self.doc["current_status"]["open"]["where"], found=True, now=NOW + timedelta(minutes=5))
            codes = {e["code"] for e in self.check(text)["errors"]}
            again = GB.build(Q, now=NOW + timedelta(minutes=10))
        self.assertNotIn("current_research_skipped", codes)
        self.assertFalse([t for t in again["research"]["targets"] if t.get("kind") == "open_breadth"])
        self.assertTrue(again["current_status"]["open"]["searched"]["found"])

    def test_lines_for_open_only(self):
        t = [x for x in self.doc["research"]["targets"] if x.get("kind") == "open_breadth"]
        L = RS.lines_for("bX", t)
        self.assertTrue(any("開いた質問" in x for x in L))
        self.assertFalse(any("ask research fetch" in x for x in L))     # 公式ページの名所の手順(段階78)は出さない


class OpenRoute(unittest.TestCase):
    def test_range_only_question_is_plan(self):
        cond = AR.resolve("横浜から行ける場所で紅葉情報を教えて", NOW)
        self.assertEqual(cond["route"], "plan")

    def test_knowledge_question_stays(self):
        cond = AR.resolve("紅葉について教えて", NOW)
        self.assertEqual(cond["route"], "knowledge")


if __name__ == "__main__":
    unittest.main()
