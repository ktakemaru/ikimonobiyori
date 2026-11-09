"""段階72 第2部: 名前の質問と、同じ名前の別のもの(シモバシラ)。カードの主語の決まり。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import knowledge as K
from ikimonobiyori import names as NM

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)
URL = "https://takaovc.ces-net.jp/?page_id=753"
MODEL = "**氷の花（氷華）**と呼ばれます。高尾山では、シモバシラというシソ科の植物の枯れた茎にできるので、その名前で呼ばれることもあります（地面にできる霜柱とは別のものです）。"


def src():
    return {"name": "高尾ビジターセンター", "title": "氷の花！シモバシラ", "url": URL, "checked_on": "2026-11-10"}


ICE = {"title": "氷の花（シモバシラの茎にできる氷）", "subject": "氷の花", "subject_aliases": ["氷華"], "category": "シーズンの目安",
       "place": "高尾山", "place_aliases": ["高尾", "シモバシラ"],
       "facts": ["氷の花は、植物シモバシラの枯れた茎から水がしみだし、外気で凍ってできる", "氷の花は例年12月中旬ごろから2月まで見られ、大きいものは1月上旬まで"],
       "condition": {"months": [12, 1, 2], "year_dependent": False}, "source": src(), "confidence": "施設の解説", "rights": "事実のみ",
       "usage": "ガイドの目として1行", "homonym": "しもばしら", "sense": "ice_flower"}
PLANT = {"title": "シモバシラ（シソ科の植物）", "subject": "シモバシラ", "category": "種の解説", "place": "シモバシラ", "place_aliases": ["高尾山"],
         "facts": ["シモバシラはシソ科の多年草で、高さは40〜70cmほど", "シモバシラは8月下旬〜10月上旬に白い穂状の花を咲かせる"],
         "condition": {"months": [8, 9, 10], "year_dependent": False}, "source": src(), "confidence": "施設の解説", "rights": "事実のみ",
         "usage": "種の解説", "homonym": "しもばしら", "sense": "plant"}


class NameQuestion(unittest.TestCase):
    def test_name_question_patterns(self):
        for q in ("枯れた茎に氷ができる。なんというの?", "この花の名前は?", "氷華って何?", "これは何という鳥?"):
            self.assertTrue(NM.is_name_question(q), q)
        for q in ("今週末の紅葉は?", "高尾山の見どころを教えて"):
            self.assertFalse(NM.is_name_question(q), q)

    def test_model_answer_first_sentence(self):
        text = NM.compose("枯れた茎に氷ができる。なんというの?", cards=[ICE, PLANT])
        self.assertTrue(text.startswith(MODEL + "\n"), text)
        self.assertIn("氷の花は例年12月中旬ごろから2月まで", text)
        self.assertNotIn("シソ科の多年草で、高さ", text)                 # 植物の説明に話を移さない(区別のために短く添えるだけ)
        self.assertIn("写真で見比べられるページ(高尾ビジターセンター): " + URL, text)
        self.assertTrue(text.rstrip().endswith(URL))

    def test_unknown_description_is_none(self):
        self.assertIsNone(NM.compose("赤い実がなる木。なんというの?", cards=[ICE]))

    def test_homonym_senses(self):
        ids = [s["id"] for s in NM.homonym_senses("シモバシラ")]
        self.assertEqual(ids, ["ground_frost", "ice_flower", "plant"])
        self.assertEqual({s["id"]: s.get("season") for s in NM.homonym_senses("霜柱")}["plant"], "秋")


class CardSubject(unittest.TestCase):
    def test_subjectless_fact_is_rejected(self):
        bad = dict(ICE, subject=None, subject_aliases=[], place="高尾山", place_aliases=["高尾"], facts=["例年12月中旬ごろから2月まで、枯れた茎に氷ができる"])
        self.assertTrue(any("主語" in e for e in K.validate(bad, strict_subject=True)))
        self.assertEqual(len(K.subject_audit([bad])), 1)

    def test_fact_with_subject_passes(self):
        self.assertEqual([e for e in K.validate(ICE, strict_subject=True) if "主語" in e], [])
        self.assertEqual(K.subject_audit([ICE, PLANT]), [])

    def test_strict_add_requires_subject(self):
        no = {k: v for k, v in ICE.items() if k != "subject"}
        no["subject_aliases"] = []
        self.assertTrue(any("subject" in e for e in K.validate(no, strict_subject=True)))
        self.assertEqual([e for e in K.validate(ICE, strict_subject=True) if "主語" in e or "subject" in e], [])

    def test_retired_cards_are_not_audited(self):
        old = dict(ICE, subject=None, subject_aliases=[], place_aliases=[], facts=["例年12月中旬ごろから2月まで、枯れた茎に氷ができる"], retired={"on": "2026-11-10"})
        self.assertEqual(K.subject_audit([old]), [])


class RouteAndSeasons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        p = Path(self.tmp.name) / "knowledge" / "cards.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in (ICE, PLANT)), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_answer_route_is_name(self):
        from ikimonobiyori import answer_run as AR
        cond = AR.resolve("枯れた茎に氷ができる。なんというの?", NOW)
        self.assertEqual(cond["route"], "name")
        res = AR.run("枯れた茎に氷ができる。なんというの?", now=NOW, env=self.env, workdir=Path(self.tmp.name) / "w")
        self.assertTrue(res["text"].startswith(MODEL), res["text"])
        self.assertNotIn("紅葉", res["text"])

    def test_takao_seasons_list_both_senses_separately(self):
        from ikimonobiyori import highlights as HL
        got = HL.compose("高尾山の見どころを教えて", today=NOW.date(), env=self.env)
        t = got["text"]
        self.assertIn("・氷の花（シモバシラの茎にできる氷）(例年12月中旬〜2月、高尾ビジターセンター)", t)
        self.assertIn("・シモバシラの花(8月下旬〜10月上旬、高尾ビジターセンター)", t)
        aut, win = t.index("### 秋"), t.index("### 冬")
        self.assertTrue(aut < t.index("シモバシラの花(") < win or win < aut < t.index("シモバシラの花("))
        self.assertGreater(t.index("氷の花（シモバシラ"), win)


if __name__ == "__main__":
    unittest.main()
