"""イキモノビヨリ v0 のテスト(通信なし。ソケット禁止)。入力はすべて合成フィクスチャ(synthetic)。
biyori-hub の tests/test_ikimonobiyori.py から移した(段階12)。窓口(plan・checktext・render)との統合の部分は biyori-hub 側に残っている。"""
import ast
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H
from helpers import ROOT, run_child, write

from ikimonobiyori import engine, profiles as ip
from ikimonobiyori.fetch import ParseError, inaturalist, open_meteo
from ikimonobiyori.methods import observation_frequency as obsfreq
from ikimonobiyori.methods import temperature_progression as tprog

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
INPUTS_PATH = ROOT / "tests" / "fixtures" / "synthetic_inputs.json"
PROFILES = ip.load_profiles()
SITES, SITES_DOC = ip.load_sites()
M065 = "m065"      # 立山(雄山): 合成の気温は冷え込みが強い
M001 = "m001"      # 谷川岳: 色づき始め


def inputs():
    return json.loads(INPUTS_PATH.read_text(encoding="utf-8"))


def req(interests, start="2026-10-17T00:00:00+09:00", end="2026-10-18T23:59:00+09:00"):
    return {"schema": "biyori-request/1", "request_id": "t", "intent": "weekend_outing", "time_range": {"start": start, "end": end},
            "origin": {"name": "x", "lat": 35.0, "lon": 139.0}, "interests": list(interests)}


def run(interests, profs=None, inp=None, **kw):
    return engine.run(req(interests, **kw), profiles=profs or PROFILES, sites=SITES, inputs=inp or inputs(), now=NOW)


def ok(doc):
    return H.schema_errors("biyori-proposal/1", doc)


class Fixtures(unittest.TestCase):
    def test_fixture_is_marked_synthetic(self):
        self.assertIn("synthetic", INPUTS_PATH.name)
        d = inputs()
        self.assertTrue(d["synthetic"])
        self.assertIn("SYNTHETIC", d["note"])
        doc = run(["birds", "autumn_leaves"])
        self.assertTrue(any("SYNTHETIC" in w for w in doc["diagnostics"]["warnings"]))
        for p in doc["proposals"]:
            self.assertTrue(p["details"]["synthetic"])
            self.assertTrue(all("SYNTHETIC" in e["source"] for e in p["evidence"] if e["source_type"] in ("observation", "forecast")))

    def test_sites_copied_once_with_origin_recorded(self):
        c = SITES_DOC["copied_from"]
        self.assertEqual(c["repo"], "yamabiyori")
        self.assertEqual(len(c["commit"]), 40)
        self.assertEqual(c["count"], len(SITES_DOC["sites"]))
        areas = SITES_DOC["bird_areas"]                              # 野鳥の場所: 軽井沢周辺(暫定・ユーザー確認待ち)。approved のものだけが問い合わせの対象
        self.assertEqual([(a["name"], a["status"], a["lat"], a["lon"], a["location_precision"]) for a in areas],
                         [("軽井沢周辺", "approved", 36.3, 138.6, "area_10km"), ("葛西臨海公園周辺", "approved", 35.6, 139.9, "area_10km"),
                          ("谷津干潟周辺", "approved", 35.7, 140.0, "area_10km")])     # 段階5a: 実測が 30 以上の場所だけ追加
        self.assertEqual((areas[0]["id"], areas[0]["radius_km"], areas[0]["provisional"]), ("karuizawa", 10, True))     # 暫定(ユーザー確認待ち)
        s = SITES[M065]
        self.assertTrue(all(k in s for k in ("name", "lat", "lon", "elevation_m", "region", "kind")))


class Contract(unittest.TestCase):
    def test_schema_and_determinism(self):
        a, b = run(["birds", "autumn_leaves"]), run(["birds", "autumn_leaves"])
        self.assertEqual(ok(a), [])
        self.assertEqual(json.dumps(a, ensure_ascii=False, sort_keys=True), json.dumps(b, ensure_ascii=False, sort_keys=True))
        self.assertEqual(a["agent"]["id"], "ikimonobiyori")
        self.assertIsNone(a["agent"]["commit"])                       # 新規ビヨリ: source なし

    def test_band_never_exceeds_maybe_while_unvalidated(self):
        doc = run(["birds", "autumn_leaves"])
        self.assertLessEqual({p["suitability"]["band"] for p in doc["proposals"]}, {"maybe", "no"})
        self.assertIn("maybe", {p["suitability"]["band"] for p in doc["proposals"]})
        # プロファイルが go を指定しても、max_band(maybe)で抑える
        profs = copy.deepcopy(PROFILES)
        profs["autumn_leaves"]["method"]["band_map"]["peak"] = "go"
        doc = run(["autumn_leaves"], profs)
        self.assertNotIn("go", {p["suitability"]["band"] for p in doc["proposals"]})
        self.assertIn("maybe", {p["suitability"]["band"] for p in doc["proposals"]})
        profs["birds"]["method"]["params"] = [dict(q, value=0.0) if q["name"] == "maybe_min_relative_frequency" else q
                                              for q in profs["birds"]["method"]["params"]]
        self.assertNotIn("go", {p["suitability"]["band"] for p in run(["birds"], profs)["proposals"]})

    def test_confidence_method_validated_and_value_null(self):
        for p in run(["birds", "autumn_leaves"])["proposals"]:
            c = p["uncertainty"]["confidence"]
            self.assertIs(c["validated"], False)
            self.assertIsNone(c["value"])
            self.assertEqual(c["method"], "observation-frequency" if ":birds:" in p["id"] else "heuristic-unvalidated")

    def test_evidence_has_source_type_url_and_last_updated(self):
        for p in run(["birds", "autumn_leaves"])["proposals"]:
            for e in p["evidence"]:
                self.assertIn(e["source_type"], ("forecast", "observation", "static_reference"))
                self.assertIn("url", e)
                self.assertIn("last_updated", e)
            real = [e for e in p["evidence"] if e["source_type"] in ("observation", "forecast")]
            self.assertTrue(all(e["url"].startswith("https://") for e in real))
        birds = [p for p in run(["birds"])["proposals"]]
        self.assertTrue(all(e["last_updated"] == "2025-10-19" for p in birds for e in p["evidence"]))   # 最新の観察日

    def test_missing_last_updated_is_null_with_warning(self):
        inp = inputs()
        for q in inp["birds"][0]["queries"]:
            q["latest_observations"] = None
        doc = run(["birds"], inp=inp)
        self.assertTrue(all(e["last_updated"] is None for p in doc["proposals"] for e in p["evidence"]))
        self.assertTrue(any("最終更新日" in w for w in doc["diagnostics"]["warnings"]))

    def test_phenology_stage_and_calendar_day(self):
        doc = run(["autumn_leaves"])
        st = {p["place"]["name"]: p["phenology_stage"] for p in doc["proposals"] if p["id"].endswith("2026-10-17:" + M065) or p["id"].endswith("2026-10-17:" + M001)}
        self.assertEqual(st, {"立山(雄山)": "peak", "谷川岳": "early_bloom"})
        self.assertEqual({p["phenology_stage"] for p in doc["proposals"]}, {"peak", "early_bloom", "before_bud"})
        for p in run(["birds", "autumn_leaves"])["proposals"]:
            self.assertEqual(p["time_window"]["kind"], "calendar_day")
            self.assertTrue(p["time_window"]["start"].endswith("+09:00"))
        self.assertTrue(all("phenology_stage" not in p for p in run(["birds"])["proposals"]))


class Seasons(unittest.TestCase):
    def test_out_of_season_returns_not_applicable_without_proposals(self):
        doc = run(["autumn_leaves"], start="2026-02-10T00:00:00+09:00", end="2026-02-11T23:59:00+09:00")
        self.assertEqual((doc["status"], doc["status_reason"], doc["proposals"]), ("not_applicable", "out_of_season", []))
        self.assertEqual(ok(doc), [])

    def test_skeleton_profiles_return_not_applicable(self):
        for interest in ("cherry_blossom", "wildflowers", "higanbana", "sunflower", "fireflies", "bioluminescence"):
            doc = run([interest])
            self.assertEqual((doc["status"], doc["status_reason"], doc["proposals"]), ("not_applicable", "profile_skeleton", []), interest)
            self.assertEqual(ok(doc), [])
        for pid in ("cherry_blossom", "higanbana", "sunflower", "fireflies", "bioluminescence"):
            self.assertEqual(PROFILES[pid]["status"], "skeleton")
            self.assertIsNone(PROFILES[pid]["season"]["months"])         # 出典のない月は決めない(未確認)

    def test_skeleton_out_of_season_when_months_are_known(self):
        profs = copy.deepcopy(PROFILES)
        profs["cherry_blossom"]["status"] = "implemented"                 # 期間外の判定を試す(実装済みとみなし、months を与える)
        profs["cherry_blossom"]["season"]["months"] = [3, 4]
        profs["cherry_blossom"]["method"]["params"] = []
        doc = run(["cherry_blossom"], profs)
        self.assertEqual((doc["status"], doc["status_reason"]), ("not_applicable", "out_of_season"))

    def test_mixed_subjects_are_partial_with_warnings(self):
        doc = run(["autumn_leaves", "cherry_blossom"])
        self.assertEqual(doc["status"], "partial")
        self.assertTrue(doc["proposals"])
        self.assertTrue(any("cherry_blossom" in w and "骨組み" in w for w in doc["diagnostics"]["warnings"]))

    def test_no_matching_profile(self):
        doc = run(["hiking"])
        self.assertEqual((doc["status"], doc["status_reason"]), ("not_applicable", "no_matching_profile"))

    def test_missing_temperatures_are_not_filled_with_zero(self):
        inp = inputs()
        series = inp["temperatures"][M065]["daily"]["temperature_2m_min"]
        series[5] = None
        doc = run(["autumn_leaves"], inp=inp)
        w = [x for x in doc["diagnostics"]["warnings"] if "そろわない" in x]
        self.assertTrue(w)
        ids = {p["id"] for p in doc["proposals"]}
        self.assertNotIn(f"ikimonobiyori:autumn_leaves:2026-10-17:{M065}", ids)       # 欠損を含む窓は提案にしない
        self.assertEqual(ok(doc), [])


class Birds(unittest.TestCase):
    def test_location_is_rounded_to_precision_and_care_attached(self):
        for p in run(["birds"])["proposals"]:
            self.assertEqual(p["place"]["location_precision"], "area_10km")
            self.assertEqual((p["place"]["lat"], p["place"]["lon"]), (35.7, 139.1))       # 35.678912 / 139.123456 を小数1桁に
            self.assertIs(p["care"]["do_not_disclose_exact_location"], True)
            self.assertEqual(p["care"]["manners"], ["巣・ねぐらに近づかない", "給餌をしない", "録音の再生で誘引しない"])
            self.assertEqual(p["subject"]["category"], "observation_record")
            blob = json.dumps(p, ensure_ascii=False)
            for exact in ("35.678912", "139.123456"):
                self.assertNotIn(exact, blob)                                           # 正確な座標が出力のどこにもない(出典 URL も)
        profs = copy.deepcopy(PROFILES)
        profs["birds"]["care"]["location_precision"] = "area_1km"
        self.assertEqual(run(["birds"], profs)["proposals"][0]["place"]["lat"], 35.68)
        self.assertEqual(engine.round_coord(35.678912, "exact"), 35.678912)

    def test_scores_use_named_scale_and_exact_values(self):
        doc = run(["birds"])
        p = next(x for x in doc["proposals"] if x["id"].endswith("Parus minor") and "2026-10-17" in x["id"])
        sc = p["suitability"]["score"]
        self.assertEqual((sc["scale"], sc["go_threshold"]), ("ikimonobiyori-birds-relative-frequency-0-1", None))
        ev = {e["metric"]: e["value"] for e in p["evidence"]}
        self.assertEqual(sc["value"], ev["species_observations"] / ev["total_observations"])
        self.assertTrue(0 <= sc["value"] <= 1)

    def test_too_few_observations_gives_no_proposal(self):
        inp = inputs()
        for q in inp["birds"][0]["queries"]:
            for y in q["years"].values():
                for r in y["results"]:
                    r["count"] = 0
        doc = run(["birds"], inp=inp)
        self.assertEqual(doc["proposals"], [])
        self.assertTrue(any("min_total_observations" in w for w in doc["diagnostics"]["warnings"]))
        self.assertEqual(doc["status"], "ok")                                     # 件数不足は結果(insufficient_data)。失敗ではない
        self.assertTrue(any(w.startswith("[insufficient_data] ") for w in doc["diagnostics"]["warnings"]))

    def test_frequencies_are_deterministic_and_sorted(self):
        rows = [[{"name": "b", "common_name": None, "taxon_id": 1, "count": 5}, {"name": "a", "common_name": None, "taxon_id": 2, "count": 5}]]
        r = obsfreq.relative_frequencies(rows, min_total=1, top_n=5)
        self.assertEqual([s["name"] for s in r["species"]], ["a", "b"])        # 同率は学名の昇順
        self.assertEqual(r["species"][0]["relative_frequency"], 0.5)
        self.assertFalse(obsfreq.relative_frequencies(rows, min_total=11, top_n=5)["enough"])
        self.assertEqual(obsfreq.band_for(0.9, maybe_min=0.05, max_band="maybe"), "maybe")
        self.assertEqual(obsfreq.band_for(0.01, maybe_min=0.05, max_band="maybe"), "no")


class Methods(unittest.TestCase):
    def test_temperature_progression(self):
        s = {f"2026-10-{d:02d}": 10.0 - d % 3 for d in range(1, 15)}
        m = tprog.mean_tmin(s, datetime(2026, 10, 10).date(), 7)
        self.assertAlmostEqual(m, sum(s[f"2026-10-{d:02d}"] for d in range(4, 11)) / 7)
        self.assertIsNone(tprog.mean_tmin(s, datetime(2026, 10, 3).date(), 7))     # 足りない日は None(0 で埋めない)
        self.assertEqual(tprog.stage_for(5.0, start=8, advance=6), "peak")
        self.assertEqual(tprog.stage_for(6.0, start=8, advance=6), "peak")
        self.assertEqual(tprog.stage_for(7.0, start=8, advance=6), "early_bloom")
        self.assertEqual(tprog.stage_for(9.0, start=8, advance=6), "before_bud")
        self.assertIsNone(tprog.stage_for(None, start=8, advance=6))
        self.assertEqual(tprog.progress(9.0, start=8, strong=5), 0.0)
        self.assertEqual(tprog.progress(4.0, start=8, strong=5), 1.0)
        self.assertAlmostEqual(tprog.progress(6.5, start=8, strong=5), 0.5)

    def test_profile_values_drive_the_result_not_the_code(self):
        base = {p["id"]: p["phenology_stage"] for p in run(["autumn_leaves"])["proposals"]}
        profs = copy.deepcopy(PROFILES)
        for q in profs["autumn_leaves"]["method"]["params"]:
            if q["name"] == "advance_min_temp_c":
                q["value"] = 3                                   # 見頃の目安を厳しくすると、立山(M=4.0)は見頃でなくなる
        changed = {p["id"]: p["phenology_stage"] for p in run(["autumn_leaves"], profs)["proposals"]}
        self.assertEqual(base[f"ikimonobiyori:autumn_leaves:2026-10-17:{M065}"], "peak")
        self.assertEqual(changed[f"ikimonobiyori:autumn_leaves:2026-10-17:{M065}"], "early_bloom")

    def test_no_threshold_literals_in_code(self):
        # コードに数値の閾値を直接書かない: 数値リテラルは 0/1/2/7(暦・小数桁・添字)だけ
        allowed = {0, 1, 2, 7, 9}      # 0/1/2: 添字・小数桁・単位 / 7: 1週=7日 / 9: JST の UTC オフセット(時間)。いずれも閾値ではない
        bad = []
        files = [ROOT / "ikimonobiyori" / "engine.py"] + list((ROOT / "ikimonobiyori" / "methods").glob("*.py")) +             list((ROOT / "ikimonobiyori" / "fetch").glob("*.py"))
        for f in files:
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                    if n.value not in allowed:
                        bad.append((f.name, n.lineno, n.value))
        self.assertEqual(bad, [], "閾値らしい数値リテラルがコードにある(プロファイルへ)")

    def test_no_vendor_imports(self):
        for f in (ROOT / "ikimonobiyori").rglob("*.py"):
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                names = [n.module] if isinstance(n, ast.ImportFrom) and n.module else [a.name for a in n.names] if isinstance(n, ast.Import) else []
                for nm in names:
                    self.assertFalse(nm.split(".")[0] in ("mountain_weather_core", "mountain_weather_mvp", "explore_hoshibiyori", "vendor"), (f.name, nm))


class Parsers(unittest.TestCase):
    def test_inaturalist_parser_rejects_unexpected_shapes(self):
        rows, total = inaturalist.parse_species_counts({"total_results": 1, "results": [{"count": 3, "taxon": {"id": 1, "name": "Parus minor"}}]})
        self.assertEqual((rows[0]["name"], rows[0]["count"], total), ("Parus minor", 3, 1))
        for bad in ({}, {"results": "x"}, {"results": [{"count": "3", "taxon": {"name": "a"}}]}, {"results": [{"count": 3}]},
                    {"results": [{"count": 3, "taxon": {"id": 1}}]}):
            with self.assertRaises(ParseError):
                inaturalist.parse_species_counts(bad)
        self.assertEqual(inaturalist.parse_latest_observed({"results": [{"observed_on": "2025-01-02"}, {"observed_on": "2025-03-04"}]}), "2025-03-04")
        self.assertIsNone(inaturalist.parse_latest_observed({"results": []}))

    def test_open_meteo_parser(self):
        d = open_meteo.parse_daily_tmin({"daily": {"time": ["2026-10-01", "2026-10-02"], "temperature_2m_min": [8.1, None]}})
        self.assertEqual(d, {"2026-10-01": 8.1, "2026-10-02": None})           # null は None のまま
        for bad in ({}, {"daily": {"time": ["a"], "temperature_2m_min": [1, 2]}}, {"daily": {"time": ["a"], "temperature_2m_min": ["x"]}}):
            with self.assertRaises(ParseError):
                open_meteo.parse_daily_tmin(bad)

    def test_query_builders_are_pure(self):
        q = inaturalist.species_counts_query(lat=35.0, lng=139.0, radius_km=10, center=datetime(2026, 10, 17).date(), year=2025,
                                             window_weeks=1, iconic_taxa="Aves", quality_grade="research")
        self.assertEqual((q["params"]["d1"], q["params"]["d2"]), ("2025-10-10", "2025-10-24"))
        self.assertTrue(q["url"].startswith("https://api.inaturalist.org/v1/observations/species_counts?"))
        m = open_meteo.daily_query(lat=36.0, lon=138.0, past_days=7, forecast_days=3)
        self.assertEqual(m["params"]["timezone"], "Asia/Tokyo")
        plan = engine.plan_queries(req(["birds", "autumn_leaves"]), PROFILES, [{"name": "a", "lat": 35.0, "lon": 139.0}], SITES, today=NOW.date())
        self.assertEqual(len([x for x in plan if x["kind"] == "birds"]), 2 * 5)      # 2日 × 過去5年
        self.assertEqual(len([x for x in plan if x["kind"] == "autumn_leaves"]), len(SITES))


class ProfileSchema(unittest.TestCase):
    def test_all_profiles_valid_and_params_documented(self):
        self.assertEqual(set(PROFILES), {"birds", "autumn_leaves", "cherry_blossom", "higanbana", "sunflower", "fireflies", "bioluminescence",
                                         "wintering_birds", "flowers"})                       # wintering_birds は段階16 C、flowers は段階17 フェーズ4 で足した(指示書)
        for pid, p in PROFILES.items():
            self.assertEqual(ip.validate_profile(p), [], pid)
            for q in p["method"].get("params") or []:
                self.assertIn("provisional", q)
                self.assertTrue(q.get("source") or q.get("reason"), (pid, q["name"]))     # 出典または理由
        self.assertEqual({p["status"] for p in PROFILES.values()}, {"implemented", "skeleton"})
        self.assertEqual([k for k, p in PROFILES.items() if p["status"] == "implemented"], ["autumn_leaves", "birds"])

    def test_schema_negatives(self):
        def errs(fn, pid="birds"):
            d = copy.deepcopy(PROFILES[pid])
            fn(d)
            return ip.validate_profile(d)
        self.assertTrue(errs(lambda d: d["method"].pop("params")))                       # 実装済みに params がない
        self.assertTrue(errs(lambda d: d["band_policy"].update(max_band="go")))           # validated=false で go
        self.assertTrue(errs(lambda d: d["method"]["params"][0].update(source=None, reason=None)))   # 出典も理由もない
        self.assertTrue(errs(lambda d: d["care"].update(do_not_disclose_exact_location=False)))      # 野鳥は位置を出さない
        self.assertTrue(errs(lambda d: d.pop("scale")))
        self.assertTrue(errs(lambda d: d.update(status="finished")))

    def test_autumn_thresholds_have_sources_and_are_provisional(self):
        for q in PROFILES["autumn_leaves"]["method"]["params"]:
            if q["name"].endswith("_min_temp_c"):
                self.assertTrue(q["provisional"])
                self.assertTrue(q["source"].startswith("https://"))
                self.assertIn("気象庁の基準ではない", PROFILES["autumn_leaves"]["known_limits"][1])
        names = {q["name"] for q in PROFILES["birds"]["method"]["params"]}
        self.assertTrue({"window_weeks", "history_years", "min_total_observations", "maybe_min_relative_frequency"} <= names)

class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return run_child([sys.executable, "-X", "utf8", str(ROOT / "ikimonobiyori" / "main.py"), *args], capture_output=True,
                              text=True, encoding="utf-8")

    def test_cli_offline_and_refuses_live(self):
        import tempfile
        d = tempfile.mkdtemp()
        write(Path(d) / "r.json", req(["autumn_leaves"]))
        r = self.run_cli("--request", str(Path(d) / "r.json"), "--inputs", str(INPUTS_PATH), "--now", "2026-10-14T22:00:00+09:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["schema"], "biyori-proposal/1")
        self.assertEqual(self.run_cli("--request", str(Path(d) / "r.json"), "--now", "2026-10-14T22:00:00+09:00", "--live").returncode, 4)
        self.assertEqual(self.run_cli("--request", str(Path(d) / "r.json"), "--inputs", str(INPUTS_PATH), "--now", "2026-10-14T22:00:00").returncode, 2)
        r = self.run_cli("--request", str(Path(d) / "r.json"), "--plan-queries", "--now", "2026-10-14T22:00:00+09:00")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(all(q["url"].startswith("https://api.open-meteo.com/") for q in json.loads(r.stdout)))


if __name__ == "__main__":
    unittest.main()
