"""段階82 の続き(本人の判断 2026-11-13 の 1): 2 つの種を比べる見分け方のカード(項目 contrasts)の組み合わせと逆の文を止める。
合成データ(通信しない)。カードは一時フォルダに書く。"""
import json
import tempfile
import unittest
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import knowledge as K

C = GB.cfg()
SAZANKA = {"id": "K004", "title": "サザンカとツバキの見分け方",
           "facts": ["花の似ているツバキは花ごと落ちるのに対して、サザンカは花びらが1枚ずつ散る"],
           "contrasts": [{"a": ["ツバキ"], "a_re": "花ごと(落ち|ぽとり|散)", "b": ["サザンカ"], "b_re": "花びらが(1|一)枚ずつ散|花びらが散"}]}
ROUBAI = {"id": "K001", "title": "ソシンロウバイはお正月のころ(ロウバイとの違い)",
          "facts": ["ソシンロウバイは花の内側まで黄色く、花の内側が暗紫色でやや小ぶりのロウバイより少し大きな花を咲かせる"],
          "contrasts": [{"a": ["ロウバイ"], "a_re": "(中心|内側|真ん中)が(暗)?紫|小ぶり", "b": ["ソシンロウバイ"], "b_re": "(内側|中心|真ん中)まで黄色"}]}
KAMO = {"id": "K002", "title": "冬のカモの見分け方",
        "facts": ["キンクロハジロは潜って餌をとるカモで、マガモ・コガモは水面で餌をとるカモ"],
        "contrasts": [{"a": ["キンクロハジロ"], "a_re": "潜って|もぐって", "b": ["マガモ", "コガモ"], "b_re": "水面で"}]}
HAKUCHO = {"id": "K003", "title": "オオハクチョウ(コハクチョウとの違い)",
           "facts": ["オオハクチョウは、よく似たコハクチョウより大きい"],
           "contrasts": [{"a": ["オオハクチョウ"], "a_re": "(より|ほうが|方が)大き|半分以上", "b": ["コハクチョウ"], "b_re": ""}]}
BRIEF = {"facts": [], "cards": [SAZANKA, ROUBAI, KAMO, HAKUCHO]}


def codes(text):
    return [e["code"] for e in GV.contrast_errors(GV.sentences(text.splitlines(), C), BRIEF, C)]


class Reversed(unittest.TestCase):
    def test_the_example_fails(self):
        self.assertEqual(codes("サザンカは花ごと落ちます [K004]。"), ["trait_reversed"])
        self.assertEqual(codes("サザンカは花ごと落ちます。[K004]"), ["trait_reversed"])

    def test_hiragana_and_kanji_names(self):
        self.assertEqual(codes("さざんかは花ごと落ちます。[K004]"), ["trait_reversed"])
        self.assertEqual(codes("山茶花は花ごと落ちる花です。[K004]"), ["trait_reversed"])

    def test_other_side_reversed(self):
        self.assertEqual(codes("ツバキは花びらが1枚ずつ散ります。[K004]"), ["trait_reversed"])
        self.assertEqual(codes("サザンカは花ごと落ち、ツバキは花びらが散ります。[K004]"), ["trait_reversed"])

    def test_comparative_reversed(self):
        self.assertEqual(codes("コハクチョウはオオハクチョウより大きい白鳥です。[K003]"), ["trait_reversed"])

    def test_fix_message(self):
        e = GV.contrast_errors(GV.sentences(["サザンカは花ごと落ちます。[K004]"], C), BRIEF, C)[0]
        self.assertIn("ツバキ", e["detail"])
        self.assertIn("カードのとおりの組み合わせ", e["fix"])


class NotOverBlocked(unittest.TestCase):
    def test_correct_pairs_pass(self):
        self.assertEqual(codes("ツバキは花ごと落ちますが、サザンカは花びらが1枚ずつ散ります。[K004]"), [])
        self.assertEqual(codes("花の似ているツバキは花ごと落ちますが、サザンカは花びらが1枚ずつ散ります。[K004]"), [])
        self.assertEqual(codes("散った花びらが一枚ずつ地面に落ちるのがサザンカで、花ごと落ちるツバキとの見分けになります。[K004]"), [])

    def test_the_cards_own_lines_pass(self):
        for k in BRIEF["cards"]:
            for f in k["facts"]:
                self.assertEqual(codes(f + "。[" + k["id"] + "]"), [], f)

    def test_negation_and_comparison_partner(self):
        self.assertEqual(codes("サザンカは花ごと落ちず、花びらが1枚ずつ散ります。[K004]"), [])
        self.assertEqual(codes("サザンカはツバキのように花ごと落ちることはありません。[K004]"), [])
        self.assertEqual(codes("サザンカはツバキと違って、花びらが1枚ずつ散ります。[K004]"), [])
        self.assertEqual(codes("コハクチョウより大きいのがオオハクチョウです。[K003]"), [])

    def test_longer_name_is_not_the_shorter_one(self):
        self.assertEqual(codes("ソシンロウバイは花の内側まで黄色です。[K001]"), [])
        self.assertEqual(codes("ソシンロウバイは内側が暗紫色です。[K001]"), ["trait_reversed"])

    def test_middle_dot_list(self):
        self.assertEqual(codes("キンクロハジロは潜って餌をとり、マガモ・コガモは水面で餌をとります。[K002]"), [])
        self.assertEqual(codes("マガモ・コガモは潜って餌をとります。[K002]"), ["trait_reversed"])

    def test_without_marker_or_other_card_is_not_this_check(self):
        self.assertEqual(codes("サザンカは花ごと落ちます。"), [])                 # 印なしは trait_without_card が受け持つ
        self.assertEqual(codes("サザンカは花ごと落ちます。[F001]"), [])


class CardField(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        p = K.path(self.env)
        p.parent.mkdir(parents=True, exist_ok=True)
        card = {"title": "サザンカとツバキの見分け方", "category": "種の解説", "place": "試験の公園", "facts": SAZANKA["facts"],
                "condition": {"year_dependent": False}, "source": {"name": "試験の公園", "title": "花", "url": "https://example.org/a", "checked_on": "2026-11-13"},
                "confidence": "施設の解説", "rights": "x", "usage": "x"}
        p.write_text(json.dumps(card, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_contrasts_keeps_a_change_log(self):
        K.set_contrasts("サザンカとツバキの見分け方", SAZANKA["contrasts"], at="2026-11-13T09:00:00+09:00", env=self.env)
        self.assertEqual(K.load(self.env)[0]["contrasts"], SAZANKA["contrasts"])
        log = Path(self.tmp.name) / K.cfg()["changes_file"]
        self.assertIn("set_contrasts", log.read_text(encoding="utf-8"))

    def test_bad_items_are_refused(self):
        for bad in ([], [{"a": ["ツバキ"], "a_re": "(", "b": ["サザンカ"], "b_re": ""}], [{"a": ["ツバキ"], "a_re": "", "b": ["サザンカ"]}],
                    [{"a": ["ツバキ"], "a_re": "x", "b": ["ツバキ"], "b_re": ""}]):
            with self.assertRaises(ValueError):
                K.set_contrasts("サザンカとツバキの見分け方", bad, at="2026-11-13T09:00:00+09:00", env=self.env)

    def test_brief_cards_carry_the_field(self):
        rows = GB._card_rows([({**K.load(self.env)[0], "contrasts": SAZANKA["contrasts"]}, "theme")], C)
        self.assertEqual(rows[0]["contrasts"], SAZANKA["contrasts"])


if __name__ == "__main__":
    unittest.main()
