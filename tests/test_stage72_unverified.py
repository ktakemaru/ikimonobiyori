"""段階72 第5部: 一般に知られた名所を「未確認」として添える。合成データ(通信しない)。"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import unverified as U

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)
HEAD = "ほかに知られている名所（今年の情報・出典は未確認）"
ANSWER = "今回のおすすめ\n① 試験の梅園 約30km\n・今の状況は咲き始め(11/9時点、試験町)\n\n出典\nhttps://example.org/a\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()


class Record(Base):
    def test_detail_fields_are_rejected(self):
        out = U.record([{"name": "試験梅林", "prefecture": "埼玉県", "phone": "03-0000-0000"},
                        {"name": "試験梅林 入園500円", "prefecture": "埼玉県"},
                        {"name": "試験梅林", "prefecture": "埼玉県", "theme": "梅 3月1日開園"},
                        {"name": "試験梅林", "prefecture": "埼玉県", "fee": 300, "trees": 1000}], env=self.env, now=NOW)
        self.assertEqual(out["written"], 0)
        self.assertEqual(len(out["rejected"]), 4)

    def test_out_of_range_is_rejected(self):
        out = U.record([{"name": "試験の名古屋の梅", "prefecture": "愛知県", "theme": "梅"},
                        {"name": "試験の会津の梅", "prefecture": "福島県", "theme": "梅"},
                        {"name": "試験の北海道の梅", "prefecture": "北海道", "theme": "梅"}], env=self.env, now=NOW)
        self.assertEqual(out["written"], 0)
        ok = U.record([{"name": "試験の白河の梅", "prefecture": "福島県", "city": "白河市", "theme": "梅"}], env=self.env, now=NOW)
        self.assertEqual(ok["written"], 1)

    def test_record_keeps_only_allowed_fields(self):
        U.record([{"name": "試験梅林", "prefecture": "埼玉県", "city": "試験市", "theme": "梅", "months": [2, 3]}], env=self.env, now=NOW)
        row = U.load(self.env)[0]
        self.assertEqual(set(row) - {"source", "recorded_at"}, {"name", "prefecture", "city", "theme", "months"})
        self.assertEqual(row["source"], "一般に知られた名所（未確認）")
        self.assertTrue((Path(self.tmp.name) / "unverified" / "spots.jsonl").exists())


class Attach(Base):
    def add(self, n=7):
        U.record([{"name": f"試験梅林{i}", "prefecture": "埼玉県", "theme": "梅", "months": [2, 3]} for i in range(n)]
                 + [{"name": "試験の紅葉谷", "prefecture": "栃木県", "theme": "紅葉", "months": [11]}], env=self.env, now=NOW)

    def test_section_after_picks_and_not_in_sources(self):
        self.add()
        t = U.attach(ANSWER, "梅の名所は?", env=self.env)
        self.assertIn(HEAD, t)
        self.assertLess(t.index("今回のおすすめ"), t.index(HEAD))
        self.assertLess(t.index(HEAD), t.index("\n出典\n"))
        src = t[t.index("\n出典\n"):]
        self.assertNotIn("試験梅林", src)
        self.assertIn("・試験梅林0(埼玉県、例年2月・3月)", t)
        self.assertEqual(sum(1 for l in t.splitlines() if l.startswith("・試験梅林")), 5)
        self.assertNotIn("試験の紅葉谷", t)                          # テーマが違う

    def test_no_details(self):
        self.add(1)
        t = U.attach(ANSWER, "梅の名所は?", env=self.env)
        sec = t[t.index(HEAD):t.index("\n出典\n")]
        for w in ("円", "本", "電話", "http"):
            self.assertNotIn(w, sec)

    def test_verified_is_not_shown(self):
        self.add(1)
        self.assertTrue(U.verify("試験梅林0", "埼玉県", env=self.env, now=NOW))
        self.assertEqual(U.attach(ANSWER, "梅の名所は?", env=self.env), ANSWER)

    def test_prefecture_filter(self):
        self.add(1)
        self.assertEqual(U.attach(ANSWER, "梅の名所は?", prefectures={"神奈川県"}, env=self.env), ANSWER)

    def test_already_in_answer_is_not_repeated(self):
        U.record([{"name": "試験の梅園", "prefecture": "埼玉県", "theme": "梅"}], env=self.env, now=NOW)
        self.assertEqual(U.attach(ANSWER, "梅の名所は?", env=self.env), ANSWER)


class Route(Base):
    def test_answer_has_section_and_research_targets(self):
        from ikimonobiyori import answer_run as AR
        U.record([{"name": f"試験梅林{i}", "prefecture": "埼玉県", "theme": "梅", "months": [2]} for i in range(3)], env=self.env, now=NOW)
        res = AR.run("梅の名所と時期を教えて", now=NOW, env=self.env, workdir=Path(self.tmp.name) / "w")
        self.assertIn(HEAD, res["text"])
        picks = res["text"].split(HEAD)[0]
        self.assertNotIn("試験梅林", picks)
        self.assertEqual([t["where"] for t in res["research_targets"] if t["what"] == "未確認の名所の確認"], ["試験梅林0", "試験梅林1"])


if __name__ == "__main__":
    unittest.main()
