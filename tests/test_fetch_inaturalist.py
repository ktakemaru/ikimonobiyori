"""野鳥(iNaturalist)の取得層(biyori-hub の tests/test_ikimono_birds_live.py から移した。段階12。独立検査器・窓口との接続・実際の応答の記録を使う部分は biyori-hub 側に残っている): 形の確認・間隔・キャッシュ・中止条件・集計値だけの保存・位置の丸め。すべて通信なし(偽の http_get)。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H
from helpers import ROOT

from ikimonobiyori import engine, main as imain, profiles as ip
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import ParseError, birds_live, inaturalist
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.fetch.live import LiveError

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 23, 0, tzinfo=JST)
CFG = load_config()
PROFS = ip.load_profiles()
SITES, SITES_DOC = ip.load_sites()
BIRDS = PROFS["birds"]
AREA = next(a for a in SITES_DOC["bird_areas"] if a["id"] == "karuizawa")
DATES = [datetime(2026, 10, 17).date()]
SPECIES = [("Parus minor", "シジュウカラ", 40), ("Corvus macrorhynchos", "ハシブトガラス", 20), ("Zosterops japonicus", "メジロ", 14),
           ("Passer montanus", "スズメ", 6), ("Phasianus versicolor", "キジ", 4)]


def resp(n=len(SPECIES), with_extras=True):
    results = []
    for i, (sci, ja, c) in enumerate(SPECIES[:n]):
        t = {"id": 1000 + i, "name": sci, "preferred_common_name": ja, "rank": "species", "iconic_taxon_name": "Aves"}
        if with_extras:                                  # 写真・観察者に近い項目(保存してはいけない)
            t["default_photo"] = {"url": "https://example.invalid/p.jpg", "license_code": "cc-by", "attribution": "(c) someone"}
            t["wikipedia_url"] = "https://example.invalid/w"
        results.append({"count": c, "taxon": t})
    return {"total_results": len(SPECIES), "page": 1, "per_page": 200, "results": results}


class Fake:
    def __init__(self, status=200, body=None, headers=None):
        self.calls, self.status, self.body, self.headers = [], status, body, headers or {"X-RateLimit-Remaining": "59"}

    def __call__(self, url):
        self.calls.append(url)
        return self.status, self.body if self.body is not None else json.dumps(resp()), self.headers


def fetch(cache, http, *, area=AREA, live=True, cache_only=False, max_requests=10, shape=False, sleeps=None, unparsed=None, cfg=CFG, dates=DATES, per_year=True):
    return birds_live.fetch_bird_counts(area, dates, BIRDS, NOW, cache=cache, cfg=cfg, http_get=http, live=live, cache_only=cache_only,
                                        max_requests=max_requests if live else None, unparsed_dir=unparsed or tempfile.mkdtemp(),
                                        sleep=(sleeps.append if sleeps is not None else (lambda s: None)), shape_check=shape, per_year=per_year)


class Config(unittest.TestCase):
    def test_hosts_by_subject_only_birds_get_inaturalist(self):
        h = CFG["live"]["allowed_hosts_by_subject"]
        self.assertEqual(h["birds"], ["api.inaturalist.org"])
        self.assertEqual(h["autumn_leaves"], ["api.open-meteo.com"])
        self.assertEqual(CFG["live"]["allowed_hosts"], ["api.open-meteo.com"])           # 既存(紅葉・他ビヨリ)の許可リストは変えない
        self.assertGreaterEqual(CFG["live"]["min_interval_s"], 2)
        self.assertNotIn("@", CFG["live"]["user_agent"])                                 # メールアドレスを入れない
        self.assertIn("biyori-hub/ikimonobiyori", CFG["live"]["user_agent"])
        self.assertEqual(AREA["status"], "approved")
        self.assertEqual((AREA["lat"], AREA["lon"], AREA["radius_km"]), (36.3, 138.6, 10))

class ShapeCheck(unittest.TestCase):
    def test_one_request_small_per_page_and_only_aggregates_saved(self):
        c, http = Cache(tempfile.mkdtemp()), Fake()
        inputs, rep = fetch(c, http, shape=True, max_requests=3)
        self.assertEqual((rep["requests"], len(http.calls)), (1, 1))
        self.assertIn(f"per_page={CFG['live']['inaturalist']['shape_check_per_page']}", http.calls[0])
        self.assertTrue(http.calls[0].startswith("https://api.inaturalist.org/v1/observations/species_counts?"))
        self.assertIn("iconic_taxa=Aves", http.calls[0])
        self.assertIn("lat=36.3&lng=138.6&radius=10", http.calls[0])
        sh = rep["shape"]
        self.assertEqual(sh["status"], 200)
        self.assertIn("default_photo", sh["fields_seen"]["taxon"])                         # 元の応答に写真の項目があったことは記録する
        self.assertEqual(rep["rate_headers"], {"X-RateLimit-Remaining": "59"})
        blob = json.dumps(sh["minimized"]) + "".join(p.read_text(encoding="utf-8") for p in Path(c.dir).glob("*.json"))
        for banned in ("default_photo", "example.invalid", "attribution", "wikipedia_url"):
            self.assertNotIn(banned, blob)                                                 # 写真・帰属の項目を保存していない
        self.assertEqual(sh["minimized"]["results"][0], {"count": 40, "taxon": {"id": 1000, "name": "Parus minor", "preferred_common_name": "シジュウカラ",
                                                                                 "rank": "species", "iconic_taxon_name": "Aves"}})

    def test_shape_mismatch_stops_and_saves_raw(self):
        d = Path(tempfile.mkdtemp())
        with self.assertRaises(ParseError) as cm:
            fetch(Cache(tempfile.mkdtemp()), Fake(body=json.dumps({"results": [{"n": 3, "species": "x"}]})), shape=True, unparsed=d)
        saved = list(d.glob("*.json"))
        self.assertEqual(len(saved), 1)
        self.assertIn(str(saved[0]), str(cm.exception))
        self.assertEqual(json.loads(saved[0].read_text(encoding="utf-8"))["status"], 200)


class Fetch(unittest.TestCase):
    def test_five_years_one_by_one_with_interval_and_cache(self):
        c, http, sleeps = Cache(tempfile.mkdtemp()), Fake(), []
        inputs, rep = fetch(c, http, sleeps=sleeps)
        self.assertEqual((rep["requests"], len(http.calls)), (5, 5))                      # 過去5年
        self.assertEqual(len(sleeps), 4)                                                   # 1リクエストずつ。2回目以降の前に待つ
        self.assertTrue(all(s >= CFG["live"]["min_interval_s"] - 0.5 for s in sleeps), sleeps)
        self.assertEqual(sorted(inputs["birds"][0]["queries"][0]["years"]), ["2021", "2022", "2023", "2024", "2025"])
        urls = inputs["birds"][0]["queries"][0]["urls"]
        self.assertTrue(all("per_page=200" in u for u in urls.values()))
        http2 = Fake()
        _, rep2 = fetch(c, http2)
        self.assertEqual((rep2["requests"], rep2["cache_hits"], http2.calls), (0, 5, []))      # キャッシュヒットで通信 0
        _, rep3 = fetch(c, Fake(status=500), live=False, cache_only=True)
        self.assertEqual((rep3["requests"], rep3["cache_hits"]), (0, 5))

    def test_max_requests_and_non_200_abort_without_retry(self):
        http = Fake()
        _, rep = fetch(Cache(tempfile.mkdtemp()), http, max_requests=3)
        self.assertEqual((rep["requests"], len(http.calls), len(rep["misses"])), (3, 3, 2))
        for status in (429, 403, 404, 500):
            http = Fake(status=status, body="{}")
            c = Cache(tempfile.mkdtemp())
            with self.assertRaises(LiveError):
                fetch(c, http)
            self.assertEqual(len(http.calls), 1)                                           # 再試行しない・次に進まない
            self.assertEqual(list(Path(c.dir).glob("*.json")) if Path(c.dir).exists() else [], [])

    def test_disallowed_host_is_never_requested(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["live"]["allowed_hosts_by_subject"]["birds"] = ["example.invalid"]
        http = Fake()
        with self.assertRaises(LiveError):
            fetch(Cache(tempfile.mkdtemp()), http, cfg=cfg)
        self.assertEqual(http.calls, [])

    def test_truncation_warning_when_per_page_too_small(self):
        body = resp()
        body["total_results"] = 999
        _, rep = fetch(Cache(tempfile.mkdtemp()), Fake(body=json.dumps(body)), max_requests=1)
        self.assertTrue(rep["truncated"])
        self.assertTrue(any("一部のみ" in w for w in rep["warnings"]))


class Privacy(unittest.TestCase):
    EXACT = {"id": "x", "name": "軽井沢周辺", "lat": 36.312345, "lon": 138.654321, "radius_km": 10, "location_precision": "area_10km"}

    def test_exact_input_coordinates_never_reach_query_cache_or_proposals(self):
        c, http = Cache(tempfile.mkdtemp()), Fake()
        inputs, rep = fetch(c, http, area=self.EXACT)
        everything = "".join(http.calls) + json.dumps(inputs, ensure_ascii=False) + json.dumps(rep, ensure_ascii=False, default=str)
        everything += "".join(p.read_text(encoding="utf-8") for p in Path(c.dir).glob("*.json"))
        doc = engine.run({"schema": "biyori-request/1", "request_id": "p", "intent": "weekend_outing", "origin": {"name": "x", "lat": 35.0, "lon": 139.0},
                          "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-17T23:59:00+09:00"}, "interests": ["birds"]},
                         profiles=PROFS, sites=SITES, inputs=inputs, now=NOW)
        everything += json.dumps(doc, ensure_ascii=False)
        for exact in ("36.312345", "138.654321", "36.3123", "138.6543"):
            self.assertNotIn(exact, everything)
        self.assertIn("lat=36.3&lng=138.7", http.calls[0])                      # 138.654321 → 小数1桁に丸めて 138.7
        p = doc["proposals"][0]
        self.assertEqual((p["place"]["lat"], p["place"]["lon"]), (36.3, 138.7))


class EndToEnd(unittest.TestCase):
    def request_file(self, interests=("birds",)):
        p = Path(tempfile.mkdtemp()) / "r.json"
        p.write_text(json.dumps({"schema": "biyori-request/1", "request_id": "e2e", "intent": "weekend_outing",
                                 "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-18T23:59:00+09:00"},
                                 "origin": {"name": "x", "lat": 35.0, "lon": 139.0}, "interests": list(interests)}), encoding="utf-8")
        return p

    def setUp(self):
        pass                                                         # 偽の http_get を注入するので実通信にならない(ゲートは注入時に通る)

    def test_one_place_one_day_chain(self):
        r, cdir = self.request_file(), tempfile.mkdtemp()
        out, inp = Path(tempfile.mkdtemp()) / "o.json", Path(tempfile.mkdtemp()) / "i.json"
        http = Fake()
        rc = imain.main(["--request", str(r), "--live", "--max-requests", "10", "--dates-limit", "1", "--now", NOW.isoformat(),
                         "--cache-dir", cdir, "--out", str(out), "--inputs-out", str(inp), "--per-year"], http_get=http)
        self.assertEqual(rc, 0)
        doc, inputs = json.loads(out.read_text(encoding="utf-8")), json.loads(inp.read_text(encoding="utf-8"))
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual((doc["diagnostics"]["api_calls"], doc["diagnostics"]["cache_hit"], len(http.calls)), (5, False, 5))
        self.assertEqual(doc["diagnostics"]["rate_limit_headers"], {"X-RateLimit-Remaining": "59"})
        self.assertEqual(len(doc["proposals"]), 5)                                          # 上位5種 × 1日
        self.assertTrue(all("SYNTHETIC" not in e["source"] for p in doc["proposals"] for e in p["evidence"]))
        self.assertEqual(doc["data_as_of"][0]["fetched_at"], NOW.isoformat(timespec="seconds"))
        # 2 回目: 通信 0
        http2, out2 = Fake(), Path(tempfile.mkdtemp()) / "o2.json"
        rc = imain.main(["--request", str(r), "--live", "--max-requests", "10", "--dates-limit", "1", "--now", (NOW + timedelta(minutes=5)).isoformat(),
                         "--cache-dir", cdir, "--out", str(out2), "--per-year"], http_get=http2)
        self.assertEqual((rc, http2.calls), (0, []))
        self.assertEqual(json.loads(out2.read_text(encoding="utf-8"))["diagnostics"]["api_calls"], 0)

    def test_live_refuses_both_subjects_and_shape_check_writes_file(self):
        r = self.request_file(("birds", "autumn_leaves"))
        self.assertEqual(imain.main(["--request", str(r), "--live", "--max-requests", "5", "--now", NOW.isoformat()], http_get=Fake()), 2)
        r = self.request_file()
        shape = Path(tempfile.mkdtemp()) / "s.json"
        rc = imain.main(["--request", str(r), "--live", "--max-requests", "3", "--shape-check", "--shape-out", str(shape), "--dates-limit", "1",
                         "--now", NOW.isoformat(), "--cache-dir", tempfile.mkdtemp()], http_get=Fake())
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(shape.read_text(encoding="utf-8"))["status"], 200)



class SyntheticInaturalistSparse(unittest.TestCase):
    """合成の iNaturalist の入力(記録の少ない場所)。実際の応答ではない(tests/fixtures/make_synthetic_inaturalist.py)。
    実際の応答の記録(biyori-hub の recorded_inaturalist_2026-10-14.json)は、利用条件を目視で確認するまで、このリポジトリに置かない。"""
    PATH = ROOT / "tests" / "fixtures" / "synthetic_inaturalist_sparse.json"

    def rec(self):
        return json.loads(self.PATH.read_text(encoding="utf-8"))

    def test_marked_synthetic_and_aggregates_only(self):
        d = self.rec()
        self.assertTrue(d["synthetic"])
        self.assertFalse(d["recorded"])
        self.assertIn("SYNTHETIC", d["note"])
        blob = json.dumps(d, ensure_ascii=False)
        for banned in ("default_photo\": {", "photo_url", "\"user\"", "login", "license_code"):
            self.assertNotIn(banned, blob)                                    # 写真・観察者の項目を持たない(集計値だけ)

    def test_shape_is_what_the_parser_expects(self):
        d = self.rec()
        sc = d["shape_check"]
        self.assertEqual(sc["fields_seen"]["top"], ["page", "per_page", "results", "total_results"])
        self.assertEqual(sc["fields_seen"]["result"], ["count", "taxon"])
        rows, total = inaturalist.parse_species_counts(sc["minimized"])
        self.assertEqual((len(rows), total), (3, 3))
        self.assertIn("per_page=10", sc["url"])
        for blk in d["inputs"]["birds"]:
            for q in blk["queries"]:
                self.assertEqual(sorted(q["years"]), ["2021", "2022", "2023", "2024", "2025"])
                for r in q["years"].values():
                    inaturalist.parse_species_counts(r)

    def test_sparse_data_gives_no_proposals_not_zero_filled(self):
        d = self.rec()["inputs"]
        req = {"schema": "biyori-request/1", "request_id": "r", "intent": "weekend_outing", "origin": {"name": "x", "lat": 35.0, "lon": 139.0},
               "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-17T23:59:00+09:00"}, "interests": ["birds"]}
        doc = engine.run(req, profiles=PROFS, sites=SITES, inputs=d, now=NOW)
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        # 件数不足は失敗ではなく結果(5b-3): status は ok のまま、警告にコード insufficient_data と原文
        self.assertEqual((doc["status"], doc.get("status_reason"), doc["proposals"]), ("ok", None, []))
        self.assertTrue(any(w.startswith("[insufficient_data] ") and "総数 9" in w and "min_total_observations=30" in w for w in doc["diagnostics"]["warnings"]))
        self.assertEqual(doc["details"], {"warning_codes": {"insufficient_data": 1}})
        # 閾値を下げれば(テスト内のプロファイルのコピーだけ)提案が出る(コードが閾値を持っていない確認)
        profs = json.loads(json.dumps(PROFS))
        for q in profs["birds"]["method"]["params"]:
            if q["name"] == "min_total_observations":
                q["value"] = 5
        doc2 = engine.run(req, profiles=profs, sites=SITES, inputs=d, now=NOW)
        self.assertEqual(len(doc2["proposals"]), 4)                           # 合成の入力は4種
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc2), [])
        for p in doc2["proposals"]:
            self.assertEqual((p["place"]["lat"], p["place"]["lon"]), (35.7, 139.1))
            self.assertLessEqual(p["suitability"]["band"], "maybe")


if __name__ == "__main__":
    unittest.main()
