"""段階72 第7部: 11/10 の会話の質問の回帰テスト。合成データ(通信しない。書き込みは一時フォルダだけ)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import answer_run as AR
from ikimonobiyori import final_check as FC
from ikimonobiyori import observations as O

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)
MODEL = "**氷の花（氷華）**と呼ばれます。高尾山では、シモバシラというシソ科の植物の枯れた茎にできるので、その名前で呼ばれることもあります（地面にできる霜柱とは別のものです）。"
ICE = {"title": "氷の花（シモバシラの茎にできる氷）", "subject": "氷の花", "category": "シーズンの目安", "place": "高尾山", "place_aliases": ["シモバシラ"],
       "facts": ["氷の花は例年12月中旬ごろから2月まで見られ、大きいものは1月上旬まで"], "condition": {"months": [12, 1, 2], "year_dependent": False},
       "source": {"name": "高尾ビジターセンター", "url": "https://takaovc.ces-net.jp/?page_id=753", "checked_on": "2026-11-10"},
       "confidence": "施設の解説", "rights": "事実のみ", "usage": "名前の質問", "homonym": "しもばしら", "sense": "ice_flower"}


class Conversation1110(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        p = Path(self.tmp.name) / "knowledge" / "cards.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(ICE, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_q(self, q):
        res = AR.run(q, now=NOW, env=self.env, workdir=Path(self.tmp.name) / ("w" + str(abs(hash(q)))))
        return res

    def clean(self, res):
        r = FC.check(res["text"], res["text"])
        self.assertEqual(r["removed"], [], res["text"])            # 送る前の検査で消える文がない

    def test_ice_flower_name(self):
        res = self.run_q("枯れた茎に氷ができる。なんというの?")
        self.assertTrue(res["text"].startswith(MODEL + "\n"), res["text"])
        self.clean(res)

    def test_kasumigaura(self):
        res = self.run_q("霞ヶ浦にはどんな野鳥がいるの?")
        self.assertNotIn("箱根", res["text"])
        self.assertIn("霞ヶ浦", [t["where"] for t in res["research_targets"]])
        self.clean(res)

    def test_omiya_south_plant(self):
        res = self.run_q("大宮南部浄化センター付近には野鳥はいませんか?")
        self.assertNotIn("横浜", res["text"])
        self.assertIn("大宮南部浄化センター", [t["where"] for t in res["research_targets"]])

    def test_far_is_fine(self):
        q = "遠くても構いません。今見られる花と場所を教えて"
        cond = AR.resolve(q, NOW)
        self.assertEqual(AP.scope_of(q, cond["origin_source"], cond["refine"]), "wide")
        res = self.run_q(q)
        self.assertNotIn("近場で手軽に", res["text"])

    def test_autumn_and_susuki_weekend(self):
        q = "今週末に紅葉やススキ、そのほか秋を満喫できそうなところ教えて"
        cond = AR.resolve(q, NOW)
        self.assertEqual(AP.scope_of(q, cond["origin_source"], cond["refine"]), "no_origin")
        res = self.run_q(q)
        self.assertTrue(res["text"].strip())
        self.assertNotIn("近場で手軽に", res["text"])
        plan = Path(res["workdir"]) / "answer_plan.json"
        if plan.exists():
            picks = json.loads(plan.read_text(encoding="utf-8")).get("picks") or []
            prefs = [p.get("prefecture") for p in picks if p.get("prefecture")]
            if len(set(prefs)) > 1 or len(prefs) < 3:
                self.assertLessEqual(max([prefs.count(x) for x in prefs] or [0]), 2)

    def test_akiruno_fireflies(self):
        O.record([{"subject": "flowers", "name": "試験川(試験院周辺)", "city": "あきる野市", "prefecture": "東京都", "kind": "ホタル", "state": "",
                   "typical": "例年ですと、試験川全体で7月上旬までホタルをみることができます", "url": "https://example.org/p1251",
                   "publisher": "試験の観光協会", "source_class": "official", "basis": "page", "source_year": 2014}], env=self.env, now=NOW)
        res = self.run_q("あきる野市でホタルが見られるところと時期は?")
        self.assertIn("2014年の記載では、7月上旬まで", res["text"])
        self.assertNotIn("〜7月上旬", res["text"])
        self.clean(res)


if __name__ == "__main__":
    unittest.main()
