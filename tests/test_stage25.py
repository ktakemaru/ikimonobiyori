"""段階25: 市区町村の代表点を取って範囲を確かめた地点・古徳沼の承認・横浜自然観察の森・却下/退役の保証。通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide

P = guide.load_policy()


def entry(name, theme):
    return next(e for e in guide.committed_entries() if e["name"] == name and e["theme"] == theme)


class Phase1Range(unittest.TestCase):
    def test_places_now_checked_are_provisional_curated_in_range(self):
        for name in ("渡良瀬遊水地", "秋ヶ瀬公園", "泉の森", "奥日光(戦場ヶ原・中禅寺湖)"):
            e = entry(name, "野鳥")
            self.assertEqual((e["tier"], e["range"]["status"], e["approval"]["state"], e["approval"]["by"]), ("curated", "in_range", "provisional", "auto-rule"), name)
            self.assertGreaterEqual(e["independent_sources"], 2)
            self.assertEqual(set(e["range"]["by_origin"]), {"東京", "横浜"})

    def test_one_source_places_stay_reference_even_in_range(self):
        for name in ("ふなばし三番瀬海浜公園", "彩湖"):
            e = entry(name, "野鳥")
            self.assertEqual((e["tier"], e["range"]["status"], e["approval"]["state"]), ("reference", "in_range", "candidate"), name)

    def test_unknown_municipality_stays_unconfirmed(self):
        e = entry("妙岐ノ鼻・和田公園(霞ヶ浦)", "野鳥")
        self.assertEqual((e["range"]["status"], e["approval"]["state"]), ("pending", "candidate"))
