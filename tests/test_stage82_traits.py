"""段階82 第2部: 種の見分け方・特徴の文は、カードの裏づけ(その種のその特徴を書いたカードの印)を求める。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import research as RS

C = GB.cfg()
K_TSUBAKI = {"id": "K001", "title": "ツバキの花と鳥(花ごと落ちるわけ)", "subject": "ツバキ",
             "facts": ["ツバキの花が丸ごと落ちるのは、花弁とおしべの筒が根元でつながっているから"]}
K_SAZANKA = {"id": "K002", "title": "サザンカとツバキの見分け方", "subject": "サザンカ",
             "facts": ["花の似ているツバキは花ごと落ちるのに対して、サザンカは花びらが1枚ずつ散る"]}
BRIEF = {"facts": [], "cards": [K_TSUBAKI, K_SAZANKA]}


def errs(text, brief=BRIEF):
    return [e["code"] for e in GV.trait_errors(GV.sentences(text.splitlines(), C), brief, C)]


class Traits(unittest.TestCase):
    def test_the_real_mistake_without_marker_fails(self):
        self.assertEqual(errs("サザンカは、花びらが一枚ずつ散らず、花ごと落ちることが多い花です。"), ["trait_without_card"])

    def test_fix_message(self):
        e = GV.trait_errors(GV.sentences(["サザンカは、花びらが一枚ずつ散らず、花ごと落ちることが多い花です。"], C), BRIEF, C)[0]
        self.assertIn("この種の特徴は資料にありません。書かないでください", e["fix"])

    def test_hiragana_species_name_is_checked_too(self):
        self.assertEqual(errs("さざんかは花ごと落ちます。"), ["trait_without_card"])

    def test_marked_with_that_species_card_passes(self):
        self.assertEqual(errs("ツバキは花ごと落ちますが、サザンカは花びらが1枚ずつ散ります。[K002]"), [])

    def test_other_species_card_does_not_back_it(self):
        self.assertEqual(errs("サザンカは花ごと落ちます。[K001]"), ["trait_wrong_card"])

    def test_season_and_environment_talk_is_not_checked(self):
        self.assertEqual(errs("冬鳥は秋に北から渡ってきます。標高が高いほど時期が遅くなります。"), [])
        self.assertEqual(errs("サザンカは冬の庭を彩る花です。"), [])
        self.assertEqual(errs("桜は、例年の目安がまとまりごとに違います。"), [])           # 止めすぎの直し(時期の説明)
        self.assertEqual(errs("カエデは日当たりのよい枝から先に赤くなるので、色の進み方の違いが分かります。"), [])
        self.assertEqual(errs("尾瀬のミズバショウは散策路から見られます。"), [])          # 尾瀬の「尾」・散策の「散」は特徴の語ではない

    def test_group_names_are_not_species(self):
        self.assertEqual(errs("猛禽類は、くちばしが鋭い鳥の仲間です。"), [])

    def test_okurigana_is_not_a_species(self):
        self.assertEqual(errs("ゲンジボタルのほうが大きく見えます。"), [])               # 「大きく」の「きく」を菊にしない


class BriefSide(unittest.TestCase):
    def test_species_without_cards_is_listed(self):
        self.assertEqual(GB._species_without_cards("コキアの時期と見られる場所を教えて", []), ["コキア"])
        self.assertEqual(GB._species_without_cards("サザンカの時期", [K_SAZANKA]), [])

    def test_research_step_for_species_card(self):
        L = RS.lines_for("b1", [{"what": "コキア", "where": None, "why": "コキアの公的な解説", "kind": "species_card"}])
        self.assertTrue(any("ask knowledge add" in x for x in L))
        self.assertTrue(any("コキアの公的な解説" in x for x in L))


if __name__ == "__main__":
    unittest.main()
