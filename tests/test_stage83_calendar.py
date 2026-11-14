"""段階83 第3部・第4部: 季節の暦(calendar)と小話(tale)のカードの選び方。合成データ(通信しない)。"""
import json
import os
import tempfile
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import knowledge as K

C = GB.cfg()
SRC = {"name": "試験の博物館", "title": "試験", "url": "https://museum.example.org/a", "checked_on": "2026-11-13"}


def cal(title, env, months, target="鳥", facts=("冬の雑木林では試験の鳥が目立つ",)):
    return {"title": title, "category": "出会い方・歩き方", "subject": "試験の鳥", "place": env, "facts": list(facts),
            "narrative": ["どこをどう見る"] * len(facts), "condition": {"months": months, "year_dependent": False},
            "source": SRC, "confidence": "紹介", "rights": "r", "usage": "u",
            "calendar": {"environment": env, "months": months, "target": target, "where": "試験の丘陵"}}


def tale(title, subject, aliases=()):
    return {"title": title, "category": "名前・歴史・文化", "subject": subject, "subject_aliases": list(aliases), "place": subject,
            "facts": [f"{subject}の名前には言い伝えがある"], "narrative": ["小話"], "condition": {"months": [], "year_dependent": False},
            "source": SRC, "confidence": "紹介", "rights": "r", "usage": "u", "tale": {"topic": "名前の由来"}}


class Calendar(unittest.TestCase):
    SHOWN = [cal("冬の雑木林A", "里山・雑木林", [12, 1, 2]), cal("冬の雑木林B", "里山・雑木林", [1]),
             cal("冬の水辺", "水辺", [12, 1]), cal("夏の水辺", "水辺", [7, 8]), cal("冬の公園", "街の公園・庭園", [1, 2]),
             cal("冬の干潟", "干潟・河口", [1])]

    def pick(self, q, months, open_q, cands=(), cond=None):
        return GB.calendar_cards(q, cond or {}, list(cands), months, C, open_q, shown=self.SHOWN)

    def test_environment_and_month_from_question(self):
        got = [k["title"] for k in self.pick("冬の雑木林の楽しみ方を教えて", [11], True)]
        self.assertEqual(got, ["冬の雑木林A", "冬の雑木林B"])          # 「冬の」→ 12〜2月、「雑木林」→ 里山・雑木林だけ

    def test_open_question_mixes_environments_up_to_four(self):
        got = self.pick("今の見頃のものを教えて", [1], True)
        self.assertEqual(len(got), C["calendar"]["max_cards_open"])
        self.assertEqual(len({k["place"] for k in got}), 4)          # 環境ごとに順に 1 枚ずつ
        self.assertTrue(all(k["link"] == C["calendar"]["link"] for k in got))
        self.assertEqual(got[0]["where"], "試験の丘陵")

    def test_place_question_limit_and_skip_routes(self):
        got = self.pick("近くの公園で何が見られる?", [1], False)
        self.assertLessEqual(len(got), C["calendar"]["max_cards"])
        self.assertEqual(self.pick("冬の雑木林", [1], True, cond={"route": "season_place"}), [])
        self.assertEqual(self.pick("河津桜はいつ", [1], False), [])     # 環境の語のない、場所や種を決めた質問には入れない

    def test_have_titles_not_duplicated(self):
        got = GB.calendar_cards("冬の雑木林の楽しみ方", {}, [], [1], C, True, shown=self.SHOWN, have_titles=["冬の雑木林A"])
        self.assertEqual([k["title"] for k in got], ["冬の雑木林B"])

    def test_open_question(self):
        self.assertTrue(GB.is_open_question("今の見頃のものを教えて", {}, c=C))
        self.assertTrue(GB.is_open_question("冬の雑木林の楽しみ方を教えて", {}, c=C))
        self.assertFalse(GB.is_open_question("サザンカの見頃は?", {}, c=C))
        self.assertFalse(GB.is_open_question("今の見頃のものを教えて", {}, towns=["松田町"], c=C))


class Tale(unittest.TestCase):
    SHOWN = [tale("ヒガンバナの呼び名", "ヒガンバナ", ["曼珠沙華"]), tale("サルスベリの名前", "サルスベリ")]

    def test_one_tale_matching_question(self):
        got = GB.tale_cards("曼珠沙華はどこで見られる?", {}, [], [], C, shown=self.SHOWN)
        self.assertEqual([k["title"] for k in got], ["ヒガンバナの呼び名"])
        self.assertEqual(GB.tale_cards("今の見頃は?", {}, [], [], C, shown=self.SHOWN), [])
        cands = [{"name": "サルスベリの並木", "chosen": True}]
        self.assertEqual(len(GB.tale_cards("近くの公園", {}, cands, [], C, shown=self.SHOWN)), C["tale"]["max_cards"])


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.tmp

    def tearDown(self):
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.old

    def test_special_cards_excluded_by_default_and_tags(self):
        plain = {**cal("ふつうのカード", "水辺", [1]), "title": "ふつうのカード"}
        plain.pop("calendar")
        rows = [cal("暦", "水辺", [1]), tale("小話", "ヒガンバナ"), plain]
        p = K.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        self.assertEqual([r["title"] for r in K.load_shown(centers=[])], ["ふつうのカード"])
        self.assertEqual(len(K.load_shown(centers=[], include_special=True)), 3)
        (p.parent / "calendar_tags.jsonl").write_text(json.dumps({"title": "ふつうのカード", "place": "水辺", "environment": "水辺",
                                                                  "months": [1], "target": "鳥", "where": "試験の池"}, ensure_ascii=False) + "\n",
                                                      encoding="utf-8")
        pool = K.calendar_pool(centers=[])
        self.assertEqual(sorted(r["title"] for r in pool), ["ふつうのカード", "暦"])
        self.assertEqual(next(r for r in pool if r["title"] == "ふつうのカード")["calendar"]["where"], "試験の池")

    def test_validate_special_fields(self):
        bad = cal("x", "宇宙", [1])
        self.assertTrue(any("environment" in e for e in K.special_errors(bad)))
        bad = cal("x", "水辺", [13])
        self.assertTrue(any("months" in e for e in K.special_errors(bad)))
        self.assertEqual(K.special_errors(cal("x", "水辺", [1])), [])
        self.assertTrue(K.special_errors({**tale("t", "ウメ"), "tale": {}}))


if __name__ == "__main__":
    unittest.main()
