"""段階79: 観光協会の区分・種が混ざる行・時期の分からない名所・材料の場所・日付のない発信(第1部)、野鳥の候補(第2部)。"""
import unittest
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_materials as GM
from ikimonobiyori import guide_narrative as GN
from ikimonobiyori import publisher as P
from ikimonobiyori import season_place as SP


class TourismAssociation(unittest.TestCase):
    """第1部 1: 発行元の名前が観光協会(観光物産協会・観光連盟・観光コンベンション協会)のホストは「公式」。"""

    def test_names_in_catalog_make_hosts_official(self):
        self.assertTrue(P.shows_official("https://visit-chiyoda.tokyo/app/spot/detail/800"))      # 千代田区観光協会(名所カタログの題名)
        self.assertTrue(P.shows_official("https://www.kanuma-kanko.jp/"))                         # 鹿沼市観光協会

    def test_note_mentions_do_not_count(self):
        # 注記の「確認元は八王子観光コンベンション協会」は数えない(紹介サイト)
        self.assertFalse(P.shows_official("https://www.enjoytokyo.jp/article/109052/"))

    def test_name_rule(self):
        pairs = []
        P._walk_names({"url": "https://a.example.jp/x", "title": "試験町観光協会 桜まつり"}, pairs)
        P._walk_names({"url": "https://b.example.jp/x", "publisher": "一般社団法人試験市観光物産協会"}, pairs)
        self.assertEqual(pairs, [("a.example.jp", "試験町観光協会"), ("b.example.jp", "一般社団法人試験市観光物産協会")])


class MixedKinds(unittest.TestCase):
    """第1部 2: 1 つの名所に時期の違う種があれば、種ごとの行(その時期に当たる種だけ)。"""

    def test_sakurayama_rows_per_kind(self):
        sp = SP.resolve_all("桜の名所を教えて")[0]
        rows = [r for r in SP.gather(sp, "横浜") if r["name"] == "桜山公園"]
        by = {tuple(r["kinds"]): r for r in rows}
        self.assertIn(("冬桜",), by)
        self.assertIn(("河津桜",), by)
        self.assertTrue(by[("冬桜",)]["start"].startswith("11"))
        self.assertTrue(by[("河津桜",)]["start"].startswith("02"))

    def test_kind_without_window_is_not_mixed(self):
        sp = SP.resolve_all("桜の名所を教えて")[0]
        ueno = [r for r in SP.gather(sp, "横浜") if r["name"] == "上野恩賜公園" and r.get("season")]
        self.assertTrue(ueno)
        self.assertNotIn("寒桜", ueno[0]["kinds"])

    def test_record_of_other_kind_gets_its_own_row(self):
        rows = {"x": {"kinds": ["ソメイヨシノ"], "season": "3月下旬"}}
        self.assertTrue(SP._other_kind({"kinds": ["寒桜"]}, rows["x"], {"name": "桜"}))
        self.assertFalse(SP._other_kind({"kinds": ["桜"]}, rows["x"], {"name": "桜"}))
        self.assertFalse(SP._other_kind({"kinds": ["ソメイヨシノ"]}, rows["x"], {"name": "桜"}))


def _row(name, start, season="試験", kinds=("スイセン",)):
    return {"name": name, "prefecture": "東京都", "city": "試験市", "km": 30, "km_estimated": False, "kinds": list(kinds),
            "start": start, "end": start, "season": season, "url": None, "official": True}


class UnknownSeason(unittest.TestCase):
    """第1部 3: 時期の分かる名所が 4 件以上なら、時期の記載のない名所は資料に入れない。"""

    def test_dropped_when_enough_known(self):
        rows = [_row(f"既{i}", "01-11") for i in range(4)] + [_row("不明", None, None)]
        with mock.patch.object(SP, "gather", return_value=rows):
            got = GM.species_rows("スイセンの名所を教えて", {"route": "season_place", "origin": "横浜", "defaulted_date": True})
        self.assertNotIn("不明", [r["name"] for r in got])

    def test_kept_when_few_known(self):
        rows = [_row(f"既{i}", "01-11") for i in range(3)] + [_row("不明", None, None)]
        with mock.patch.object(SP, "gather", return_value=rows):
            got = GM.species_rows("スイセンの名所を教えて", {"route": "season_place", "origin": "横浜", "defaulted_date": True})
        self.assertIn("不明", [r["name"] for r in got])


class MaterialPlace(unittest.TestCase):
    """第1部 4: 語りの材料が特定の場所の話なら、都県と市区町村を付ける。"""

    def test_card_city(self):
        self.assertEqual(GN.place_label({"place": "試験川", "prefecture": "東京都", "city": "試験市"}), "試験川・東京都試験市")

    def test_alias_is_a_city(self):
        with mock.patch.object(GN, "_place_index", return_value={"どこか": ("東京都", "あきる野市")}):
            self.assertEqual(GN.place_label({"place": "養沢川", "place_aliases": ["あきる野"]}), "養沢川・東京都あきる野市")

    def test_wide_place_gets_prefecture_only(self):
        with mock.patch.object(GN, "_place_index", return_value={"霞ヶ浦": ("茨城県", "稲敷市")}):
            self.assertEqual(GN.place_label({"place": "霞ヶ浦"}), "霞ヶ浦・茨城県")

    def test_general_story_unchanged(self):
        with mock.patch.object(GN, "_place_index", return_value={}):
            self.assertEqual(GN.place_label({"place": "渡り鳥"}), "渡り鳥")


class UndatedCurrent(unittest.TestCase):
    """第1部 5: 日付のない今年の現況は、いつの記録か分からないと事実の文に書く。"""

    def test_wording(self):
        from ikimonobiyori import guide_brief as GB
        F = GB._Facts(GB.cfg(), set())
        GB._candidate_facts(F, {"name": "試験公園", "current": {"state_raw": "2026年の試験公園(45種)", "publisher": "試験の会", "url": None}})
        txt = F.rows[0]["content"]
        self.assertIn("いつの記録かは資料にない", txt)
        self.assertNotIn("日付なし", txt)


if __name__ == "__main__":
    unittest.main()


def _card(place, months, facts, title=None):
    return {"title": title or f"{place}の試験", "category": "シーズンの目安", "place": place, "place_aliases": [], "facts": facts,
            "condition": {"months": months}, "source": {"name": "試験", "url": "https://www.city.example.lg.jp/x", "checked_on": "2026-11-11"}}


class BirdHighlights(unittest.TestCase):
    """第2部: 範囲の指定がない野鳥の質問に、季節の目玉がある観察地(地域の組が偏らないように 4〜6 件)と目玉の材料。"""

    def setUp(self):
        from ikimonobiyori import guide_brief as GB
        self.GB = GB
        self.c = GB.cfg()
        self.cards = [_card(s["card_place"], [11, 12, 1, 2], [f"{s['card_place']}では冬に{s['label']}が見られる"]) for s in self.c["bird_highlights"]["sites"]]

    def _run(self, question, cond):
        from ikimonobiyori import knowledge as K
        with mock.patch.object(K, "load_shown", return_value=self.cards):
            return self.GB.bird_highlights(question, cond, {}, [11], [], self.c)

    def test_groups_spread(self):
        hl = self._run("野鳥のおすすめを教えて", {"subjects": ["birds"]})
        self.assertGreaterEqual(len(hl), 4)
        self.assertLessEqual(len(hl), 6)
        self.assertGreaterEqual(len({h["group"] for h in hl}), 3)
        self.assertGreaterEqual(len({h["theme"] for h in hl}), 4)
        self.assertTrue(all(h["cards"] for h in hl))

    def test_not_for_region_or_species(self):
        self.assertEqual(self._run("千葉の野鳥のおすすめ", {"subjects": ["birds"], "region": "千葉"}), [])
        self.assertEqual(self._run("紅葉のおすすめ", {"subjects": ["autumn_leaves"]}), [])

    def test_out_of_season_sites_are_skipped(self):
        self.cards = [_card(s["card_place"], [6], ["夏の話"]) for s in self.c["bird_highlights"]["sites"]]
        self.assertEqual(self._run("野鳥のおすすめを教えて", {"subjects": ["birds"]}), [])

    def test_materials_one_per_site(self):
        hl = self._run("野鳥のおすすめを教えて", {"subjects": ["birds"]})
        cards = self.GB._add_highlight_cards([], hl, self.c)
        mat = self.GB._highlight_materials({"items": [], "missing": []}, cards, hl, self.c)
        kind = self.c["bird_highlights"]["material_kind"]
        got = [i for i in mat["items"] if i["kind"] == kind]
        self.assertEqual(len(got), len(hl))
        self.assertIn("・", got[0]["place"])
        self.assertIn(f"### {kind}", "\n".join(GN.render(mat)))


class BirdHighlightsWords(BirdHighlights):
    def test_migrant_word_is_not_a_place(self):
        self.assertGreaterEqual(len(self._run("渡り鳥はどこで見られる?", {"subjects": ["birds"]})), 4)
