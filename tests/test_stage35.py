"""段階35(指示書 biyori-hub/docs/stageH9-instructions.md の「段階R2」): 試用で見つかった穴の修正。通信なし。合成のデータだけ。
- 穴2: 野鳥は「この時期に見られる鳥」(iNaturalist の過去の記録のキャッシュ・前の年の同じ時期の記録)で書き、「例年の見頃」の関係を出さない。
       休園日の規則(第1・3月曜・祝日の場合は翌日・年末年始の日付)を対象の日と照らす。
- 穴3: 新しい・古いは状態の日付で判定する(原文の「10/25現在」も状態の日付)。例年の時期に、今年の行事の期間をそのまま入れない。"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import closures as C
from ikimonobiyori import observations as O
from ikimonobiyori import profiles as PR
from ikimonobiyori.config import load_config
from ikimonobiyori.engine import round_coord
from ikimonobiyori.fetch import birds_live
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.paths import data_path

P = O.load_policy()
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 1, 10, 0, tzinfo=JST)
D = [date(2026, 11, 2)]
RULE = "小谷戸の里は毎月第1・3月曜(祝日の場合は翌日)と12月29日～1月3日"

SPOTS = {"spots": [
    {"id": "t-b-1", "subject": "birds", "name": "試験の遊水地", "prefecture": "神奈川県", "city": "試験市", "bird_area": "kanagawa_sakaigawa",
     "pages": [{"url": "https://birds.example.org/", "publisher": "試験の遊水地(自然情報)", "source_class": "official"}]},
    {"id": "t-b-2", "subject": "birds", "name": "試験の公園", "prefecture": "神奈川県", "city": "試験市", "bird_area": "kanagawa_sakaigawa",
     "closed": {"text": RULE, "facility": "小谷戸の里", "open_note": "公園には入れます", "url": "https://city.example.jp/maioka"}, "pages": []},
    {"id": "t-b-3", "subject": "birds", "name": "試験の森", "prefecture": "神奈川県", "city": "試験市",
     "season_birds": [{"text": "冬鳥のジョウビタキが来始めます", "season": "11月", "year": 2025, "url": "https://mori.example.org/",
                       "publisher": "試験の森", "source_class": "official"}], "pages": []},
    {"id": "t-h-1", "subject": "flowers", "name": "試験の花園", "prefecture": "神奈川県", "city": "試験市", "flower_kinds": ["コスモス"],
     "typical": [{"text": "11月上旬～11月下旬", "kind": "コスモス", "publisher": "試験の協会", "url": "https://hana.example.org/ev",
                  "year": 2025, "source_class": "secondary", "event_derived": True}],
     "events": [{"name": "試験のコスモスまつり", "kind": "コスモス", "start": "2026-10-31", "end": "2026-11-29", "url": "https://hana.example.org/",
                 "publisher": "試験の花園", "source_class": "official"}], "pages": []},
]}
CAT_FLOWERS = {"entries": [
    {"id": "t-cat-1", "name": "試験のバラ園", "tags": {"prefecture": "神奈川県", "city": "試験市"}, "sources": [{"url": "https://rose.example.org/"}],
     "flower_windows": [{"kind": "秋バラ", "start": "10-10", "end": "11-08", "source_url": "https://rose.example.org/ev", "source_year": 2026,
                         "note": "今年(2026年)のローズフェスティバルの期間を例年の目安に使っている"}],
     "events": [{"kind": "秋バラ", "name": "試験のローズフェスティバル", "start": "2026-10-10", "end": "2026-11-08", "year": 2026,
                 "source_url": "https://rose.example.org/ev", "verified": True}]},
    {"id": "t-cat-2", "name": "試験のコスモス畑", "tags": {"prefecture": "神奈川県", "city": "試験町"}, "sources": [{"url": "https://cos.example.org/"}],
     "flower_windows": [{"kind": "コスモス", "start": "10-01", "end": "10-20", "source_url": "https://cos.example.org/", "source_year": None,
                         "note": "キバナコスモスは例年10月上旬〜中旬"}]},
]}
CATALOGS = {"birds": {"entries": []}, "flowers": CAT_FLOWERS}


def rec(spot, state, state_date, subject="birds", url="https://birds.example.org/", **kw):
    return {"subject": subject, "spot": spot, "state": state, "state_date": state_date, "url": url,
            "publisher": kw.pop("publisher", "試験の遊水地(自然情報)"), "source_class": kw.pop("source_class", "official"), **kw}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def facts(self, subject, now=NOW, dates=D):
        return O.facts(subject, region="神奈川", dates=dates, now=now, env=self.env, spots_doc=SPOTS, catalogs={subject: CATALOGS[subject]})

    def put_inat(self, area_id="kanagawa_sakaigawa", d=D[0]):
        """合成の iNaturalist の応答(集計値だけ)を、問い合わせと同じ URL でキャッシュに置く。"""
        area = next(a for a in O.load_obs_bird_areas() if a["id"] == area_id)
        prof = PR.load_profiles()["birds"]
        cfg = load_config()
        area = dict(area, lat=round_coord(area["lat"], "area_10km"), lon=round_coord(area["lon"], "area_10km"))
        cache = Cache(data_path(cfg["cache"]["dir"], self.env))
        body = {"total_results": 3, "page": 1, "per_page": 200, "results": [
            {"count": 20, "taxon": {"id": 1, "name": "Anas crecca", "preferred_common_name": "コガモ"}},
            {"count": 12, "taxon": {"id": 2, "name": "Anas acuta", "preferred_common_name": "オナガガモ"}},
            {"count": 8, "taxon": {"id": 3, "name": "Phoenicurus auroreus", "preferred_common_name": "ジョウビタキ"}}]}
        for _d, _k, q in birds_live.bird_queries(area, [d], prof, cfg["live"]["inaturalist"]["per_page"]):
            cache.put(url=q["url"], params=q["params"], body=json.dumps(body, ensure_ascii=False), source="iNaturalist API",
                      fetched_at="2026-10-31T22:14:00+09:00")


class Hole3Freshness(Base):
    def test_state_date_decides_freshness(self):
        """10/27 の状態を 11/1 に読んだ記録は、11/1 の質問で古い(読んだ日ではなく状態の日付で判定)。"""
        O.record([rec("t-h-1", "コスモス: 全体としては、現在2～3分咲きです。", "2026-10-27", subject="flowers", url="https://hana.example.org/")],
                 env=self.env, now=NOW)
        p = O.plan("flowers", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs={"flowers": CAT_FLOWERS})
        item = next(i for i in p["items"] if i["id"] == "t-h-1")
        self.assertEqual(item["freshness"]["class"], "stale")
        self.assertEqual((item["freshness"]["basis"], item["freshness"]["basis_date"]), ("state_date", "2026-10-27"))
        self.assertTrue(p["needs_fetch"])

    def test_date_written_in_state_text_counts_as_state_date(self):
        """状態の日付の欄が空でも、原文の「10/25現在」を状態の日付として判定する(記録のファイルは書き換えない)。"""
        O.record([rec("t-h-1", "コスモス: 10/25現在満開です。", None, subject="flowers", url="https://hana.example.org/")], env=self.env, now=NOW)
        rows = O.read_records("flowers", self.env)
        self.assertIsNone(rows[0]["state_date"])
        self.assertEqual(rows[0]["state_date_from_text"], "2026-10-25")
        self.assertEqual(O.freshness(rows[0], NOW.date(), "flowers", P)["class"], "stale")

    def test_no_state_date_uses_read_time(self):
        O.record([rec("t-h-1", "開花状況の記載なし", None, subject="flowers", url="https://hana.example.org/")], env=self.env, now=NOW)
        rows = O.read_records("flowers", self.env)
        fr = O.freshness(rows[0], NOW.date(), "flowers", P)
        self.assertEqual((fr["class"], fr["basis"]), ("fresh", "read_at"))

    def test_event_period_is_not_typical(self):
        """今年の行事の期間を写した「例年の見頃」は例年の時期として出さず、分けて書く。"""
        f = self.facts("flowers")
        rose = next(c for c in f["candidates"] + f["avoid"] if c["id"] == "t-cat-1")
        self.assertEqual(rose["typical"], [])
        self.assertEqual(rose["event_periods_not_typical"][0]["text"], "10/10〜11/8")
        self.assertEqual(rose["typical_line"], "例年の時期は分かりません(今年の行事「試験のローズフェスティバル」は10/10〜11/8)")
        cos = next(c for c in f["candidates"] + f["avoid"] if c["id"] == "t-h-1")
        self.assertEqual(cos["typical"], [])
        self.assertEqual(cos["typical_line"], "例年の時期は分かりません(今年の行事「試験のコスモスまつり」は10/31〜11/29)")
        self.assertEqual(cos["tier"], 2)                       # 対象の日に行事がある花は、例年の時期が分からなくても前の段
        plain = next(c for c in f["candidates"] + f["avoid"] if c["id"] == "t-cat-2")
        self.assertEqual(plain["typical_line"], "例年の見頃: 10/1〜10/20")    # 行事でない例年の時期はそのまま

    def test_record_typical_with_event_words_is_not_typical(self):
        O.record([rec("t-cat-2", "開花状況の記載なし", None, subject="flowers", url="https://news.example.jp/",
                      typical="例年10月下旬から11月下旬にかけて開催", source_class="secondary", publisher="試験新聞")], env=self.env, now=NOW)
        f = self.facts("flowers")
        cos = next(c for c in f["candidates"] + f["avoid"] if c["id"] == "t-cat-2")
        self.assertEqual([t["text"] for t in cos["typical"]], ["10/1〜10/20"])


class Hole2Birds(Base):
    def test_no_typical_relation_for_birds_and_season_line(self):
        self.put_inat()
        f = self.facts("birds")
        self.assertGreaterEqual(len(f["candidates"]), 3)
        for c in f["candidates"]:
            self.assertIsNone(c["relation_label"])
            self.assertNotIn("例年の見頃", c["season_line"])
            self.assertIn("この時期に見られる鳥", c["season_line"])
        a = next(c for c in f["candidates"] if c["id"] == "t-b-1")
        self.assertEqual([s["name"] for s in a["inat"]["species"]], ["コガモ", "オナガガモ", "ジョウビタキ"])
        self.assertEqual(a["inat"]["total"], 80)                         # 窓が 10 月と 11 月にまたがる 2 応答の合計
        self.assertIn("コガモ・オナガガモ・ジョウビタキが多く記録されています", a["season_line"])
        self.assertIn("この時期の記録が多い", a["reason_labels"])

    def test_without_cache_uses_past_record_or_page(self):
        O.record([rec("t-b-1", "下飯田遊水地(18種): マガモ、コガモ、キンクロハジロ ほか", "2025-11-19"),
                  rec("t-b-1", "冬鳥のコガモ・オオバンが増えて来ました", "2026-10-21")], env=self.env, now=NOW)
        f = self.facts("birds")
        a = next(c for c in f["candidates"] if c["id"] == "t-b-1")
        self.assertIsNone(a["inat"])
        self.assertEqual([x["kind"] for x in a["season_birds"]], ["past_record"])       # 今年の記録は「前の年の同じ時期」に入れない
        self.assertEqual(a["season_line"], "この時期に見られる鳥: 2025年11/19の記録(試験の遊水地(自然情報))では「下飯田遊水地(18種): マガモ、コガモ、キンクロハジロ ほか」")
        m = next(c for c in f["candidates"] if c["id"] == "t-b-3")
        self.assertEqual(m["season_line"], "この時期に見られる鳥: 試験の森の紹介では「冬鳥のジョウビタキが来始めます」")
        p = next(c for c in f["candidates"] if c["id"] == "t-b-2")
        self.assertEqual(p["season_line"], "この時期に見られる鳥の記録は見つかっていません")

    def test_closed_day_is_stated_for_the_target_date(self):
        f = self.facts("birds")
        p = next(c for c in f["candidates"] if c["id"] == "t-b-2")
        self.assertEqual(p["closed_on"][0]["closed"], True)
        self.assertEqual(p["closed_on"][0]["line"], "11/2(月)は小谷戸の里が休みです(公園には入れます)。")


class Closures(unittest.TestCase):
    def test_first_and_third_monday_with_holiday_shift(self):
        self.assertTrue(C.evaluate(RULE, date(2026, 11, 2))["closed"])           # 第1月曜
        self.assertFalse(C.evaluate(RULE, date(2026, 11, 3))["closed"])          # 文化の日(火)。第1月曜は祝日でないので振替なし
        self.assertFalse(C.evaluate(RULE, date(2026, 11, 4))["closed"])
        self.assertTrue(C.evaluate(RULE, date(2026, 11, 16))["closed"])          # 第3月曜
        self.assertTrue(C.evaluate(RULE, date(2026, 12, 30))["closed"])          # 12/29〜1/3
        self.assertTrue(C.evaluate(RULE, date(2027, 1, 2))["closed"])

    def test_holiday_monday_moves_to_next_open_day(self):
        r = "毎月第2月曜(祝日の場合は翌日)"
        self.assertFalse(C.evaluate(r, date(2026, 10, 12))["closed"])           # スポーツの日(第2月曜)は開いている
        self.assertTrue(C.evaluate(r, date(2026, 10, 13))["closed"])            # 翌日が休み
        r3 = "毎月第3月曜(祝日の場合は翌日)"
        self.assertFalse(C.evaluate(r3, date(2026, 9, 21))["closed"])           # 敬老の日
        self.assertFalse(C.evaluate(r3, date(2026, 9, 22))["closed"])           # 国民の休日
        self.assertFalse(C.evaluate(r3, date(2026, 9, 23))["closed"])           # 秋分の日
        self.assertTrue(C.evaluate(r3, date(2026, 9, 24))["closed"])            # 祝日でない最初の日

    def test_weekly_and_unreadable(self):
        self.assertTrue(C.evaluate("毎週月曜日(祝日の場合は翌日)", date(2026, 11, 9))["closed"])
        self.assertFalse(C.evaluate("毎週月曜日(祝日の場合は翌日)", date(2026, 11, 10))["closed"])
        u = C.evaluate("年末年始", date(2026, 12, 31))
        self.assertIsNone(u["closed"])
        self.assertIn("規則から読めません", C.line(u))
        self.assertIn("「年末年始」", C.line(u))

    def test_holidays_2026(self):
        h = C.holidays(2026)
        self.assertEqual(h[date(2026, 5, 6)], "振替休日")
        self.assertEqual(h[date(2026, 9, 22)], "国民の休日")
        self.assertEqual(h[date(2026, 11, 3)], "文化の日")


class SpotsData(unittest.TestCase):
    def test_kanagawa_bird_spots_have_areas_and_operator_checked(self):
        doc = O.load_spots()
        birds = [s for s in doc["spots"] if s["subject"] == "birds" and s.get("prefecture") == "神奈川県"]
        self.assertGreaterEqual(len(birds), 3)
        areas = {a["id"]: a for a in O.load_obs_bird_areas()}
        self.assertFalse(set(areas) & {a["id"] for a in PR.load_sites()[1]["bird_areas"]})   # 既定の問い合わせの区域には入れない
        for s in birds:
            self.assertIn(s["bird_area"], areas)
            self.assertIs(areas[s["bird_area"]]["active"], False)          # 既定の問い合わせ・定期実行には入れない
        blog = next(p for s in birds for p in s.get("pages") or [] if "blogspot" in p["url"])
        self.assertIn("指定管理者", blog["operator_evidence"])                  # ブログを公式とするのは、運営者だと原文で確かめたものだけ


if __name__ == "__main__":
    unittest.main()


class RecordByUrl(Base):
    def test_record_reports_new_and_duplicate_rows_per_page(self):
        r1 = O.record([rec("t-b-1", "コガモが増えました", "2026-10-28")], env=self.env, now=NOW)
        self.assertEqual(r1["by_url"], [{"url": "https://birds.example.org/", "publisher": "試験の遊水地(自然情報)", "source_class": "official",
                                         "written": 1, "duplicates": 0}])
        r2 = O.record([rec("t-b-1", "コガモが増えました", "2026-10-28")], env=self.env, now=NOW)     # 同じ日に同じ事実 → 新しい記録 0
        self.assertEqual((r2["written"], r2["by_url"][0]["written"], r2["by_url"][0]["duplicates"]), (0, 0, 1))
