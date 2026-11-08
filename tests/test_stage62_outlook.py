"""段階62 第4部: 公式の新しい現況を、例年の時期より優先する(「過ぎている見込み」「終盤」にしない)。通信なし・合成データ。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP

POL = AP.load_policy()
D = AP._d("2026-11-08")


def cand(state, sdate, rel, window=("10-01", "10-31"), cls="official"):
    return {"name": "試験の道の駅", "relation": rel, "current": {"state": state, "state_date": sdate, "source_class": cls},
            "typical": [{"start": window[0], "end": window[1]}]}


class AfterWindow(unittest.TestCase):
    def test_fresh_official_state_overrides_after_peak(self):
        self.assertEqual(AP.outlook_of(cand("色づき始め", "2026-11-06", "after_peak"), D, POL), "toward")
        self.assertEqual(AP.outlook_of(cand("見頃", "2026-11-06", "after_peak"), D, POL), "late")

    def test_old_or_secondary_state_does_not_override(self):
        self.assertEqual(AP.outlook_of(cand("色づき始め", "2026-11-01", "after_peak"), D, POL), "past")          # 対象日の 7 日前
        self.assertEqual(AP.outlook_of(cand("色づき始め", "2026-11-06", "after_peak", cls="secondary"), D, POL), "past")
        self.assertEqual(AP.outlook_of(cand("見頃過ぎ", "2026-11-06", "after_peak"), D, POL), "past")

    def test_fresh_start_of_colour_near_window_end_is_not_late(self):
        c = cand("色づき始め", "2026-11-06", "in_peak", window=("10-20", "11-12"))
        self.assertEqual(AP.outlook_of(c, D, POL), "toward")
        c = cand("見頃", "2026-11-06", "in_peak", window=("10-20", "11-12"))
        self.assertEqual(AP.outlook_of(c, D, POL), "late")                                                    # 見頃は従来どおり終盤


if __name__ == "__main__":
    unittest.main()
