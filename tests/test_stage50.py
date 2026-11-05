"""段階50(指示書 docs/stage50-sources-data-instructions.md): 通信しない。
- 前シーズンの情報の判定(東京都公園協会の紅葉情報は 2026-11-05 時点で 2025 年シーズンの最終版)。
- 台帳に東京都公園協会の紅葉情報が公式として載り、前シーズンの日付の記録は受け付けない。
- 都立公園・庭園 37 か所が名所(カタログまたは観察の名所)にあり、樹種・本数がある。"""
import copy
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import season, sources

POLICY = sources.load_policy()
TEXT = "紅葉状況 最終情報更新日：令和7年12月18日（木）17時 ※令和7年12月22日（月）に閉鎖"


class SeasonCheck(unittest.TestCase):
    def test_reads_reiwa_date(self):
        self.assertEqual(season.parse_update_date(TEXT, POLICY), date(2025, 12, 18))
        self.assertEqual(season.parse_update_date("最終情報更新日：令和元年11月1日", POLICY), date(2019, 11, 1))
        self.assertEqual(season.parse_update_date("最終情報更新日：2026年11月10日", POLICY), date(2026, 11, 10))

    def test_no_guess(self):
        self.assertIsNone(season.parse_update_date("更新しました", POLICY))
        self.assertIsNone(season.parse_update_date("最終情報更新日：令和7年2月30日", POLICY))

    def test_last_season_is_not_current(self):
        st = season.season_status(date(2025, 12, 18), date(2026, 11, 5), POLICY)
        self.assertIs(st["current"], False)
        self.assertEqual(st["label"], "前シーズンの情報")
        self.assertIn("2025年12月18日の最終版", st["note"])

    def test_this_season_is_current(self):
        self.assertIs(season.season_status(date(2026, 11, 10), date(2026, 11, 12), POLICY)["current"], True)
        self.assertIs(season.season_status(date(2025, 12, 18), date(2026, 1, 5), POLICY)["current"], True)   # 直近の9月1日(2025-09-01)以降
        self.assertIs(season.season_status(date(2026, 8, 31), date(2026, 9, 2), POLICY)["current"], False)   # 9月1日より前

    def test_unreadable_or_future_date_is_not_called_current(self):
        self.assertIsNone(season.season_status(None, date(2026, 11, 5), POLICY)["current"])
        self.assertIsNone(season.season_status(date(2026, 12, 1), date(2026, 11, 5), POLICY)["current"])


class Ledger(unittest.TestCase):
    def setUp(self):
        self.reg = sources.load_registry("autumn_leaves")
        self.src = sources.sources_by_id(self.reg)["tokyo-park-kouyou-special"]

    def test_entry_is_official_with_37_places(self):
        self.assertEqual(self.src["kind"], "status_page")
        self.assertEqual(self.src["publisher_kind"], "park_manager")
        self.assertEqual(len(self.src["covers"]), 37)
        self.assertTrue(self.src["notation"]["season_check"])
        self.assertEqual(self.src["notation"]["map"], {})                     # 凡例が読めていない状態名を段階に変えない
        self.assertEqual(self.src["readable"]["observed_latest_update"], "2025-12-18")

    def _rec(self, updated):
        return {"schema": "ikimono-status-record/1", "subject": "autumn_leaves", "source_id": self.src["id"], "name": "六義園" if False else "石神井公園",
                "label": "石神井公園", "official_state": "落葉", "stage": None, "official_updated": updated,
                "read_at": "2026-11-05T10:00:00+09:00", "url": self.src["url"]}

    def test_last_season_record_is_rejected_this_season_passes(self):
        reg = copy.deepcopy(self.reg)
        s = sources.sources_by_id(reg)["tokyo-park-kouyou-special"]
        s["approval"] = {"status": "approved", "approved_by": "user", "approved_on": "2026-11-05"}
        pol = copy.deepcopy(POLICY)
        schema = pol["record"]["schema"]
        rec = self._rec("2025-12-18"); rec["schema"] = schema
        errs = sources.validate_record(rec, registry=reg, policy=pol)
        self.assertTrue(any("前シーズン" in e for e in errs), errs)
        rec = self._rec("2026-11-04"); rec["schema"] = schema
        errs = sources.validate_record(rec, registry=reg, policy=pol)
        self.assertFalse(any("前シーズン" in e for e in errs), errs)


class Spots(unittest.TestCase):
    NAMES_CATALOG = {"六義園", "小石川後楽園"}

    def test_all_37_places_exist_and_new_ones_have_trees(self):
        spots = {s["name"]: s for s in O.load_spots()["spots"] if s["subject"] == "autumn_leaves"}
        covers = [c.get("name") or c["label"] for c in sources.sources_by_id(sources.load_registry("autumn_leaves"))["tokyo-park-kouyou-special"]["covers"]]
        for n in covers:
            if n in self.NAMES_CATALOG:
                continue
            self.assertIn(n, spots, n)
            t = spots[n]["trees"]
            self.assertEqual(t["publisher"], "東京都公園協会")
            self.assertEqual(t["year"], 2025)                                  # 今年の現況ではない
            self.assertEqual(t["source_class"], "official")

    def test_secondary_typical_windows_are_secondary_and_2025(self):
        spots = {s["name"]: s for s in O.load_spots()["spots"] if s["subject"] == "autumn_leaves"}
        for n, peak in (("城北中央公園", "11月下旬～12月上旬"), ("戸山公園", "11月下旬～12月上旬"), ("舎人公園", "11月中旬～12月上旬"), ("武蔵野公園", "11月中旬～12月下旬")):
            ty = spots[n]["typical"]
            self.assertEqual([t["text"] for t in ty], [peak])
            self.assertEqual({t["source_class"] for t in ty}, {"secondary"})
            self.assertEqual({t["publisher"] for t in ty}, {"ウォーカープラス"})
        hibiya = spots["日比谷公園"]["typical"]
        self.assertIn("るるぶ", {t["publisher"] for t in hibiya})
        self.assertEqual({t["source_class"] for t in hibiya}, {"secondary"})


if __name__ == "__main__":
    unittest.main()
