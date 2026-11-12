"""段階82 第1部: 種の名前の読み替え(ひらがな・カタカナ・漢字を同じ種に)。合成のカードとリポジトリのカタログ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_answer_page as GAP
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import season_place as SP
from ikimonobiyori import species_alias as SA

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=JST)

CARD = {"title": "試験の見分け方(サザンカ)", "category": "種の解説", "subject": "サザンカ", "place": "国営昭和記念公園",
        "facts": ["国営昭和記念公園では、サザンカが10月下旬〜2月下旬に園内各所で咲く", "花の似ているツバキは花ごと落ちるのに対して、サザンカは花びらが1枚ずつ散る"],
        "narrative": ["見分け方"], "condition": {"months": [11, 12, 1, 2], "year_dependent": False},
        "source": {"name": "試験の公園事務所", "title": "花ごよみ", "url": "https://www.showakinen-koen.jp/flower-information/", "checked_on": "2026-11-11"},
        "confidence": "施設の解説", "rights": "事実のみ・自分の言葉・出典明記", "usage": "ガイドの目として1行"}


class Normalize(unittest.TestCase):
    def test_hiragana_and_kanji_become_katakana(self):
        self.assertEqual(SA.normalize("さざんかの見頃と見どころを教えて")[0], "サザンカの見頃と見どころを教えて")
        self.assertEqual(SA.normalize("山茶花と椿の違い")[0], "サザンカとツバキの違い")
        self.assertEqual(SA.normalize("こきあの時期")[0], "コキアの時期")
        self.assertEqual(SA.normalize("おおたかを見たい")[0], "オオタカを見たい")

    def test_katakana_is_unchanged(self):
        self.assertEqual(SA.normalize("サザンカの見頃")[0], "サザンカの見頃")
        self.assertEqual(SA.normalize("サザンカの見頃")[1], [])

    def test_words_in_the_existing_table_are_left_to_the_table(self):
        for q in ("あじさいの名所", "梅の名所と時期", "紫陽花の名所", "彼岸花はどこ"):
            self.assertEqual(SA.normalize(q)[0], q)                 # 今までの表で引ける(答えを変えない)

    def test_part_of_a_longer_known_word_is_not_rewritten(self):
        self.assertEqual(SA.normalize("椿寒桜はどこで見られる?")[0], "椿寒桜はどこで見られる?")

    def test_no_mix_ups(self):
        for q in ("もみじの見頃", "ふじさんの紅葉", "かもを見たい", "話をきくと楽しい", "しめ縄", "不思議な花"):
            self.assertEqual(SA.normalize(q)[0], q, q)
        self.assertEqual([x["name"] for x in SP.resolve_all("ふじさんの紅葉")], [])           # 「ふじ」を藤にしない
        self.assertEqual([x["name"] for x in SP.resolve_all("秋はすすきの名所")], ["ススキ"])   # 「はす」を蓮にしない
        self.assertEqual([x["name"] for x in SP.resolve_all("話をきくと楽しい")], [])          # 「きく」を菊にしない
        self.assertEqual([x["name"] for x in SP.resolve_all("ふじの名所")], ["藤"])
        self.assertEqual([x["name"] for x in SP.resolve_all("うめの名所と時期")], ["梅"])
        self.assertEqual([x["name"] for x in SP.resolve_all("きくの名所")], ["菊"])

    def test_two_catalog_species_in_one_question(self):
        self.assertEqual([x["name"] for x in SP.resolve_all("ツバキとサザンカの違い")], ["ツバキ", "サザンカ"])


class Brief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        from ikimonobiyori import knowledge as K
        self.kp = K.path()                       # 資料のカードは既定の置き場所(テストでは tests/nonet.py の一時フォルダ)から読む
        self.kp_old = self.kp.read_text(encoding="utf-8") if self.kp.exists() else None
        self.kp.parent.mkdir(parents=True, exist_ok=True)
        self.kp.write_text(json.dumps(CARD, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        if self.kp_old is None:
            self.kp.unlink()
        else:
            self.kp.write_text(self.kp_old, encoding="utf-8")
        self.tmp.cleanup()

    def _title(self, b):
        d = GB.brief_dir(self.env)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{b['id']}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        return GAP.title_for({"brief": b["id"], "question": b.get("asked") or b["question"]}, self.env)

    def test_hiragana_sazanka_brief_has_card_and_spots(self):
        b = GB.build("さざんかの見頃と見どころを教えて", now=NOW, env=self.env)
        self.assertEqual(b["question"], "サザンカの見頃と見どころを教えて")
        self.assertEqual(b["asked"], "さざんかの見頃と見どころを教えて")
        self.assertIn("試験の見分け方(サザンカ)", [k["title"] for k in b["cards"]])
        names = [c["name"] for c in b["candidates"]]
        self.assertIn("亀戸中央公園", names)
        self.assertIn("国営昭和記念公園", names)
        t = self._title(b)
        self.assertIn("サザンカ", t)
        self.assertNotEqual(t, "花の見どころ")

    def test_same_as_katakana_question(self):
        a = GB.build("さざんかの見頃と見どころを教えて", now=NOW, env=self.env)
        k = GB.build("サザンカの見頃と見どころを教えて", now=NOW, env=self.env)
        self.assertEqual([c["name"] for c in a["candidates"]], [c["name"] for c in k["candidates"]])
        self.assertEqual([x["title"] for x in a["cards"]], [x["title"] for x in k["cards"]])

    def test_difference_title(self):
        b = GB.build("ツバキの見頃と見られるところを教えて。ツバキとさざんかの違いも教えて", now=NOW, env=self.env)
        self.assertEqual(self._title(b), "ツバキとサザンカの違い")


class MoreMixUps(unittest.TestCase):
    """段階82 第1部の追記: コケモモ・コケリンドウを苔にしない / 表のひらがなの書き方は題でカタカナに。"""

    def test_koke_prefix(self):
        self.assertEqual([x["name"] for x in SP.resolve_all("コケモモの実はいつ")], [])
        self.assertEqual([x["name"] for x in SP.resolve_all("コケリンドウの花")], [])
        self.assertEqual([x["name"] for x in SP.resolve_all("コケがきれいな場所")], ["苔"])

    def test_hiragana_table_words_in_title_themes(self):
        t = GAP.cfg()["title"]
        self.assertEqual(GAP._themes_in("あじさいの見頃と見どころ", t), ["アジサイ"])
        self.assertEqual(GAP._themes_in("すいせんの見頃", t), ["スイセン"])
        self.assertEqual(GAP._themes_in("ふじさんの紅葉", t), ["紅葉"])


if __name__ == "__main__":
    unittest.main()
