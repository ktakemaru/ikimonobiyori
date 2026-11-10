"""段階76: 資料の候補の広がり(例年の目安の候補)・テーマのカード・冬季閉鎖・細かい直し。合成データ(通信しない)。"""
import json
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import knowledge as K

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)


def card(title, place, facts, category="種の解説", months=(10, 11, 12), aliases=(), closure=None, subject=None):
    c = {"title": title, "category": category, "place": place, "place_aliases": list(aliases), "facts": list(facts),
         "condition": {"months": list(months), "year_dependent": False},
         "source": {"name": "試験の県", "title": "試験の頁", "url": "https://www.pref.example.lg.jp/" + title, "checked_on": "2026-11-10"},
         "confidence": "公的資料", "rights": "確認済み: 試験。事実のみ・自分の言葉・出典明記", "usage": "ガイドの目として1行",
         "subject": subject or place}
    if closure:
        c["closure"] = closure
    return c


class WithCards(unittest.TestCase):
    """データ置き場(テストの一時フォルダ)の知識カードを、試験のカードに差し替える。"""
    CARDS = []

    def setUp(self):
        self.p = K.path()
        self.old = self.p.read_text(encoding="utf-8") if self.p.exists() else None
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.p.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in self.CARDS), encoding="utf-8")
        GB._HOSTS = None

    def tearDown(self):
        if self.old is None:
            self.p.unlink(missing_ok=True)
        else:
            self.p.write_text(self.old, encoding="utf-8")
        GB._HOSTS = None


class TypicalCandidates(unittest.TestCase):
    def test_covers_wraps_the_year(self):
        self.assertTrue(GB._covers({"start": "11-15", "end": "02-28"}, ["01-10"]))
        self.assertTrue(GB._covers({"start": "10-21", "end": "12-10"}, ["11-14"]))
        self.assertFalse(GB._covers({"start": "06-01", "end": "07-31"}, ["11-14"]))
        self.assertFalse(GB._covers("6月", ["11-14"]))

    def test_group_of(self):
        c = GB.cfg()
        self.assertEqual(GB._group_of("群馬県", c), "栃木・群馬")
        self.assertEqual(GB._group_of("千葉県", c), "埼玉・千葉・茨城")
        self.assertIsNone(GB._group_of("愛知県", c))

    def test_wide_question_has_three_or_more_region_groups(self):
        """段階75 の 3 番: 「遠くても」の資料に、3 つ以上の地域の組の候補が入る(ガイドのカタログの例年の目安から)。"""
        d = GB.build("遠くても構いません。今見られる花と場所を教えて", now=NOW)
        self.assertEqual(d["scope"], "wide")
        groups = {r.get("group") for r in d["candidates"] if r.get("group")}
        self.assertGreaterEqual(len(groups), 3, groups)
        typ = [r for r in d["candidates"] if r.get("basis") == "typical" and r.get("rank") is None]
        self.assertTrue(typ)
        per = {}
        for r in typ:
            per[r["group"]] = per.get(r["group"], 0) + 1
        self.assertLessEqual(max(per.values()), GB.cfg()["typical_candidates"]["per_group"])
        names = {f.get("place") for f in d["facts"] if f["kind"] == "typical"}
        self.assertTrue(all(r["name"] in names for r in typ))

    def test_normal_question_adds_far_typical_candidates_up_to_the_limit(self):
        d = GB.build("今の見頃のものを教えて", now=NOW)
        typ = [r for r in d["candidates"] if r.get("rank") is None]
        self.assertLessEqual(len(typ), GB.cfg()["typical_candidates"]["far_total"])
        self.assertTrue(all(r["group"] != "東京・神奈川" for r in typ))


class ThemeCards(WithCards):
    CARDS = [card("冬桜とは試験", "冬桜", ["冬桜は秋と春に咲く"], months=(10, 11, 12)),
             card("試験の湖の冬鳥", "試験湖", ["試験湖には冬鳥のカモが集まる"], months=(11, 12)),
             card("冬鳥の渡り試験", "冬鳥", ["冬鳥は秋に北から渡ってくる"], months=(10, 11)),
             card("ニッコウキスゲの試験", "試験高原", ["試験高原のニッコウキスゲは7月に咲く"], months=(7,)),
             card("試験の夏鳥", "夏鳥", ["夏鳥は春に渡る"], months=(5, 6))]

    def test_theme_cards_have_links_and_respect_the_season(self):
        d = GB.build("今の見頃のものを教えて", now=NOW)
        by = {k["title"]: k["link"] for k in d["cards"]}
        self.assertEqual(by.get("冬桜とは試験"), GB.cfg()["card_links"]["theme"])
        self.assertEqual(by.get("冬鳥の渡り試験"), GB.cfg()["card_links"]["theme"])
        self.assertNotIn("試験の夏鳥", by)                          # 季節(対象の日の月)が外れる
        self.assertNotIn("試験の湖の冬鳥", by)                      # 特定の場所のカードは一般の話にしない
        self.assertLessEqual(len(d["cards"]), GB.cfg()["max_cards"])

    def test_species_name_in_question_pulls_cards(self):
        d = GB.build("ニッコウキスゲはいつどこへ行けばいい?", now=NOW)
        self.assertIn("ニッコウキスゲの試験", [k["title"] for k in d["cards"]])

    def test_place_question_gets_place_cards_first(self):
        d = GB.build("試験湖にはどんな野鳥がいるの?", now=NOW)
        self.assertEqual(d["cards"][0]["title"], "試験の湖の冬鳥")
        self.assertEqual(d["cards"][0]["link"], GB.cfg()["card_links"]["place"])


class Closures(WithCards):
    CARDS = [card("試験の峠道の冬期閉鎖", "八ヶ岳", ["試験の峠道は例年11月から4月まで冬期閉鎖"], category="安全", months=(11, 12, 1, 2, 3, 4),
                  aliases=["試験の峠道"], subject="試験の峠道",
                  closure={"name": "試験の峠道", "section": "試験町〜試験峠", "areas": ["八ヶ岳"], "typical": "例年11月〜翌4月",
                           "typical_months": [11, 12, 1, 2, 3, 4], "season": {"year": 2026, "text": "令和8年11月19日〜令和9年4月15日(予定)"}}),
             card("試験の高原道路の冬期閉鎖", "試験の高原", ["試験の高原道路は12月から閉鎖"], category="安全", months=(12, 1),
                  subject="試験の高原道路", closure={"name": "試験の高原道路", "areas": ["試験の高原"], "typical": "例年12月〜1月", "typical_months": [12, 1]})]

    def test_closure_is_a_safety_fact_with_the_period_note(self):
        d = GB.build("八ヶ岳の見どころを教えて", now=NOW)
        cl = [f for f in d["facts"] if f["kind"] == "safety" and "冬季閉鎖" in f["content"]]
        self.assertEqual(len(cl), 1)
        self.assertIn("試験の峠道", cl[0]["content"])
        self.assertIn(GB.cfg()["closure_note"]["in_period"], cl[0]["content"])
        self.assertTrue(cl[0]["fields"]["in_target"])
        self.assertNotIn("試験の峠道の冬期閉鎖", [k["title"] for k in d["cards"]])   # 閉鎖はカードの欄に出さない

    def test_closures_for_matches_by_area(self):
        got = GB.closures_for(["試験の高原"], [11], GB.cfg())
        self.assertEqual([(c["title"], hit) for c, hit in got], [("試験の高原道路の冬期閉鎖", False)])
        self.assertEqual(GB.closures_for(["関係のない場所"], [11], GB.cfg()), [])


def brief():
    c = GB.cfg()
    f = {"id": "F001", "kind": "current", "kind_label": c["kinds"]["current"], "place": "試験の渓谷", "content": "試験の渓谷: 見頃(11/9時点)",
         "values": GB.values("試験の渓谷: 見頃(11/9時点)"), "source": "試験町", "source_class": "official", "url": "https://example.org/a",
         "observed": "2026-11-09", "read_at": None}
    g = dict(f, id="F002", url=None, source="URL のない発行元", content="試験の渓谷: 例年 11月中旬", kind="typical",
             values=GB.values("試験の渓谷: 例年 11月中旬"))
    return {"id": "b-test", "question": "今週末の紅葉は?", "dates": {"today": "2026-11-10", "this_weekend": ["2026-11-14", "2026-11-15"],
                                                               "next_weekend": [], "periods": [["2026-11-14", "2026-11-15"]]},
            "candidates": [{"name": "試験の渓谷"}], "facts": [f, g], "cards": [], "fallback": {"text": "x\n"}}


class VerifyFixes(unittest.TestCase):
    PL = "\n\n[場所]\n記録: 試験の渓谷\n"

    def codes(self, body):
        return [e["code"] for e in GV.check(body + self.PL, brief())["errors"]]

    def test_guidance_sentence_is_not_a_question(self):
        self.assertEqual(self.codes("どちらも季節が進むと見え方が変わるので、出かける前に最新の発表をご確認ください。"), [])
        self.assertIn("question_in_answer", self.codes("どちらにしますか。"))
        self.assertIn("question_in_answer", self.codes("ほかの場所も調べましょうか?"))

    def test_target_dates_are_allowed_in_a_marked_sentence(self):
        self.assertEqual(self.codes("今週末(11月14日・15日)の試験の渓谷は、11/9時点で見頃です。[F001]"), [])
        self.assertIn("value_mismatch", self.codes("試験の渓谷は11/10時点で見頃です。[F001]"))

    def test_long_disclaimer_in_the_body_fails(self):
        self.assertIn("long_disclaimer", self.codes("例年は11月中旬が見頃です(紹介サイトの記載で、公式ではありません)。[F002]"))
        self.assertNotIn("long_disclaimer", self.codes("紹介サイトによると、例年は11月中旬が見頃です。[F002]"))

    def test_sources_without_url_are_not_listed(self):
        r = GV.check("試験の渓谷は11/9時点で見頃です。[F001] 例年は11月中旬が見頃です。[F002]" + self.PL, brief())
        self.assertTrue(r["ok"], r["errors"])
        self.assertIn("https://example.org/a", r["final"])
        self.assertNotIn("URL のない発行元", r["final"])

    def test_official_hosts_from_config(self):
        self.assertEqual(GB._source_class("https://www.kirigamine-vc.jp/nature/nikko-kisuge"), "official")


if __name__ == "__main__":
    unittest.main()
