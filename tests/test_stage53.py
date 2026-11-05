"""段階53 第1部: 花の写真（開花 ＞ つぼみ。果実・枯れ姿は使わない）。通信しない。"""
import json
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_photos as GP, wildflower_page
from ikimonobiyori.fetch import commons_photos as CP, inat_photos
from test_stage39 import Net, cand, search, taxon, NOSLEEP, TODAY

POLICY = guide.load_policy()
PH = POLICY["photos"]
PP = PH["phenology"]


def obs(*photo_ids, lic="cc-by"):
    return json.dumps({"results": [{"photos": [{"id": i, "license_code": lic, "attribution": f"(c) 撮影者{i}, some rights reserved",
                                                "url": f"https://inaturalist-open-data.s3.amazonaws.com/photos/{i}/square.jpg"} for i in photo_ids]}]})


EMPTY = json.dumps({"results": []})
ROW = {"name": "クロユリ試験", "scientific": "Fritillaria testus", "taxon_id": 8101}


class Fetch(unittest.TestCase):
    def run_fetch(self, net, rows=(ROW,)):
        return inat_photos.fetch_phenology(list(rows), http_get=net.get, http_bytes=net.get_bytes, ph=PH, max_requests=20,
                                           has_cache=lambda _t: False, today=TODAY, sleep=NOSLEEP)

    def test_flowering_is_preferred_over_budding(self):
        net = Net({"term_value_id=13": (200, obs(11)), "term_value_id=15": (200, obs(22))})
        got, unused, _rep = self.run_fetch(net)
        self.assertEqual((got[0]["meta"]["state"], got[0]["meta"]["photo_id"], unused), ("開花", 11, {}))
        self.assertTrue(all("term_value_id=15" not in u for u in net.calls))            # 開花が見つかれば、つぼみは探さない
        self.assertEqual(got[0]["meta"]["rule"], PP["rule_version"]["value"])
        self.assertIn("/medium.", net.bytes_calls[0])

    def test_budding_when_no_flowering(self):
        net = Net({"term_value_id=13": (200, EMPTY), "term_value_id=15": (200, obs(22))})
        got, _un, _rep = self.run_fetch(net)
        self.assertEqual((got[0]["meta"]["state"], got[0]["meta"]["photo_id"]), ("つぼみ", 22))

    def test_neither_gives_no_photo(self):
        net = Net({"term_value_id=13": (200, EMPTY), "term_value_id=15": (200, EMPTY)})
        got, unused, _rep = self.run_fetch(net)
        self.assertEqual(got, [])
        self.assertIn("クロユリ試験", unused)

    def test_license_outside_the_allowed_list_is_not_used(self):
        net = Net({"term_value_id=13": (200, obs(11, lic="cc-by-nc")), "term_value_id=15": (200, EMPTY)})
        self.assertEqual(self.run_fetch(net)[0], [])

    def test_the_query_uses_the_phenology_annotation_and_license_filter(self):
        u = inat_photos.observations_url(8101, 13, PH)
        for part in ("term_id=12", "term_value_id=13", "taxon_id=8101", "photo_license=cc0%2Ccc-by%2Ccc-by-sa", "quality_grade=research"):
            self.assertIn(part, u)


class Ensure(unittest.TestCase):
    def ensure(self, names, net, theme="野草", phenology=True):
        return GP.ensure(names, theme=theme, policy=POLICY, http_get=net.get, http_bytes=net.get_bytes, today=TODAY, sleep=NOSLEEP, phenology=phenology)

    def test_new_species_gets_a_flowering_photo_with_state(self):
        net = Net({"/taxa?": (200, search(cand(8201, "Iris testus", "試験アヤメ"))), "term_value_id=13": (200, obs(31)), "term_value_id=15": (200, EMPTY)})
        self.assertEqual(self.ensure(["試験アヤメ"], net)["results"], {"試験アヤメ": "saved"})
        self.assertEqual(GP.load_photo(8201)[0]["state"], "開花")

    def test_old_cache_is_reevaluated_and_the_rejected_photo_is_kept_with_a_mark(self):
        # 古い規則で取った写真（果実の写真だったアヤメなど）: 規則の印がない
        net0 = Net({"/taxa?": (200, search(cand(8202, "Iris oldus", "古いアヤメ"))), "/taxa/8202": (200, taxon(8202, "Iris oldus"))})
        self.ensure(["古いアヤメ"], net0, phenology=False)
        self.assertNotIn("rule", GP.load_photo(8202)[0])
        net = Net({"term_value_id=13": (200, obs(41)), "term_value_id=15": (200, EMPTY)})
        self.assertEqual(self.ensure(["古いアヤメ"], net)["results"], {"古いアヤメ": "saved"})
        meta = GP.load_photo(8202)[0]
        self.assertEqual((meta["state"], meta["photo_id"]), ("開花", 41))
        rej = list((GP.cache_dir() / PP["rejected_dir"]).glob("8202-*.json"))                # 消さずに残し、不採用の印を付ける
        self.assertEqual(len(rej), 1)
        self.assertEqual(json.loads(rej[0].read_text(encoding="utf-8"))["rejected_by_rule"], PP["rule_version"]["value"])

    def test_old_cache_without_a_better_photo_stays_as_unknown_and_is_not_searched_again(self):
        net0 = Net({"/taxa?": (200, search(cand(8203, "Iris unknownus", "不明アヤメ"))), "/taxa/8203": (200, taxon(8203, "Iris unknownus"))})
        self.ensure(["不明アヤメ"], net0, phenology=False)
        net = Net({"term_value_id=13": (200, EMPTY), "term_value_id=15": (200, EMPTY)})
        self.ensure(["不明アヤメ"], net)
        self.assertEqual(GP.load_photo(8203)[0]["state"], "不明")
        net2 = Net({})
        self.assertEqual(self.ensure(["不明アヤメ"], net2)["results"], {"不明アヤメ": "cached"})
        self.assertEqual(net2.n, 0)                                                         # 評価済み。もう探さない

    def test_birds_are_not_affected(self):
        self.assertIsNone(GP.phenology_cfg("野鳥", POLICY))
        self.assertIsNone(GP.phenology_cfg("紅葉", POLICY))


class Commons(unittest.TestCase):
    ROW = {"scientific": "Primula testus"}

    def info(self, text, lic="CC BY-SA 4.0"):
        return {"descriptionurl": "https://commons.wikimedia.org/wiki/File:x.jpg", "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/500px-x.jpg",
                "mime": "image/jpeg", "license_short": lic, "artist": "A", "restrictions": "", "categories": text, "description": text}

    def pick(self, items):
        cm = PH["commons"]
        pages = [(t, self.info(txt)) for t, txt in items]
        return CP.scientific_pick(pages, self.ROW, cm, [t for t, _ in items], PP)[0]

    def test_flower_words_win_over_unknown_and_fruit_is_never_used(self):
        pick = self.pick([("File:a.jpg", "Primula testus fruit capsule"), ("File:b.jpg", "Primula testus"), ("File:c.jpg", "Primula testus flowers")])
        self.assertEqual((pick["title"], pick["state"]), ("File:c.jpg", "開花"))

    def test_bud_beats_unknown_and_only_fruit_gives_nothing(self):
        pick = self.pick([("File:b.jpg", "Primula testus"), ("File:d.jpg", "Primula testus bud")])
        self.assertEqual((pick["title"], pick["state"]), ("File:d.jpg", "つぼみ"))
        self.assertIsNone(self.pick([("File:a.jpg", "Primula testus seed"), ("File:e.jpg", "Primula testus 果実")]))

    def test_unknown_is_kept_when_nothing_better(self):
        self.assertEqual(self.pick([("File:b.jpg", "Primula testus")])["state"], "不明")


class PageDisplay(unittest.TestCase):
    def test_state_line_shows_scientific_name_and_state_and_bud_note(self):
        self.assertEqual(wildflower_page.state_text({"scientific": "Fritillaria camschatcensis", "state": "つぼみ"}, POLICY),
                         "Fritillaria camschatcensis ／ 状態: つぼみ" + PP["bud_note"])
        self.assertEqual(wildflower_page.state_text({"scientific": "Iris x", "state": "開花"}, POLICY), "Iris x ／ 状態: 開花")
        self.assertEqual(wildflower_page.state_text({"scientific": "Iris x"}, POLICY), "Iris x ／ 状態: 不明")        # 古いキャッシュ


if __name__ == "__main__":
    unittest.main()


# ---- 第2部: まつり・イベント ----
import copy
from datetime import date

from ikimonobiyori import festivals as FE, season
from ikimonobiyori import ask_verify as V
from test_stage51 import STRICT, GOOD51, c51


class Weekday(unittest.TestCase):
    TODAY = date(2026, 11, 6)

    def test_2025_and_2024_calendars_are_previous_year(self):
        self.assertTrue(season.previous_year_by_weekday("10月25日(土)～11月24日(月)", self.TODAY))        # 2025年の暦
        self.assertTrue(season.previous_year_by_weekday("10月26日（土）～11月24日（日）", self.TODAY))     # 2024年の暦
        self.assertTrue(season.previous_year_by_weekday("11月15日（土）", self.TODAY))                    # 2026年の11/15は日曜

    def test_2026_calendar_passes_and_no_weekday_is_not_judged(self):
        self.assertFalse(season.previous_year_by_weekday("11月1日（日）～11月30日（月）", self.TODAY))
        self.assertFalse(season.previous_year_by_weekday("10/24(土)〜11/23(月)", self.TODAY))
        self.assertIsNone(season.previous_year_by_weekday("2026年10月24日 - 2026年11月23日", self.TODAY))

    def test_check_reports_the_mismatching_fragments(self):
        r = season.weekday_check("10/25(土)と11/15(日)", 2026)
        self.assertEqual(r["checked"], 2)
        self.assertEqual(len(r["mismatches"]), 1)


class FestivalStatus(unittest.TestCase):
    def doc(self, **kw):
        f = {"id": "x", "name": "試験もみじまつり", "spots": ["s1"], "organizer": "試験協会", "organizer_class": "official", "start": "2026-11-01", "end": "2026-11-30",
             "url": "https://example.org/", "raw": ["11月1日（日）～11月30日（月）"], "lightup": None}
        f.update(kw)
        return {"festivals": [f]}

    def test_ongoing_upcoming_and_ended_are_computed_from_today(self):
        d = self.doc()
        self.assertEqual(FE.for_spot("s1", date(2026, 11, 6), d)[0]["period_line"], "主催者が設定した期間: まつり期間中(11/1〜11/30)")
        self.assertEqual(FE.for_spot("s1", date(2026, 10, 25), d)[0]["period_line"], "主催者が設定した期間: あと7日で開始(11/1〜11/30)")
        self.assertEqual(FE.for_spot("s1", date(2026, 11, 1), self.doc(start="2026-11-01"))[0]["state"], "ongoing")
        self.assertEqual(FE.for_spot("s1", date(2026, 12, 1), d), [])                      # 終了したものは出さない

    def test_previous_season_year_missing_and_weekday_mismatch_are_not_used(self):
        t = date(2026, 11, 6)
        self.assertEqual(FE.for_spot("s1", t, self.doc(start="2025-11-01", end="2025-11-30")), [])
        self.assertEqual(FE.for_spot("s1", t, self.doc(start=None)), [])
        self.assertEqual(FE.for_spot("s1", t, self.doc(raw=["10月25日(土)～11月24日(月)"])), [])    # 2025年の暦

    def test_lightup_line_has_period_and_hours(self):
        d = self.doc(lightup={"start": "2026-11-06", "end": "2026-11-29", "hours": "16:00〜21:00", "note": None})
        self.assertEqual(FE.for_spot("s1", date(2026, 11, 6), d)[0]["lightup_line"], "ライトアップ: 11/6〜11/29 16:00〜21:00")

    def test_the_real_data_is_all_usable_this_season_and_mitake_is_secondary(self):
        t = date(2026, 11, 6)
        self.assertEqual(FE.dropped(t), {})
        by = {f["id"]: f for f in FE.load()["festivals"]}
        self.assertEqual(by["mitake-tenku-momiji-2026"]["organizer_class"], "secondary")
        self.assertEqual((by["mitake-tenku-momiji-2026"]["start"], by["mitake-tenku-momiji-2026"]["end"]), ("2026-10-24", "2026-11-23"))
        self.assertEqual(by["nagatoro-koyo-2026"]["organizer_class"], "official")
        self.assertEqual(FE.dropped(date(2025, 11, 6)).keys(), by.keys())                  # 前年の日付に対しては、どれも今シーズンの情報ではない


class FestivalAnswerRules(unittest.TestCase):
    def facts(self, with_state):
        f = copy.deepcopy(STRICT)
        f["lines"]["practical_rules"] = True
        for c in f["subjects"]["birds"]["candidates"]:
            c["practical"] = []
            c["festivals"] = []
        c0 = f["subjects"]["birds"]["candidates"][0]
        c0["festivals"] = [{"name": "試験まつり", "url": "https://birds.example.org/", "period_line": "主催者が設定した期間: まつり期間中(11/1〜11/30)"}]
        if not with_state:
            c0["current"] = None
        return f, c0["name"]

    def test_festival_period_must_be_a_separate_line_from_the_state(self):
        f, name = self.facts(True)
        bad = GOOD51 + f"{name}: 主催者が設定した期間: まつり期間中(11/1〜11/30)で、11/3時点で見ごろです。\n"
        self.assertIn("festival_mixed_with_state", c51(bad, f))
        ok = GOOD51 + f"{name}: 主催者が設定した期間: まつり期間中(11/1〜11/30)です。\n"
        self.assertNotIn("festival_mixed_with_state", c51(ok, f))

    def test_no_state_candidate_needs_the_sentence(self):
        f, name = self.facts(False)
        self.assertIn("festival_no_state_missing", c51(GOOD51, f))
        self.assertNotIn("festival_no_state_missing", c51(GOOD51 + "色づき状況は確認できていません。\n", f))


# ---- 第3部: ビジターセンターの台帳（承認待ち）とウェザーニュース由来の承認取り消し ----
import yaml as _yaml
from ikimonobiyori import sources as _sources


class Ledger(unittest.TestCase):
    SEC = {s["id"]: s for s in _yaml.safe_load((_sources.SECONDARY_SOURCES_DIR / "autumn_leaves.yaml").read_text(encoding="utf-8"))["sources"]}

    def test_visitor_centers_are_pending_and_never_approved_by_the_code(self):
        for k in ("yamakei-takao-visitor-center", "yamakei-mitake-visitor-center"):
            self.assertEqual(self.SEC[k]["approval"]["status"], "pending", k)
            self.assertIn("info_id=", self.SEC[k]["url"])
            self.assertEqual(self.SEC[k]["terms"]["status"], "not_checked")

    def test_weathernews_derived_entries_are_revoked(self):
        self.assertEqual(self.SEC["walkerplus-koyo-forecast-east"]["approval"]["status"], "revoked")
        self.assertEqual(self.SEC["nihon-kisho-koyo-forecast"]["approval"]["status"], "revoked")
        self.assertEqual(self.SEC["walkerplus-koyo-kanagawa"]["approval"]["status"], "approved")        # ウォーカープラスの一覧（例年の時期）は引き続き使える

    def test_the_ledger_passes_the_check(self):
        self.assertEqual(dict((p.name, e) for p, e in _sources.check_all_secondary())["autumn_leaves.yaml"], [])
