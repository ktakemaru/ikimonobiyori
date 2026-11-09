"""段階73 第1部: 段階72 の残り(棚卸しの都県の補い・カードの主語・大きな地名の座標)。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import areas as AR
from ikimonobiyori import coverage as CV
from ikimonobiyori import knowledge as K
from ikimonobiyori import place_guard as PG


class RecordPrefecture(unittest.TestCase):
    def setUp(self):
        self.spot_of = {"t-0001": ("試験の渓谷", "栃木県"), "t-0002": ("試験の庭", CV.UNKNOWN)}
        self.city_pref = {"試験市中区": "神奈川県", "試験町": "群馬県"}

    def test_spot_id_gives_name_and_prefecture(self):
        self.assertEqual(CV._record_pref({"spot": "t-0001"}, self.spot_of, self.city_pref), ("栃木県", "試験の渓谷"))

    def test_written_prefecture_wins(self):
        self.assertEqual(CV._record_pref({"spot": "t-0001", "prefecture": "東京都"}, self.spot_of, self.city_pref)[0], "東京都")

    def test_city_and_city_prefix(self):
        self.assertEqual(CV._record_pref({"name": "試験の池", "city": "試験町"}, self.spot_of, self.city_pref)[0], "群馬県")
        self.assertEqual(CV._record_pref({"name": "試験の池", "city": "試験市"}, self.spot_of, self.city_pref)[0], "神奈川県")
        self.assertEqual(CV._record_pref({"name": "試験の池", "city": "神奈川県試験市"}, self.spot_of, {})[0], "神奈川県")

    def test_unknown_stays_unknown(self):
        self.assertEqual(CV._record_pref({"spot": "t-0002"}, self.spot_of, self.city_pref), (CV.UNKNOWN, "試験の庭"))
        self.assertEqual(CV._record_pref({"name": "試験の滝"}, self.spot_of, self.city_pref)[0], CV.UNKNOWN)

    def test_ambiguous_city_prefix_is_not_guessed(self):
        cp = {"試験市北区": "東京都", "試験市南区": "埼玉県"}
        self.assertEqual(CV._record_pref({"name": "試験の池", "city": "試験市"}, {}, cp)[0], CV.UNKNOWN)


class Subject(unittest.TestCase):
    def test_rewritten_fact_passes(self):
        card = {"title": "試験の紅葉の目安", "place": "試験山", "subject": "試験山の紅葉",
                "facts": ["試験山の紅葉は、気温が8℃前後を下回ると色づき始める"]}
        self.assertEqual(K.subject_errors(card), [])
        self.assertTrue(K.subject_errors({"title": "x", "place": "試験山", "facts": ["気温が8℃前後を下回ると色づき始める"]}))


class Lakes(unittest.TestCase):
    def test_lakes_have_coordinates_and_stay_research_targets(self):
        for n in ("霞ヶ浦", "印旛沼", "相模湖"):
            a = PG.pending_area(n)
            self.assertIsNotNone(a, n)
            self.assertIsNotNone((a.get("center") or {}).get("lat"), n)
            self.assertTrue(str(a.get("qid", "")).startswith("Q"), n)
            self.assertNotIn(n, [x["name"] for x in AR.load()["areas"]])
        self.assertIsNotNone(PG.pending_area("西浦"))


if __name__ == "__main__":
    unittest.main()
