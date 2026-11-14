"""段階84 第1部: 段階83 の判断の反映と追加の直し(A〜E)。合成データ(通信しない)。"""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_materials as GM
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import season_place as SP
from ikimonobiyori import seasonal_obs as SO
from ikimonobiyori.fetch import ParseError

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=JST)
NL = chr(10)


def _sp(tid, sci, ja, iconic, n):
    return {"count": n, "taxon": {"id": tid, "name": sci, "preferred_common_name": ja, "iconic_taxon_name": iconic}}


def fake_get(calls):
    def get(url):
        calls.append(url)
        if "/taxa/" in url:
            ids = [int(x) for x in urlsplit(url).path.rsplit("/", 1)[1].split(",")]
            anc = {5: [1, 47158, 47792, 5], 8: [1, 47158, 47224, 8], 9: [1, 47158, 9]}
            return 200, json.dumps({"results": [{"id": i, "ancestor_ids": anc.get(i, [1, i])} for i in ids]}), {}
        q = parse_qs(urlsplit(url).query)
        if "/histogram" in url:
            return 200, json.dumps({"results": {"week_of_year": {str(w): 10 for w in range(1, 53)}}}), {}
        if "term_id" in q:
            return 200, json.dumps({"results": [_sp(1, "Farfugium japonicum", "ツワブキ", "Plantae", 4)]}), {}
        if "Aves" in q["iconic_taxa"][0]:
            res = [_sp(1, "Farfugium japonicum", "ツワブキ", "Plantae", 9), _sp(2, "Hypsipetes amaurotis", "ヒヨドリ", "Aves", 8)]
        else:
            res = [_sp(5, "Sympetrum frequens", "アキアカネ", "Insecta", 9), _sp(8, "Zizeeria maha", "ヤマトシジミ", "Insecta", 9),
                   _sp(9, "Tenodera aridifolia", "オオカマキリ", "Insecta", 9)]
        return 200, json.dumps({"results": res}), {}
    return get


class TmpData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.tmp
        SO._VOCAB.clear()

    def tearDown(self):
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.old
        SO._VOCAB.clear()


class Region(TmpData):
    def test_niigata_group_is_niigata_and_fukushima(self):
        r = SO.region("niigata_s_tohoku")
        self.assertEqual(r["place_ids"], [13081, 10910])                 # 宮城・山形を外した(本人の判断 2026-11-13 の 2)
        self.assertEqual(SO.region_label(r), "新潟・福島")
        self.assertIs(SO.region("新潟・南東北"), r)                       # guide_mode の地域の組の名前で引ける

    def test_saved_before_change_is_refetched(self):
        r = SO.region("niigata_s_tohoku")
        years = SO.years_for(NOW)
        old = {"fetched_at": "2026-11-13T09:00:00+09:00", "years": years}
        self.assertFalse(SO.fresh(old, NOW, reg=r))                       # 地域の組を変える前に取った保存
        self.assertTrue(SO.fresh({**old, "fetched_at": NOW.isoformat()}, NOW, reg=r))
        self.assertFalse(SO.fresh({**old, "fetched_at": NOW.isoformat(), "place_ids": [13081, 10910, 10939]}, NOW, reg=r))
        tk = SO.region("tokyo_kanagawa")
        self.assertTrue(SO.fresh(old, NOW, reg=tk))                       # ほかの組の古い保存はそのまま使う

    def test_fetch_saves_place_ids(self):
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["niigata_s_tohoku"], weeks=[46])
        saved = json.loads(SO.week_path("niigata_s_tohoku", 46).read_text(encoding="utf-8"))
        self.assertEqual(saved["place_ids"], [13081, 10910])
        self.assertIn("place_id=13081%2C10910&", calls[-1])


class Insects(TmpData):
    def _fill(self):
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["tokyo_kanagawa"], weeks=[46, 47, 48])
        return calls

    def test_taxa_lookup_splits_insects(self):
        self._fill()
        self.assertEqual(SO.missing_taxa(), [5, 8, 9])
        calls = []
        out = SO.run_taxa(NOW, fake_get(calls), lambda: 5 - len(calls))
        self.assertEqual((out["done"], out["left"], len(calls)), (3, 0, 1))
        self.assertEqual(SO.load_taxa_groups(), {"5": "dragonflies", "8": "butterflies", "9": "other_insects"})
        win = SO.species_window("tokyo_kanagawa", date(2026, 11, 18))
        self.assertEqual([r["name"] for r in win["categories"]["dragonflies"]], ["アキアカネ"])
        self.assertEqual([r["name"] for r in win["categories"]["butterflies"]], ["ヤマトシジミ"])
        self.assertEqual([r["name"] for r in win["categories"]["other_insects"]], ["オオカマキリ"])

    def test_taxa_parse_rejects_bad_shape(self):
        for bad in ({}, {"results": [{"id": 1}]}, {"results": [{"id": "1", "ancestor_ids": []}]}):
            with self.assertRaises(ParseError):
                SO.parse_taxa(bad)

    def test_question_words_pick_lines(self):
        self._fill()
        SO.run_taxa(NOW, fake_get([]), lambda: 9)
        cond = {"origin": "横浜", "periods": [["2026-11-18"]]}

        def cats(q):
            return [r["category"] for r in GB.seasonal_rows(q, cond, [], NOW, None, GB.cfg())]
        self.assertEqual(cats("今の時期に見られるチョウやトンボは?"), ["dragonflies", "butterflies"])
        self.assertEqual(cats("今ごろ見られる虫は?"), ["dragonflies", "butterflies", "other_insects"])
        self.assertIn("insects", cats("今の見頃のものを教えて"))                    # 全分類の質問は虫を 1 行のまま

    def test_brief_shows_dragonfly_line_even_when_few(self):
        self._fill()
        SO.run_taxa(NOW, fake_get([]), lambda: 9)
        groups = SO.load_taxa_groups()
        groups.pop("5")
        groups["5"] = "other_insects"                                    # トンボが上位にない週の形
        SO._write(SO.taxa_path(), {"fetched_at": NOW.isoformat(), "groups": groups})
        cond = {"origin": "横浜", "periods": [["2026-11-18"]]}
        rows = GB.seasonal_rows("今の時期に見られるチョウやトンボは?", cond, [], NOW, None, GB.cfg())
        by = {r["category"]: r for r in rows}
        self.assertEqual(set(by), {"dragonflies", "butterflies"})
        self.assertIn("記録は少ない", by["dragonflies"]["content"])
        self.assertEqual(by["dragonflies"]["species"], [])
        self.assertIn("ヤマトシジミ", by["butterflies"]["content"])

    def test_without_taxa_table_insects_stay_one_line(self):
        self._fill()
        cond = {"origin": "横浜", "periods": [["2026-11-18"]]}
        rows = GB.seasonal_rows("今の時期に見られるチョウやトンボは?", cond, [], NOW, None, GB.cfg())
        self.assertEqual([r["category"] for r in rows], ["insects"])


class SpeciesDictionary(TmpData):
    def _vocab(self, names):
        SO._write(SO.week_path("tokyo_kanagawa", 46), {"categories": {"plants": [{"ja": n, "sci": n, "count": 1} for n in names]}})
        SO._VOCAB.clear()

    def test_tsuwabuki_is_a_species_question(self):
        self._vocab(["ツワブキ", "ヒヨドリ"])
        self.assertEqual(SO.species_in_question("ツワブキはどこで見られる?"), ["ツワブキ"])
        self.assertEqual(GM.species_match_words("ツワブキはどこで見られる?"), ["ツワブキ"])
        self.assertFalse(GB.is_open_question("ツワブキはどこで見られる?", {}))

    def test_short_names_not_confused(self):
        self._vocab(["アキアカネ", "アカネ", "ハクセキレイ", "セキレイ", "カモ", "トンボ"])
        self.assertEqual(SO.species_in_question("アキアカネはどこ?"), ["アキアカネ"])       # 長い名前の中の短い名前は数えない
        self.assertEqual(SO.species_in_question("ハクセキレイとセキレイ"), ["ハクセキレイ", "セキレイ"])
        self.assertEqual(SO.species_in_question("カモメを見たい"), [])                       # 2 文字(カモ)は辞書に入れない
        self.assertEqual(SO.species_in_question("トンボを見たい"), [])                       # 分類の語は種にしない
        self.assertEqual(SO.species_in_question("ミヤマアカネを探す"), [])                   # 前後がカタカナの一致は数えない

    def test_species_question_keeps_only_its_category(self):
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["tokyo_kanagawa"], weeks=[46, 47, 48])
        SO._VOCAB.clear()
        cond = {"origin": "横浜", "periods": [["2026-11-18"]]}
        rows = GB.seasonal_rows("ツワブキはどこで見られる?", cond, [], NOW, None, GB.cfg())
        self.assertEqual([r["category"] for r in rows], ["plants"])

    def test_asked_species_pinned_and_split_filtered(self):
        calls = []
        SO.run_fetch(NOW, fake_get(calls), lambda: 999, regions=["tokyo_kanagawa"], weeks=[46, 47, 48])
        SO.run_taxa(NOW, fake_get([]), lambda: 9)
        SO._VOCAB.clear()
        cond = {"origin": "横浜", "periods": [["2026-11-18"]]}
        old = SO.load_policy()["brief"]["max_per_category"]
        SO.load_policy()["brief"]["max_per_category"] = {"value": 1}
        try:
            rows = GB.seasonal_rows("オオカマキリはどこで見られる?", cond, [], NOW, None, GB.cfg())
        finally:
            SO.load_policy()["brief"]["max_per_category"] = old
        self.assertEqual([r["category"] for r in rows], ["other_insects"])  # 種のある行だけ(分けた虫の行)
        self.assertEqual(rows[0]["species"], ["オオカマキリ"])               # 上位 1 種の外でも、聞かれた種を先頭に
        rows = GB.seasonal_rows("秋の虫、アキアカネはどこ?", cond, [], NOW, None, GB.cfg())
        self.assertEqual([r["category"] for r in rows], ["dragonflies"])     # 分けたあとも、その種のある行だけ

    def test_catalog_species_unchanged(self):
        base = GM.species_match_words("桜はどこで見られる?")
        self._vocab(["ヤマザクラ"])
        self.assertEqual(GM.species_match_words("桜はどこで見られる?"), base)          # 種の表で引ける種はそのまま


class Traits(unittest.TestCase):
    def errs(self, text):
        return [e["code"] for e in GV.trait_errors(GV.sentences([text]), {}, GV.cfg())]

    def test_color_size_without_card_blocked(self):
        self.assertIn("trait_without_card", self.errs("白い大きな鳥がいたら、ハクチョウです。"))

    def test_marked_sentence_checks_only_clause_species(self):
        brief = {"cards": [{"id": "K001", "title": "冬桜と寒桜の違い", "facts": ["冬桜は白から淡紅色の一重小輪の花", "寒桜は1〜2月に咲く淡紅色の一重で、冬桜とは別の種"]}]}
        s = GV.sentences(["冬桜は白から淡紅色の一重の小さな花で、1〜2月に咲く寒桜とは別の種です [K001]。"])
        self.assertEqual([e["code"] for e in GV.trait_errors(s, brief, GV.cfg())], [])   # 比べ相手(寒桜)の節には色・大きさの語がない

    def test_omoshiroi_is_not_color(self):
        self.assertEqual(self.errs("鳥では、ホオジロの仲間のすみ分けが面白いところです。"), [])


class MountainSite(unittest.TestCase):
    def test_norikura_links_to_site(self):
        st = SP.mountain_site("乗鞍岳(畳平周辺)")
        self.assertEqual(st["name"], "乗鞍岳(剣ヶ峰)")
        self.assertIsNone(SP.mountain_site("乗鞍高原"))

    def test_verify_allows_prefecture_of_mountain_candidate(self):
        brief = {"question": "チングルマはいつどこで見られる?", "facts": [], "cards": [],
                 "candidates": [{"name": "乗鞍岳(畳平周辺)", "prefecture": "岐阜県", "mountain_site": "乗鞍岳(剣ヶ峰)"}]}
        draft = "チングルマは、乗鞍岳(岐阜県高山市)の畳平周辺でも見られます。" + NL
        codes = [e["code"] for e in GV.check(draft, brief)["errors"]]
        self.assertNotIn("out_of_range", codes)                          # 岐阜県は照合の範囲の県(範囲の地図)の内


class SecondarySeasonWhenOfficialHasNone(unittest.TestCase):
    def test_secondary_line_kept(self):
        guide = [{"name": "試験の遊水地", "prefecture": "栃木県", "municipality": "栃木市", "theme": "野鳥",
                  "kinds": [{"kind": "チュウヒ"}],
                  "season": {"text": "11〜2月", "window": {"start": "11-01", "end": "02-29"}, "shown": False, "from_url": "https://spots.example.com/1"},
                  "sources": [{"url": "https://spots.example.com/1", "class": "C"}]}]
        rec = [{"name": "試験の遊水地", "prefecture": "栃木県", "city": "栃木市", "kinds": ["チュウヒ"], "start": None, "end": None,
                "season": None, "url": "https://www.city.example.lg.jp/a", "official": True, "publisher": "試験市", "from": "record"}]
        old = (SP._flower_entries, SP._guide_entries, SP._records)
        SP._flower_entries, SP._guide_entries, SP._records = (lambda: []), (lambda: guide), (lambda *a, **k: rec)
        try:
            rows = SP.gather({"name": "チュウヒ", "match": ["チュウヒ"], "words": ["チュウヒ"], "includes": []}, "横浜")
        finally:
            SP._flower_entries, SP._guide_entries, SP._records = old
        r = rows[0]
        self.assertTrue(r["official"])
        self.assertIsNone(r["season"])
        self.assertEqual(r["url"], "https://www.city.example.lg.jp/a")
        self.assertEqual(r["secondary_season"]["season"], "11月上旬〜2月下旬")
        self.assertEqual(r["secondary_season"]["url"], "https://spots.example.com/1")


if __name__ == "__main__":
    unittest.main()
