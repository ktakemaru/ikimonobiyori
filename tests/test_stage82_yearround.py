"""段階82 第3部: 季節のない名所(通年)・テーマ(苔)の質問・調べるのは 1 つの質問で 1 回だけ。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import knowledge as K
from ikimonobiyori import research as RS

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=JST)
URL = "https://www.pref.nagano.lg.jp/sakuchi/test-moss.html"


class YearRound(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        RS._save_state("b-test", {"pages": [{"url": URL, "at": NOW.isoformat(), "status": 200}], "first_at": NOW.isoformat(),
                                  "question": "苔がきれいな場所を教えて"}, self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def rec(self, **kw):
        it = {"subject": "flowers", "name": "試験の苔の森", "prefecture": "長野県", "city": "佐久穂町", "kind": "苔", "typical": "通年",
              "closed_period": "例年11月〜翌4月は道路が通行止め", "url": URL, "publisher": "長野県佐久地域振興局"}
        it.update(kw)
        return RS.record([it], "b-test", question="苔がきれいな場所を教えて", env=self.env, now=NOW)

    def test_year_round_is_accepted_with_closed_period(self):
        r = self.rec()
        self.assertEqual((r["written"], r["rejected"]), (1, []))

    def test_current_state_and_event_period_are_still_rejected(self):
        self.assertEqual(self.rec(state="見頃")["written"], 0)
        self.assertEqual(self.rec(typical="まつり期間中(10/1〜10/31)")["written"], 0)
        self.assertEqual(self.rec(typical=None)["written"], 0)

    def test_brief_shows_year_round_and_closure(self):
        self.rec()
        b = GB.build("苔がきれいな場所を教えて", now=NOW, env=self.env)
        self.assertIn("試験の苔の森", [c["name"] for c in b["candidates"]])
        texts = [f["content"] for f in b["facts"]]
        self.assertTrue(any("苔は通年" in t for t in texts), texts)
        self.assertTrue(any(f["kind"] == "safety" and "通行止め" in f["content"] for f in b["facts"]))
        self.assertFalse(any("例年の時期の記載なし" in t and "試験の苔の森" in t for t in texts))

    def test_theme_records_are_not_flower_candidates(self):
        from ikimonobiyori import observations as O
        self.rec()
        self.assertEqual([r for r in O.read_records("flowers", self.env) if r.get("kind") == "苔"], [])
        self.assertEqual(len([r for r in O.read_records("flowers", self.env, include_themes=True) if r.get("kind") == "苔"]), 1)

    def test_research_only_once_per_question(self):
        self.assertTrue(RS.already_researched("苔がきれいな場所を教えて", NOW + timedelta(hours=1), self.env))
        self.assertFalse(RS.already_researched("苔がきれいな場所を教えて", NOW + timedelta(hours=30), self.env))
        self.assertFalse(RS.already_researched("滝の名所", NOW, self.env))
        b = GB.build("苔がきれいな場所を教えて", now=NOW + timedelta(minutes=5), env=self.env)
        self.assertEqual(b["research"]["targets"], [])
        self.assertIn(GB.cfg()["research"]["done_line"], b["missing"])


class Themes(unittest.TestCase):
    def test_themes_of_cards(self):
        self.assertEqual(K.themes_of({"title": "北八ヶ岳の森と池(苔の森)", "facts": []}), ["苔"])
        self.assertEqual(K.themes_of({"title": "ミユビシギ", "facts": ["干潟にすみ、コケや海藻の芽を食べる"]}), [])
        self.assertIn("苔", K.themes_of({"title": "試験の庭", "facts": ["約100種の苔がある", "苔の庭は雨上がりが美しい"]}))

    def test_theme_question_drops_cards_that_only_mention_the_word(self):
        cards = [{"id": "K001", "title": "ミユビシギ", "facts": ["コケや海藻の芽を食べる"]},
                 {"id": "K002", "title": "苔の森", "facts": []}, {"id": "K003", "title": "八ヶ岳の山小屋", "facts": ["山小屋は秋に閉まる"]}]
        self.assertEqual([k["title"] for k in GB._theme_card_filter(cards, "苔がきれいな場所を教えて")], ["苔の森", "八ヶ岳の山小屋"])
        self.assertEqual(len(GB._theme_card_filter(cards, "サザンカの見頃")), 3)          # テーマのない質問はそのまま

    def test_tag_themes_writes_field(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            p = K.path(env)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"title": "苔の森", "facts": []}, ensure_ascii=False) + "\n", encoding="utf-8")
            r = K.tag_themes(env)
            self.assertEqual((r["cards"], r["tagged"]), (1, 1))
            self.assertEqual(K.load(env)[0]["themes"], ["苔"])


if __name__ == "__main__":
    unittest.main()


class RefusedFetchCountsAsResearched(unittest.TestCase):
    """段階82 第3部 4: 公式でないとして読まなかった取得も、その質問で一度調べたことに数える(調べる節を繰り返さない)。"""

    def test_refused(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            b = GB.build("苔がきれいな場所を教えて", now=NOW, env=env)
            GB.brief_dir(env).mkdir(parents=True, exist_ok=True)
            (GB.brief_dir(env) / f"{b['id']}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
            r = RS.fetch("https://example.com/moss", b["id"], env=env, now=NOW, http_get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("通信しない")))
            self.assertFalse(r["ok"])
            self.assertTrue(RS.already_researched("苔がきれいな場所を教えて", NOW + timedelta(minutes=3), env))
