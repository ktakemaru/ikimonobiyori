"""段階6c: スナップショットの合成(紅葉・野鳥)と、野鳥のデータ密度の調査。すべて通信なし(偽のデータ・偽の http_get)。
biyori-hub の tests/test_compose_and_survey.py から移した(段階12)。窓口が合成スナップショットを読む部分・台帳・文面の検査は biyori-hub 側に残っている。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H
from helpers import ROOT

from ikimonobiyori import compose, engine, profiles as ip, survey
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.fetch.live import LiveError

JST = timezone(timedelta(hours=9))
T0 = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
CFG = load_config()
TTL = CFG["compose"]["ttl_s"]
PROFS = ip.load_profiles()
SITES, _ = ip.load_sites()
SYN = json.loads((ROOT / "tests" / "fixtures" / "synthetic_inputs.json").read_text(encoding="utf-8"))


def req(interests):
    return {"schema": "biyori-request/1", "request_id": "c", "intent": "weekend_outing", "origin": {"name": "x", "lat": 35.0, "lon": 139.0},
            "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-18T23:59:00+09:00"}, "interests": interests}


def doc_for(subject, when):
    """偽のデータ(合成の入力)から、その対象だけの更新結果を作る。fetched_at は when。"""
    inputs = json.loads(json.dumps(SYN))
    inputs["fetched_at"] = when.isoformat(timespec="seconds")
    return engine.run(req([subject]), profiles=PROFS, sites=SITES, inputs=inputs, now=when)


class Compose(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def comp(self, now):
        return compose.compose(now, directory=self.d, ttl_s=TTL)

    def subjects(self, doc):
        return {p["subject"]["profile_id"] for p in doc["proposals"]}

    def test_only_autumn_updated(self):
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", T0), T0, directory=self.d)
        doc = self.comp(T0 + timedelta(minutes=5))
        self.assertEqual(self.subjects(doc), {"autumn_leaves"})
        self.assertEqual((doc["status"], doc["status_reason"]), ("partial", "component_missing"))
        self.assertTrue(any("野鳥" in w and "提案に含めていない" in w for w in doc["diagnostics"]["warnings"]))
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])

    def test_only_birds_updated(self):
        compose.update_component("birds", doc_for("birds", T0), T0, directory=self.d)
        doc = self.comp(T0 + timedelta(minutes=5))
        self.assertEqual(self.subjects(doc), {"birds"})
        self.assertTrue(any("紅葉" in w for w in doc["diagnostics"]["warnings"]))

    def test_both_updated_keeps_each_subject_and_its_own_times(self):
        t_aut, t_bird = T0, T0 + timedelta(hours=1)
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", t_aut), t_aut, directory=self.d)
        compose.update_component("birds", doc_for("birds", t_bird), t_bird, directory=self.d)
        now = T0 + timedelta(hours=1, minutes=30)
        doc = self.comp(now)
        self.assertEqual(self.subjects(doc), {"autumn_leaves", "birds"})
        self.assertEqual((doc["status"], doc.get("status_reason")), ("ok", None))
        self.assertEqual(doc["generated_at"], now.isoformat(timespec="seconds"))                  # トップレベルは合成した時刻
        by = {p["subject"]["profile_id"]: p for p in doc["proposals"]}
        self.assertEqual(by["autumn_leaves"]["details"]["component"]["generated_at"], t_aut.isoformat(timespec="seconds"))   # 提案ごとに部品の時刻
        self.assertEqual(by["birds"]["details"]["component"]["generated_at"], t_bird.isoformat(timespec="seconds"))
        self.assertEqual(set(by["autumn_leaves"]["details"]["component"]), {"subject", "generated_at", "saved_at"})   # data_as_of は複製しない
        self.assertTrue(doc["data_as_of"])                                                                    # 一覧はトップレベルに1か所
        self.assertEqual({a["source_type"] for a in doc["data_as_of"]}, {"forecast", "observation"})
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual(json.dumps(doc, sort_keys=True), json.dumps(self.comp(now), sort_keys=True))     # 決定論

    def test_updating_one_subject_does_not_touch_the_other(self):
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", T0), T0, directory=self.d)
        compose.update_component("birds", doc_for("birds", T0), T0, directory=self.d)
        before = (self.d / "birds.json").read_bytes()
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", T0 + timedelta(hours=2)), T0 + timedelta(hours=2), directory=self.d)
        self.assertEqual((self.d / "birds.json").read_bytes(), before)
        self.assertEqual([p.name for p in self.d.iterdir() if p.name.startswith(".")], [])          # 一時ファイルが残らない

    def test_stale_component_is_excluded_with_reason_and_others_continue(self):
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", T0), T0, directory=self.d)
        compose.update_component("birds", doc_for("birds", T0), T0, directory=self.d)
        now = T0 + timedelta(seconds=TTL["autumn_leaves"] + 60)            # 紅葉だけ有効期間を超える(野鳥は 7 日)
        doc = self.comp(now)
        self.assertEqual(self.subjects(doc), {"birds"})                    # 他の対象は続ける
        self.assertEqual(doc["status_reason"], "component_stale")
        w = [x for x in doc["diagnostics"]["warnings"] if "紅葉" in x]
        self.assertTrue(w and "提案に含めていない" in w[0] and "有効期間" in w[0])
        self.assertEqual(doc["details"]["components"]["autumn_leaves"]["state"], "stale")
        later = T0 + timedelta(seconds=TTL["birds"] + 60)
        doc2 = self.comp(later)
        self.assertEqual(doc2["proposals"], [])
        self.assertEqual(doc2["status_reason"], "no_fresh_component")     # 全部古い → 提案なし
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc2), [])

    def test_failure_keeps_last_good_if_fresh_otherwise_excluded(self):
        compose.update_component("autumn_leaves", doc_for("autumn_leaves", T0), T0, directory=self.d)
        compose.update_component("birds", doc_for("birds", T0), T0, directory=self.d)
        fail_at = T0 + timedelta(hours=1)
        compose.record_failure("autumn_leaves", "HTTP 429", fail_at, directory=self.d)
        doc = self.comp(fail_at + timedelta(minutes=1))                    # 紅葉は有効期間内 → 前回の結果を使う(警告つき)
        self.assertEqual(self.subjects(doc), {"autumn_leaves", "birds"})
        self.assertEqual(doc["status_reason"], "component_update_failed")
        self.assertTrue(any("更新に失敗" in w and "HTTP 429" in w for w in doc["diagnostics"]["warnings"]))
        doc2 = self.comp(T0 + timedelta(seconds=TTL["autumn_leaves"] + 60))   # 有効期間を超えた後 → 紅葉は含めない(失敗の理由も出る)
        self.assertEqual(self.subjects(doc2), {"birds"})
        self.assertTrue(any("紅葉" in w and "失敗" in w for w in doc2["diagnostics"]["warnings"]))
        # 部品がまだ無い対象の失敗 → 欠落として扱う(他は続く)
        d2 = Path(tempfile.mkdtemp())
        compose.update_component("birds", doc_for("birds", T0), T0, directory=d2)
        compose.record_failure("autumn_leaves", "ParseError", T0, directory=d2)
        doc3 = compose.compose(T0 + timedelta(minutes=1), directory=d2, ttl_s=TTL)
        self.assertEqual(self.subjects(doc3), {"birds"})
        self.assertEqual(doc3["details"]["components"]["autumn_leaves"]["state"], "missing")

    def test_nothing_at_all(self):
        doc = self.comp(T0)
        self.assertEqual((doc["proposals"], doc["status"], doc["status_reason"]), ([], "partial", "no_fresh_component"))
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])

    def test_write_snapshot_is_atomic_and_keeps_last_n(self):
        snaps = Path(tempfile.mkdtemp())
        compose.update_component("birds", doc_for("birds", T0), T0, directory=self.d)
        for i in range(5):
            now = T0 + timedelta(minutes=i)
            compose.write_snapshot(self.comp(now), snaps, now, keep_last=3)
        files = sorted(p.name for p in (snaps / "ikimonobiyori").iterdir())
        self.assertEqual(len(files), 3)
        self.assertTrue(all(not n.startswith(".") for n in files))

class SurveyAndLedger(unittest.TestCase):
    PLACES = ["軽井沢周辺", "葛西臨海公園周辺", "谷津干潟周辺", "渡良瀬遊水地周辺", "河口湖周辺", "印旛沼周辺"]

    def fake(self, status=200):
        calls = []

        def http(url):
            calls.append(url)
            if status != 200:
                return status, "{}", {}
            if "species_counts" in url:
                return 200, json.dumps({"total_results": 2, "page": 1, "per_page": 10, "results": [
                    {"count": 5, "taxon": {"id": 1, "name": "Parus minor", "preferred_common_name": "シジュウカラ", "rank": "species",
                                           "iconic_taxa_name": "x", "default_photo": {"url": "https://example.invalid/p"}}},
                    {"count": 2, "taxon": {"id": 2, "name": "Corvus macrorhynchos", "preferred_common_name": "ハシブトガラス", "rank": "species"}}]}), {}
            return 200, json.dumps({"total_results": 1234, "page": 1, "per_page": 1,
                                    "results": [{"id": 9, "user": {"login": "someone"}, "photos": [{"url": "https://example.invalid/x"}]}]}), {"Date": "x"}
        return http, calls

    def run_survey(self, http, **kw):
        return survey.run_density_survey(survey.load_survey(), T0, cfg=CFG, cache=Cache(tempfile.mkdtemp()), http_get=http, live=True,
                                         max_requests=kw.pop("max_requests", 8), unparsed_dir=tempfile.mkdtemp(), sleep=kw.pop("sleep", lambda s: None), **kw)

    def test_survey_is_seven_requests_in_order_with_interval(self):
        http, calls = self.fake()
        sleeps = []
        res = self.run_survey(http, sleep=sleeps.append)
        self.assertEqual((res["requests"], len(calls)), (7, 7))
        self.assertEqual([p["name"] for p in res["places"]], self.PLACES)
        self.assertTrue(all(p["total_results"] == 1234 and p["returned"] == 1 for p in res["places"]))
        self.assertEqual(len(sleeps), 6)
        self.assertIn("locale=ja", calls[-1])
        self.assertIn("species_counts", calls[-1])
        self.assertIn("per_page=10", calls[-1])
        self.assertEqual(res["locale"]["names"][0], {"scientific": "Parus minor", "common_name": "シジュウカラ", "count": 5})
        for u in calls[:-1]:
            self.assertIn("/v1/observations?", u)
            self.assertIn("month=10%2C11", u)
            self.assertIn("iconic_taxa=Aves", u)
            self.assertIn("quality_grade=research", u)
            self.assertIn("radius=10", u)
            self.assertIn("per_page=1", u)
            self.assertNotIn("year", u)                                    # 年は限らない
        self.assertTrue(all("api.inaturalist.org" in u for u in calls))

    def test_survey_stores_only_counts_and_rounded_places(self):
        http, _ = self.fake()
        c = Cache(tempfile.mkdtemp())
        res = survey.run_density_survey(survey.load_survey(), T0, cfg=CFG, cache=c, http_get=http, live=True, max_requests=8,
                                        unparsed_dir=tempfile.mkdtemp(), sleep=lambda s: None)
        blob = json.dumps(res, ensure_ascii=False) + "".join(p.read_text(encoding="utf-8") for p in Path(c.dir).glob("*.json"))
        for banned in ("someone", "example.invalid", "login", "photos", "default_photo"):
            self.assertNotIn(banned, blob)                                 # 観察者・写真は保存しない
        for pl in res["places"]:
            for v in (pl["lat"], pl["lon"]):
                self.assertEqual(round(v, 1), v)                           # 丸めた座標だけ

    def test_survey_stops_on_error_and_respects_limit_and_cache(self):
        for st in (429, 404, 500):
            http, calls = self.fake(status=st)
            with self.assertRaises(LiveError):
                self.run_survey(http)
            self.assertEqual(len(calls), 1)
        http, calls = self.fake()
        res = self.run_survey(http, max_requests=3)
        self.assertEqual((res["requests"], len(calls)), (3, 3))
        self.assertTrue(res["warnings"])
        c = Cache(tempfile.mkdtemp())
        http, calls = self.fake()
        survey.run_density_survey(survey.load_survey(), T0, cfg=CFG, cache=c, http_get=http, live=True, max_requests=8, unparsed_dir=tempfile.mkdtemp(), sleep=lambda s: None)
        http2, calls2 = self.fake()
        r2 = survey.run_density_survey(survey.load_survey(), T0 + timedelta(minutes=1), cfg=CFG, cache=c, http_get=http2, live=True, max_requests=8,
                                       unparsed_dir=tempfile.mkdtemp(), sleep=lambda s: None)
        self.assertEqual((r2["requests"], r2["cache_hits"], calls2), (0, 7, []))

    def test_survey_bad_shape_is_saved_and_stops(self):
        d = Path(tempfile.mkdtemp())
        with self.assertRaises(ParseError):
            survey.run_density_survey(survey.load_survey(), T0, cfg=CFG, cache=Cache(tempfile.mkdtemp()), http_get=lambda u: (200, json.dumps({"x": 1}), {}),
                                      live=True, max_requests=8, unparsed_dir=d, sleep=lambda s: None)
        self.assertEqual(len(list(d.glob("*.json"))), 1)

    def test_survey_conditions_match_the_request_and_do_not_change_thresholds(self):
        s = survey.load_survey()
        self.assertEqual(s["conditions"], {"iconic_taxa": "Aves", "quality_grade": "research", "radius_km": 10, "months": [10, 11]})
        self.assertEqual([p["name"] for p in s["places"]], self.PLACES)
        self.assertEqual([(p["lat"], p["lon"]) for p in s["places"]],
                         [(36.3, 138.6), (35.6, 139.9), (35.7, 140.0), (36.2, 139.7), (35.5, 138.8), (35.8, 140.2)])
        b = PROFS["birds"]
        vals = {q["name"]: q["value"] for q in b["method"]["params"]}
        self.assertEqual((vals["min_total_observations"], vals["window_weeks"], vals["default_radius_km"], vals["history_years"]), (30, 1, 10, 5))
        _, doc = ip.load_sites()
        self.assertEqual([(a["id"], a["lat"], a["lon"], a["radius_km"]) for a in doc["bird_areas"]], [("karuizawa", 36.3, 138.6, 10), ("kasai", 35.6, 139.9, 10), ("yatsu", 35.7, 140.0, 10)])   # 段階5a: 実測 30 以上の2か所だけ追加(半径は10のまま)

class WindowSurvey(unittest.TestCase):
    """段階5a: 窓×複数年を1リクエストで取る実測。同値性の確認が一致しなければ1リクエストで止まる。"""
    def run_it(self, first_total):
        calls = []

        def http(url):
            calls.append(url)
            if "species_counts" in url:
                return 200, json.dumps({"total_results": 1, "page": 1, "per_page": 200, "results": [{"count": 3, "taxon": {"id": 1, "name": "Parus minor", "preferred_common_name": "シジュウカラ"}}]}), {}
            return 200, json.dumps({"total_results": first_total if len(calls) == 1 else 50, "page": 1, "per_page": 1, "results": [{"id": 1, "user": {"login": "x"}}]}), {}
        s = survey.load_survey(ROOT / "ikimonobiyori" / "data" / "window_survey.yaml")
        res = survey.run_density_survey(s, T0, cfg=CFG, cache=Cache(tempfile.mkdtemp()), http_get=http, live=True, max_requests=8,
                                        unparsed_dir=tempfile.mkdtemp(), sleep=lambda x: None)
        return res, calls

    def test_match_runs_eight_requests_with_multi_year_params(self):
        res, calls = self.run_it(11)
        self.assertEqual(len(calls), 8)
        self.assertTrue(res["gate"]["match"])
        u = calls[0]
        for frag in ("year=2021%2C2022%2C2023%2C2024%2C2025", "month=10", "day=10%2C11", "24", "radius=10", "per_page=1", "lat=36.3", "lng=138.6"):
            self.assertIn(frag, u)
        self.assertIn("day=3%2C4", calls[6])
        self.assertIn("locale=ja", calls[7])
        self.assertIn("species_counts", calls[7])
        self.assertEqual([i["role"] for i in res["items"]], ["equivalence", "measure", "measure", "measure", "reference", "reference", "reference_wide"])

    def test_mismatch_stops_after_first_request(self):
        res, calls = self.run_it(12)
        self.assertEqual(len(calls), 1)
        self.assertFalse(res["gate"]["match"])
        self.assertTrue(any("同値性" in w for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()


class AbsenceWording(unittest.TestCase):
    """野鳥が 0 件(件数不足)のとき: 「記録が少なすぎて提案を出していません」の方式で、「鳥がいない」と読める断定を出さない(エンジンの警告の原文)。
    最終文の検査(checktext)と定型文(render)の部分は biyori-hub 側のテスト。"""
    SPARSE = ROOT / "tests" / "fixtures" / "synthetic_inaturalist_sparse.json"

    def test_engine_warning_has_no_absence_claim(self):
        d = json.loads(self.SPARSE.read_text(encoding="utf-8"))["inputs"]
        doc = engine.run(req(["birds"]), profiles=PROFS, sites=SITES, inputs=d, now=T0)
        self.assertEqual(doc["proposals"], [])
        warn = [w for w in doc["diagnostics"]["warnings"] if "提案を出さない" in w]
        self.assertEqual(len(warn), 1)
        self.assertIn("観察記録の総数 9", warn[0])
        for w in ("鳥がいない", "鳥はいない", "鳥が見られ", "観察できない", "見られません"):
            self.assertNotIn(w, warn[0])


if __name__ == "__main__":
    unittest.main()
