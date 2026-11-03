"""段階38(指示書 docs/stage38-instructions.md): 公園ごとに「見られる鳥」を写真つきで見せる。通信しない。合成のデータだけ。
1. 自前の上限(netbudget): 上限で止まる・間隔を守る・記録が残る・許可外のホストを拒否する。計測フックがあるときはそちらを使う。
2. 範囲: 探鳥地ごとの範囲で集計される。既定の半径が方針ファイルの値。
3. 季節らしさ: 一年中多い鳥が、季節らしい鳥より後ろに来る。最近の記録の鳥が先に来る。
4. 公園ページ: 公園ごとの節に、その公園の鳥だけが写真つきで出る。写真なし・撮影者名・ライセンス・写真のページ・「種の代表写真」の1文・開園と休み。
5. 返事の全文の検査: 作業・開発の説明が落ちる。"""
import json
import os
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import ask
from ikimonobiyori import ask_verify as V
from ikimonobiyori import guide_photos, netbudget
from ikimonobiyori import observations as O
from ikimonobiyori import profiles as PR
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import birds_live, inaturalist
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.methods import observation_frequency as OF
from ikimonobiyori.paths import data_path

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 1, 10, 0, tzinfo=JST)
D = [date(2026, 11, 3)]
P = O.load_policy()
PB = P["park_birds"]
PROF = PR.load_profiles()["birds"]
CFG = load_config()
RULES = V.load_rules()
AP = ask.load_policy()

SPOTS = {"spots": [
    {"id": "t-p-1", "subject": "birds", "name": "試験の森公園", "prefecture": "神奈川県", "city": "試験市", "bird_area": "kanagawa_kanazawa",
     "bird_range": {"lat": 35.34, "lon": 139.59, "radius_km": None}, "pages": [{"url": "https://mori.example.org/", "publisher": "試験の森公園", "source_class": "official"}],
     "closed": {"text": "毎週火曜日", "facility": "観察センター", "open_note": "園内には入れます", "url": "https://mori.example.org/guide"},
     "hours": {"text": "9:00～16:30", "url": "https://mori.example.org/guide"}},
    {"id": "t-p-2", "subject": "birds", "name": "試験の池公園", "prefecture": "神奈川県", "city": "試験町", "bird_range": {"lat": 35.5, "lon": 139.4, "radius_km": 1.5},
     "pages": []},
    {"id": "t-p-3", "subject": "birds", "name": "試験の川原", "prefecture": "神奈川県", "city": "試験村", "bird_range": {"lat": 35.6, "lon": 139.5}, "pages": []},
]}
CATALOGS = {"birds": {"entries": []}}


def sc(rows):
    return {"total_results": len(rows), "page": 1, "per_page": 200,
            "results": [{"count": n, "taxon": {"id": tid, "name": sci, "preferred_common_name": ja}} for tid, sci, ja, n in rows]}


# この時期(窓): トビ(一年中多い)が最も多いが、ジョウビタキ・ツグミは一年の平均よりこの時期に多い
WINDOW = sc([(1, "Milvus migrans", "トビ", 30), (2, "Phoenicurus auroreus", "ジョウビタキ", 12), (3, "Turdus eunomus", "ツグミ", 6),
             (4, "Hypsipetes amaurotis", "ヒヨドリ", 20), (5, "Larus crassirostris", "ウミネコ", 1)])
# 一年: トビ・ヒヨドリが多く、ジョウビタキ・ツグミは少ない
YEAR = sc([(1, "Milvus migrans", "トビ", 600), (2, "Phoenicurus auroreus", "ジョウビタキ", 60), (3, "Turdus eunomus", "ツグミ", 40),
           (4, "Hypsipetes amaurotis", "ヒヨドリ", 500), (5, "Larus crassirostris", "ウミネコ", 50)])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.cache = Cache(data_path(CFG["cache"]["dir"], self.env))

    def area(self, sid):
        s = next(x for x in SPOTS["spots"] if x["id"] == sid)
        return O._rounded(O.park_area(s, P), PROF)

    def put(self, sid, d=D[0], window=WINDOW, year=YEAR, fetched_at="2026-10-31T22:00:00+09:00"):
        a = self.area(sid)
        for q in O._inat_queries(a, d, PROF, CFG):
            self.cache.put(url=q["url"], params=q["params"], body=json.dumps(window, ensure_ascii=False), source="iNaturalist API", fetched_at=fetched_at)
        if year is not None:
            q = O._baseline_q(a, d, PROF, CFG)
            self.cache.put(url=q["url"], params=q["params"], body=json.dumps(year, ensure_ascii=False), source="iNaturalist API", fetched_at=fetched_at)

    def facts(self):
        return O.facts("birds", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)


# ---- 1. 自前の上限 ----

class FakeClock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class Budget(Base):
    def budget(self, n=2, hosts=("api.inaturalist.org",), gap=1, env=None):
        self.fc = FakeClock()
        return netbudget.Budget("inat_counts", hosts, n, gap, env=env or self.env, clock=self.fc.clock, sleep=self.fc.sleep)

    def test_stops_at_the_limit_before_sending(self):
        b = self.budget(n=2)
        sent = []
        get = b(lambda u: (sent.append(u), (200, "{}", {}))[1])
        get("https://api.inaturalist.org/v1/a")
        get("https://api.inaturalist.org/v1/b")
        with self.assertRaises(netbudget.BudgetError):
            get("https://api.inaturalist.org/v1/c")
        self.assertEqual(len(sent), 2)                          # 3 回目は送らない

    def test_keeps_the_interval_to_the_same_host(self):
        b = self.budget(n=3, gap=1)
        get = b(lambda u: (200, "{}", {}))
        get("https://api.inaturalist.org/v1/a")
        get("https://api.inaturalist.org/v1/b")
        self.assertEqual(len(self.fc.slept), 1)
        self.assertGreaterEqual(self.fc.slept[0], 1)

    def test_writes_a_log_in_the_data_dir(self):
        b = self.budget(n=3)
        get = b(lambda u: (200, "{}", {}))
        get("https://api.inaturalist.org/v1/observations/species_counts?lat=35.34&lng=139.59")
        rows = netbudget.read_log(self.env)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["kind"], r["mode"], r["host"], r["n"], r["max"], r["status"]), ("inat_counts", "self", "api.inaturalist.org", 1, 3, 200))
        self.assertTrue(str(netbudget.log_path(self.env)).startswith(self.tmp.name))
        self.assertNotIn("35.34", json.dumps(rows))                # 座標・クエリは記録に残さない
        self.assertTrue(re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", r["at"]))

    def test_rejects_hosts_outside_the_declared_list(self):
        b = self.budget(n=3)
        get = b(lambda u: self.fail("送ってはいけない"))
        with self.assertRaises(netbudget.BudgetError):
            get("https://example.com/x")
        self.assertEqual(b.used, 0)

    def test_uses_the_hub_hook_when_present(self):
        env = dict(self.env, BIYORI_REQ_LOG=str(Path(self.tmp.name) / "hub.jsonl"))
        self.assertEqual(netbudget.mode(env), "hook")
        b = self.budget(n=2, env=env)
        b(lambda u: (200, "{}", {}))("https://api.inaturalist.org/v1/a")
        self.assertEqual(netbudget.read_log(self.env), [])          # 記録はハブの計測フックのもの(自前の記録は書かない)
        self.assertEqual(b.summary()["mode"], "hook")

    def test_refusal_under_test_and_under_the_hook(self):
        self.assertIn("テスト中", netbudget.refusal())              # テスト中は常に拒否
        with mock.patch.object(netbudget.livegate, "under_test", return_value=False):
            self.assertIsNone(netbudget.refusal({"IKIMONOBIYORI_DATA_DIR": "x"}) if not os.environ.get("BIYORI_REQ_LOG") else None)
            with mock.patch.dict(os.environ, {"BIYORI_REQ_LOG": "x"}):
                with mock.patch.object(netbudget.livegate, "refusal", return_value="BIYORI_ALLOW_LIVE がない"):
                    self.assertEqual(netbudget.refusal(), "BIYORI_ALLOW_LIVE がない")   # 計測フックの下では従来どおり BIYORI_ALLOW_LIVE=1 が要る

    def test_the_caps_are_the_policy_values(self):
        self.assertEqual(P["inat_refresh"]["max_requests_per_question"]["value"], 10)
        from ikimonobiyori import guide
        self.assertEqual(guide.load_policy()["photos"]["max_requests_per_run"]["value"], 80)
        self.assertGreaterEqual(P["fetch_limits"]["same_host_interval_s"], 1)

    def test_ask_refresh_runs_under_the_budget_and_logs(self):
        f = ask.Flow(Path(self.tmp.name) / "ask" / "q1", now=NOW, env=self.env, clock=lambda: NOW, obs_kw={"spots_doc": SPOTS, "catalogs": CATALOGS})
        f.prepare(["birds"], "神奈川", D)
        calls = []

        def http(url):
            calls.append(url)
            return 200, json.dumps(WINDOW, ensure_ascii=False), {}
        out = f.inat_refresh(http_get=http, sleep=lambda s: None, clock=lambda: NOW)
        self.assertTrue(out["ran"])
        self.assertLessEqual(out["net"]["requests"], P["inat_refresh"]["max_requests_per_question"]["value"])
        self.assertEqual(out["net"]["requests"], len(calls))
        self.assertEqual(len(netbudget.read_log(self.env)), len(calls))
        doc = f.facts(["birds"], "神奈川", D)
        self.assertEqual(doc["inat_refresh"]["reason"], "ran")            # 取り直したあとの facts は「取り直していない」と記録しない
        self.assertNotIn("no_measure_hook", [c.get("skipped") for c in f.calls])
        self.assertTrue(any("radius=2" in u for u in calls))          # 公園ごとの範囲(既定の半径)
        self.assertTrue(all("radius=10" not in u for u in calls))


# ---- 2. 範囲 ----

class Range(Base):
    def test_default_radius_is_the_policy_value(self):
        a = O.park_area(SPOTS["spots"][0], P)
        self.assertEqual(a["radius_km"], PB["range"]["default_radius_km"]["value"])
        self.assertEqual(a["radius_km"], 2)
        self.assertEqual(O.park_area(SPOTS["spots"][1], P)["radius_km"], 1.5)        # 名所ごとの半径があればそれ
        self.assertEqual(a["id"], "park:t-p-1")

    def test_queries_use_the_park_range_and_rounded_coordinates(self):
        a = self.area("t-p-1")
        qs = O._inat_queries(a, D[0], PROF, CFG)
        for q in qs:
            self.assertEqual(q["params"]["radius"], 2)
            self.assertEqual((q["params"]["lat"], q["params"]["lng"]), (35.34, 139.59))
        self.assertEqual(qs[0]["params"]["month"], "10,11")                  # 対象の日の前後(方針の half_days)にかかる月
        b = O._baseline_q(a, D[0], PROF, CFG)
        self.assertNotIn("month", b["params"])                                # 分母は一年の記録
        self.assertNotIn("year", b["params"])

    def test_facts_aggregate_by_the_park_range(self):
        self.put("t-p-1")
        f = next(c for c in self.facts()["candidates"] if c["id"] == "t-p-1")
        self.assertEqual(f["bird_area"], "park:t-p-1")
        self.assertEqual(f["inat"]["radius_km"], 2)
        self.assertEqual(f["inat"]["scope"], "park")

    def test_status_counts_the_baseline_request(self):
        self.put("t-p-1", year=None)
        st = O.inat_status("park:t-p-1", D[0], NOW, env=self.env)
        self.assertTrue(st["baseline_needed"])
        self.assertEqual(st["state"], "stale")
        self.assertEqual(st["requests"], 1)

    def test_real_parks_have_ranges_with_sources(self):
        birds = [s for s in O.load_spots()["spots"] if s["subject"] == "birds" and s.get("bird_range")]
        self.assertGreaterEqual(len(birds), 3)
        for s in birds:
            br = s["bird_range"]
            self.assertTrue(br.get("source"))
            for v in (br["lat"], br["lon"]):
                self.assertLessEqual(len(str(v).split(".")[-1]), 2)     # 小数2桁まで(area_1km)


# ---- 3. 季節らしさ ----

class Seasonality(Base):
    def test_seasonal_rank_puts_year_round_birds_behind(self):
        w = inaturalist.parse_species_counts(WINDOW)[0]
        y = inaturalist.parse_species_counts(YEAR)[0]
        ranked = OF.seasonal_rank([w], [y], lift_min=PB["seasonality"]["lift_min"]["value"], min_count=PB["seasonality"]["min_window_count"]["value"])
        names = [r["common_name"] for r in ranked]
        self.assertLess(names.index("ジョウビタキ"), names.index("トビ"))
        self.assertLess(names.index("ツグミ"), names.index("ヒヨドリ"))
        self.assertEqual(len(ranked), 5)                                  # 消さない
        uminek = next(r for r in ranked if r["common_name"] == "ウミネコ")
        self.assertFalse(uminek["seasonal"])                               # 1 件だけの記録では季節らしさを決めない

    def test_park_birds_order_recent_then_seasonal_then_year_round(self):
        self.put("t-p-1")
        O.record([{"subject": "birds", "spot": "t-p-1", "state": "10/30 キビタキとトビを観察しました", "state_date": "2026-10-30",
                   "url": "https://mori.example.org/blog", "publisher": "試験の森公園", "source_class": "official"}], env=self.env, now=NOW)
        f = next(c for c in self.facts()["candidates"] if c["id"] == "t-p-1")
        names = [b["name"] for b in f["park_birds"]]
        kinds = [b["kind"] for b in f["park_birds"]]
        self.assertEqual(kinds[0], "recent")
        self.assertIn("キビタキ", names[:2])
        self.assertEqual(f["park_birds"][0]["why"], "最近(10/30)、公園の記録に出ています")
        self.assertEqual((f["park_birds"][0]["publisher"], f["park_birds"][0]["date"]), ("試験の森公園", "2026-10-30"))
        self.assertLess(names.index("ジョウビタキ"), names.index("ヒヨドリ"))
        jo = next(b for b in f["park_birds"] if b["name"] == "ジョウビタキ")
        self.assertEqual(jo["kind_label"], "この時期の記録")
        self.assertIn(jo["why"], (PB["why"]["seasonal"], PB["why"]["seasonal_strong"]))
        hi = next(b for b in f["park_birds"] if b["name"] == "ヒヨドリ")
        self.assertEqual(hi["why"], PB["why"]["year_round"])
        self.assertEqual(jo["taxon_id"], 2)

    def test_season_line_uses_seasonal_birds(self):
        self.put("t-p-1")
        f = next(c for c in self.facts()["candidates"] if c["id"] == "t-p-1")
        self.assertIn("ジョウビタキ", f["season_line"])
        self.assertNotIn("トビ", f["season_line"])
        self.assertIn("一年の平均より多く記録される鳥です", f["season_line"])

    def test_sea_birds_on_top_of_an_inland_park_are_flagged(self):
        win = sc([(5, "Larus crassirostris", "ウミネコ", 40), (2, "Phoenicurus auroreus", "ジョウビタキ", 5)])
        yr = sc([(5, "Larus crassirostris", "ウミネコ", 100), (2, "Phoenicurus auroreus", "ジョウビタキ", 40)])
        self.put("t-p-1", window=win, year=yr)
        doc = self.facts()
        self.assertTrue(any(w["spot"] == "試験の森公園" and "ウミネコ" in w["sea_birds"] for w in doc["range_warnings"]))


class RegionalSeasonality(Base):
    """採点の後(段階38): 季節らしさは地域全体の記録で決める。公園の少ない記録の割合のぶれで、一年中いる鳥を上にしない。"""

    def put_region(self, window, year, d=D[0], summer=None):
        a = O._rounded(O._area_by_id(O.region_area_id("神奈川県")), PROF)
        win, con = O._inat_queries(a, d, PROF, CFG)                       # この時期の月 + 反対の季節の月
        self.assertEqual(con["params"]["month"], "6,7,8")
        summer = summer or sc([(8, "Streptopelia orientalis", "キジバト", 300), (1, "Milvus migrans", "トビ", 300)])   # 夏はジョウビタキがいない
        for q, body in ((win, window), (con, summer)):
            self.cache.put(url=q["url"], params=q["params"], body=json.dumps(body, ensure_ascii=False), source="iNaturalist API", fetched_at="2026-10-31T22:00:00+09:00")
        q = O._baseline_q(a, d, PROF, CFG)
        self.cache.put(url=q["url"], params=q["params"], body=json.dumps(year, ensure_ascii=False), source="iNaturalist API", fetched_at="2026-10-31T22:00:00+09:00")

    def test_year_round_bird_with_a_noisy_park_ratio_is_behind(self):
        # 公園: キジバトがこの時期に2件(公園の一年では少ない → 公園だけの割合なら「この時期らしい」になる)
        park_w = sc([(8, "Streptopelia orientalis", "キジバト", 2), (2, "Phoenicurus auroreus", "ジョウビタキ", 1), (1, "Milvus migrans", "トビ", 20)])
        park_y = sc([(8, "Streptopelia orientalis", "キジバト", 3), (2, "Phoenicurus auroreus", "ジョウビタキ", 4), (1, "Milvus migrans", "トビ", 200)])
        self.put("t-p-1", window=park_w, year=park_y)
        # 地域全体: キジバトは一年中同じ割合、ジョウビタキはこの時期に多い
        self.put_region(sc([(8, "Streptopelia orientalis", "キジバト", 100), (2, "Phoenicurus auroreus", "ジョウビタキ", 60), (1, "Milvus migrans", "トビ", 100)]),
                        sc([(8, "Streptopelia orientalis", "キジバト", 1200), (2, "Phoenicurus auroreus", "ジョウビタキ", 150), (1, "Milvus migrans", "トビ", 1200)]))
        f = next(c for c in self.facts()["candidates"] if c["id"] == "t-p-1")
        names = [b["name"] for b in f["park_birds"]]
        self.assertEqual(names[0], "ジョウビタキ")
        kj = next(b for b in f["park_birds"] if b["name"] == "キジバト")
        self.assertEqual(kj["why"], PB["why"]["region_year_round"])
        self.assertIn("神奈川県", f["park_birds"][0]["why"])
        self.assertEqual(f["inat"]["region"]["name"], "神奈川県")

    def test_resident_with_a_mild_annual_ratio_is_not_seasonal(self):
        """一年の平均との比が lift_min を少し超えても、反対の季節(夏)と同じくらいなら『この時期らしい』にしない。"""
        park_w = sc([(9, "Egretta garzetta", "コサギ", 10), (6, "Anas crecca", "コガモ", 10)])
        park_y = sc([(9, "Egretta garzetta", "コサギ", 30), (6, "Anas crecca", "コガモ", 30)])
        self.put("t-p-1", window=park_w, year=park_y)
        self.put_region(sc([(9, "Egretta garzetta", "コサギ", 130), (6, "Anas crecca", "コガモ", 130)]),
                        sc([(9, "Egretta garzetta", "コサギ", 1000), (6, "Anas crecca", "コガモ", 1000), (1, "Milvus migrans", "トビ", 1000)]),   # 一年の比 1.5
                        summer=sc([(9, "Egretta garzetta", "コサギ", 130), (6, "Anas crecca", "コガモ", 2)]))
        f = next(c for c in self.facts()["candidates"] if c["id"] == "t-p-1")
        by = {b["name"]: b for b in f["park_birds"]}
        self.assertTrue(by["コガモ"]["seasonal"])
        self.assertFalse(by["コサギ"]["seasonal"])
        self.assertEqual([b["name"] for b in f["park_birds"]][0], "コガモ")

    def test_plan_fetches_the_regional_area_first(self):
        ir = O.plan("birds", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)["inat_refresh"]
        self.assertEqual(ir["areas"][0]["area"], "region:神奈川県")
        self.assertLessEqual(ir["planned_requests"], P["inat_refresh"]["max_requests_per_question"]["value"])
        ra = O._area_by_id("region:神奈川県")
        self.assertEqual(len(str(ra["lat"]).split(".")[-1]), 1)                 # 地域の区域は小数1桁


# ---- 4. 公園ページ ----

class Page(Base):
    def setUp(self):
        super().setUp()
        self.put("t-p-1")
        self.put("t-p-2", window=sc([(6, "Anas crecca", "コガモ", 30), (7, "Alcedo atthis", "カワセミ", 8)]),
                 year=sc([(6, "Anas crecca", "コガモ", 100), (7, "Alcedo atthis", "カワセミ", 200)]))
        meta = {"name": "ジョウビタキ", "scientific": "Phoenicurus auroreus", "taxon_id": 2, "photo_id": 11, "license": "CC BY", "license_code": "cc-by",
                "attribution": "(c) 試験 撮影者, some rights reserved (CC BY)", "photo_page": "https://www.inaturalist.org/photos/11",
                "fetched_on": "2026-11-01", "image_type": "jpeg"}
        guide_photos.save_photo({"meta": meta, "data": b"\xff\xd8\xff\xe0test", "ext": "jpeg"}, self.env)
        meta2 = dict(meta, name="コガモ", scientific="Anas crecca", taxon_id=6, photo_id=12, photo_page="https://www.inaturalist.org/photos/12")
        guide_photos.save_photo({"meta": meta2, "data": b"\xff\xd8\xff\xe0test2", "ext": "jpeg"}, self.env)
        self.f = ask.Flow(Path(self.tmp.name) / "ask" / "q2", now=NOW, env=self.env, clock=lambda: NOW, obs_kw={"spots_doc": SPOTS, "catalogs": CATALOGS})
        self.f.prepare(["birds"], "神奈川", D)
        self.f.facts(["birds"], "神奈川", D)
        self.doc = self.f.page()
        self.html = Path(self.doc["path"]).read_text(encoding="utf-8")

    def sections(self):
        return {re.search(r"<h2>(.*?)</h2>", s).group(1): s for s in re.findall(r"<section>.*?</section>", self.html, re.S)}

    def test_each_park_section_has_only_its_birds_with_photos(self):
        secs = self.sections()
        mori = next(v for k, v in secs.items() if "試験の森公園" in k)
        ike = next(v for k, v in secs.items() if "試験の池公園" in k)
        self.assertIn("ジョウビタキ", mori)
        self.assertNotIn("コガモ", mori)
        self.assertIn("コガモ", ike)
        self.assertNotIn("ジョウビタキ", ike)
        self.assertIn('src="data:image/jpeg;base64,', mori)
        self.assertIn("写真なし", mori)                                    # トビなど写真のない鳥
        self.assertTrue(self.doc["ok"], self.doc["errors"])

    def test_credit_license_link_and_the_one_note(self):
        self.assertIn("試験 撮影者", self.html)
        self.assertIn("CC BY", self.html)
        self.assertIn('href="https://www.inaturalist.org/photos/11"', self.html)
        self.assertEqual(self.html.count(AP["park_page"]["text"]["photo_note"]), 1)
        self.assertNotIn("<script", self.html)

    def test_closures_hours_and_park_link(self):
        mori = next(v for k, v in self.sections().items() if "試験の森公園" in k)
        self.assertIn("11/3(火・文化の日)は観察センターが休みです", mori)
        self.assertIn("開園: 9:00～16:30", mori)
        self.assertIn('href="https://mori.example.org/"', mori)

    def test_page_is_in_the_data_dir_and_mobile_ready(self):
        self.assertTrue(self.doc["path"].startswith(str(Path(self.tmp.name).resolve())))
        self.assertIn(str(Path("guide") / "pages"), self.doc["path"])
        self.assertIn('name="viewport"', self.html)
        self.assertIn("@media (max-width: 30rem)", self.html)
        self.assertEqual(self.doc["line"], AP["park_page"]["reply_line"].format(path=self.doc["path"]))

    def test_page_text_goes_through_the_checker(self):
        bad = V.page_check(["今回の作業で 11/9 にテストしました。"], self.f._load("facts.json", {}), RULES)
        self.assertFalse(bad["ok"])

    def test_photos_step_never_launches_under_test(self):
        out = self.f.photos()
        self.assertEqual(out, {"ran": False, "reason": "under_test"})

    def test_photos_step_with_injected_http_respects_the_budget(self):
        guide_photos.clear_cache(self.env)
        urls = []

        def http(url):
            urls.append(url)
            m = re.search(r"/taxa/(\d+)", url)
            tid = int(m.group(1))
            sci = {1: "Milvus migrans", 2: "Phoenicurus auroreus", 3: "Turdus eunomus", 4: "Hypsipetes amaurotis", 5: "Larus crassirostris",
                   6: "Anas crecca", 7: "Alcedo atthis"}[tid]
            return 200, json.dumps({"results": [{"id": tid, "name": sci, "default_photo": {"id": 100 + tid, "license_code": "cc-by",
                                                                                              "attribution": "(c) x", "medium_url": f"https://static.inaturalist.org/photos/{tid}/medium.jpg"}}]}), {}

        def hb(url, mx):
            urls.append(url)
            return 200, b"\xff\xd8\xff\xe0img", {}
        out = self.f.photos(http_get=http, http_bytes=hb, sleep=lambda s: None)
        self.assertTrue(out["ran"])
        self.assertLessEqual(out["net"]["requests"], 80)
        self.assertEqual(out["net"]["requests"], len(urls))
        self.assertTrue(all(x["photo"] for x in out["species"] if x["taxon_id"]))
        self.assertTrue(all(h in ("api.inaturalist.org", "static.inaturalist.org") for h in out["net"]["hosts"]))


# ---- 5. 返事の全文の検査 ----

class Reply(Base):
    def setUp(self):
        super().setUp()
        self.put("t-p-1")
        self.f = ask.Flow(Path(self.tmp.name) / "ask" / "q3", now=NOW, env=self.env, clock=lambda: NOW, obs_kw={"spots_doc": SPOTS, "catalogs": CATALOGS})
        self.f.prepare(["birds"], "神奈川", D)
        self.facts = self.f.facts(["birds"], "神奈川", D)
        self.doc = self.f.page()

    def body(self):
        return ("① 試験の森公園(試験市)\n・この時期に見られる鳥: ジョウビタキなど。\n\n② 試験の池公園\n・この時期の記録はまだ少なめです。\n\n"
                "③ 試験の川原\n・この時期の様子は分かっていません。\n")

    def test_dev_explanations_outside_the_answer_fail(self):
        for extra in ("今回の作業で実行したこと: 集計を取り直しました。", "リポジトリの追跡ファイルは変えていません。",
                      "コードは変更していないため、単体テストは実行していません。", "ページの保存先はデータの置き場所です。"):
            r, _ = self.f.verify(self.body() + "\n" + extra + "\n", reply=True)
            self.assertFalse(r["ok"], extra)

    def test_the_page_line_is_allowed_once(self):
        r, _ = self.f.verify(self.body() + "\n" + self.doc["line"] + "\n", reply=True)
        self.assertTrue(r["page_line_found"])
        self.assertNotIn("internal_term", {e["code"] for s in r["sentences"] for e in s["errors"]})
        self.assertNotIn("reply_dev_term", {e["code"] for s in r["sentences"] for e in s["errors"]})

    def test_official_is_said_once(self):
        r = V.check("公式ではない情報です。\n公式ではない情報です。\n", self.facts, RULES)
        self.assertIn("repeated_phrase", {e["code"] for e in r["answer_errors"]})


class Docs(unittest.TestCase):
    def test_rule6_and_skill_describe_the_self_limit(self):
        for p in (ROOT / "CLAUDE.md", ROOT / "AGENTS.md", ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md"):
            t = p.read_text(encoding="utf-8")
            self.assertIn("ask photos", t, p.name)
            self.assertIn("ask page", t, p.name)
            self.assertIn("--reply", t, p.name)
        c = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("netlog/requests.jsonl", c)


if __name__ == "__main__":
    unittest.main()
