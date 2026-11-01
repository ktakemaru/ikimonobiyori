"""段階36(指示書 biyori-hub/docs/stageH10-instructions.md 第1部): 通信なし。合成のデータだけ。
- 1: iNaturalist の取得時刻は、応答を受け取った時刻(--now ではない)。
- 2: 野鳥の区域の集計が古い(7日より前)・対象の日が前回の集計の期間の外なら、refresh --plan が「取り直す区域」を出す。
     取り直し(inat-refresh)は --max-requests 必須・1 回の質問の上限(10)を超えない・計測フックとゲートの下だけ。
- 3: 例年の時期が分からない候補に「分かりません」の印と代わりの材料(今年の行事・前の年の記録)。候補から外さない(評価表 R4 の読み方 (b))。"""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import profiles as PR
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import birds_live
from ikimonobiyori.fetch.cache import Cache
from ikimonobiyori.paths import data_path

P = O.load_policy()
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 1, 14, 0, tzinfo=JST)
D = [date(2026, 11, 2)]
PROF = PR.load_profiles()["birds"]
CFG = load_config()
AREAS = [a["id"] for a in O.load_obs_bird_areas()]

SPOTS = {"spots": [
    {"id": f"t-b-{i}", "subject": "birds", "name": f"試験の探鳥地{i}", "prefecture": "神奈川県", "city": "試験市", "bird_area": a, "pages": []}
    for i, a in enumerate(AREAS)] + [
    {"id": "t-h-1", "subject": "flowers", "name": "試験の花畑", "prefecture": "神奈川県", "city": "試験市", "flower_kinds": ["コスモス"], "pages": []},
    {"id": "t-h-2", "subject": "flowers", "name": "試験の庭", "prefecture": "神奈川県", "city": "試験市", "flower_kinds": ["バラ"], "pages": []},
    {"id": "t-h-3", "subject": "flowers", "name": "試験の行事の庭", "prefecture": "神奈川県", "city": "試験市", "flower_kinds": ["キク"],
     "events": [{"name": "試験の菊まつり", "start": "2026-10-31", "end": "2026-11-23", "url": "https://kiku.example.org/",
                 "publisher": "試験の行事の庭", "source_class": "official"}], "pages": []},
]}
CATALOGS = {"birds": {"entries": []}, "flowers": {"entries": []}}
BODY = {"total_results": 3, "page": 1, "per_page": 200, "results": [
    {"count": 20, "taxon": {"id": 1, "name": "Anas crecca", "preferred_common_name": "コガモ"}},
    {"count": 12, "taxon": {"id": 2, "name": "Anas acuta", "preferred_common_name": "オナガガモ"}},
    {"count": 8, "taxon": {"id": 3, "name": "Phoenicurus auroreus", "preferred_common_name": "ジョウビタキ"}}]}


class Fake:
    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return 200, json.dumps(BODY, ensure_ascii=False), {}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def put_inat(self, area_id, d, fetched_at):
        area = O._rounded(O._area_by_id(area_id), PROF)
        cache = Cache(data_path(CFG["cache"]["dir"], self.env))
        for q in O._inat_queries(area, d, PROF, CFG):
            cache.put(url=q["url"], params=q["params"], body=json.dumps(BODY, ensure_ascii=False), source="iNaturalist API", fetched_at=fetched_at)

    def put_all(self, d, fetched_at):
        for a in AREAS:
            self.put_inat(a, d, fetched_at)

    def plan(self, now=NOW, dates=D, policy=None):
        return O.plan("birds", region="神奈川", dates=dates, now=now, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS, policy=policy)["inat_refresh"]


class FetchedAtIsReceiveTime(Base):
    def test_fetched_at_is_clock_not_now(self):
        """--now(判定の基準)に実際より後の時刻を渡しても、取得時刻は応答を受け取った時刻(clock)。"""
        area = O._rounded(O._area_by_id(AREAS[0]), PROF)
        cache = Cache(data_path(CFG["cache"]["dir"], self.env))
        got = datetime(2026, 11, 1, 7, 14, 3, tzinfo=JST)
        inputs, rep = birds_live.fetch_bird_counts(area, D, PROF, NOW, cache=cache, cfg=CFG, http_get=Fake(), live=True, max_requests=5,
                                                   unparsed_dir=self.tmp.name, sleep=lambda s: None, clock=lambda: got)
        self.assertEqual(rep["requests"], 2)
        self.assertEqual(inputs["fetched_at"], "2026-11-01T07:14:03+09:00")
        for q in O._inat_queries(area, D[0], PROF, CFG):
            e, _ = cache.get(q["url"], q["params"], now=NOW, ttl_s=10 ** 9)
            self.assertEqual(e["fetched_at"], "2026-11-01T07:14:03+09:00")

    def test_default_clock_is_the_real_clock(self):
        """clock を渡さなければ実際の時計(--now の時間帯で)。--now が未来でも取得時刻は未来にならない。"""
        future = datetime(2030, 1, 1, 14, 0, tzinfo=JST)
        before = datetime.now(JST).replace(microsecond=0)
        s = birds_live.received_at(future)
        after = datetime.now(JST)
        t = datetime.fromisoformat(s)
        self.assertTrue(before <= t <= after, s)
        self.assertEqual(t.utcoffset(), timedelta(hours=9))

    def test_clock_without_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            birds_live.received_at(NOW, lambda: datetime(2026, 11, 1, 7, 14))


class RefreshPlan(Base):
    def test_fresh_and_in_period_is_not_listed(self):
        self.put_all(D[0], "2026-10-28T07:14:00+09:00")                       # 4 日前・対象の日そのもの
        r = self.plan()
        self.assertFalse(r["needed"])
        self.assertEqual((r["areas"], r["deferred"]), ([], []))
        self.assertEqual(sorted(x["area"] for x in r["fresh"]), sorted(AREAS))

    def test_eight_days_old_is_listed(self):
        self.put_all(D[0], "2026-10-24T07:14:00+09:00")                       # 8 日前
        r = self.plan()
        self.assertTrue(r["needed"])
        self.assertEqual({x["state"] for x in r["areas"]}, {"stale"})
        self.assertEqual(len(r["areas"]), len(AREAS))
        self.assertTrue(all(x["age_days"] > 7 for x in r["areas"]))
        self.assertLessEqual(r["planned_requests"], 10)

    def test_seven_days_is_still_fresh(self):
        self.put_all(D[0], "2026-10-25T14:00:00+09:00")                       # ちょうど 7 日
        self.assertFalse(self.plan()["needed"])

    def test_target_out_of_previous_period_is_listed(self):
        """前回の集計(中心 11/2・前後 1 週)の期間の中の 11/6 は取り直さず前回の集計を使い、期間の外の 11/20 は取り直す。"""
        self.put_all(D[0], "2026-10-31T07:14:00+09:00")
        O._write_inat_index({a: [{"center": "2026-11-02", "window_days": 7, "fetched_at": "2026-10-31T07:14:00+09:00", "requests": 2}]
                             for a in AREAS}, self.env)
        inside = self.plan(dates=[date(2026, 11, 6)])
        self.assertFalse(inside["needed"])
        self.assertEqual({x["center"] for x in inside["fresh"]}, {"2026-11-02"})
        out = self.plan(dates=[date(2026, 11, 20)])
        self.assertTrue(out["needed"])
        self.assertEqual({x["state"] for x in out["areas"]}, {"out_of_period"})
        # 期間の中なら facts も前回の集計を使い、中心の日を書く
        f = O.facts("birds", region="神奈川", dates=[date(2026, 11, 6)], now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)
        c = f["candidates"][0]
        self.assertEqual(c["inat"]["center"], "2026-11-02")
        self.assertIn("11/2の前後1週間", c["season_line"])

    def test_no_cache_is_listed_and_limit_is_kept(self):
        r = self.plan()
        self.assertEqual({x["state"] for x in r["areas"]}, {"none"})
        self.assertLessEqual(r["planned_requests"], r["max_requests"])
        pol = copy.deepcopy(P)
        pol["inat_refresh"]["max_requests_per_question"]["value"] = 5
        r = self.plan(policy=pol)
        self.assertEqual((r["planned_requests"], len(r["areas"]), len(r["deferred"])), (4, 2, len(AREAS) - 2))


class Refresh(Base):
    def test_refresh_stops_at_limit_and_writes_index(self):
        http = Fake()
        got = datetime(2026, 11, 1, 7, 14, tzinfo=JST)
        out = O.inat_refresh(AREAS, D[0], NOW, max_requests=5, env=self.env, http_get=http, sleep=lambda s: None, clock=lambda: got)
        self.assertEqual(out["requests"], 4)                                  # 区域ごと 2 リクエスト。3 つ目の区域は上限に収まらない
        self.assertEqual(len(http.calls), 4)
        self.assertEqual([x["area"] for x in out["fetched"]], AREAS[:2])
        self.assertEqual([x["area"] for x in out["deferred"]], AREAS[2:])
        idx = O.read_inat_index(self.env)
        self.assertEqual(sorted(idx), sorted(AREAS[:2]))
        self.assertEqual(idx[AREAS[0]][0], {"center": "2026-11-02", "window_days": 7, "fetched_at": "2026-11-01T07:14:00+09:00", "requests": 2})
        self.assertTrue(all(u.startswith("https://api.inaturalist.org/") for u in http.calls))
        # 取り直した区域は新しい扱い(--now 14:00 でも取得時刻は 07:14)
        st = O.inat_status(AREAS[0], D[0], NOW, env=self.env)
        self.assertEqual((st["state"], st["fetched_at"]), ("fresh", "2026-11-01T07:14:00+09:00"))

    def test_refresh_never_exceeds_question_limit(self):
        http = Fake()
        out = O.inat_refresh(AREAS * 3, D[0], NOW, max_requests=99, env=self.env, http_get=http, sleep=lambda s: None)
        self.assertEqual(out["max_requests"], 10)
        self.assertLessEqual(len(http.calls), 10)
        self.assertLessEqual(out["requests"], 10)

    def test_second_refresh_uses_cache(self):
        http = Fake()
        O.inat_refresh(AREAS[:1], D[0], NOW, max_requests=10, env=self.env, http_get=http, sleep=lambda s: None)
        http2 = Fake()
        out = O.inat_refresh(AREAS[:1], D[0], NOW + timedelta(minutes=5), max_requests=10, env=self.env, http_get=http2, sleep=lambda s: None)
        self.assertEqual((out["requests"], http2.calls), (0, []))

    def test_max_requests_is_required(self):
        with self.assertRaises(ValueError):
            O.inat_refresh(AREAS, D[0], NOW, max_requests=None, env=self.env, http_get=Fake())

    def test_cli_refuses_without_gate(self):
        """本物の通信(http_get の注入なし)は、テスト中は常に拒否(BIYORI_UNDER_TEST=1)。"""
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = O.main(["inat-refresh", "--region", "神奈川", "--date", "2026-11-02", "--now", NOW.isoformat(), "--max-requests", "10"])
        self.assertEqual(rc, 4)
        self.assertEqual(out.getvalue(), "")


class R4TypicalUnknown(Base):
    def facts(self):
        return O.facts("flowers", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)

    def test_unknown_typical_is_marked_and_kept(self):
        O.record([{"subject": "flowers", "spot": "t-h-1", "state": "コスモスは見頃です", "state_date": "2025-11-04",
                   "url": "https://hana.example.org/2025", "publisher": "試験の花畑", "source_class": "official"}], env=self.env, now=NOW)
        f = self.facts()
        ids = [c["id"] for c in f["candidates"]]
        self.assertTrue({"t-h-1", "t-h-2", "t-h-3"} <= set(ids))             # 分からなくても候補から外さない
        by = {c["id"]: c for c in f["candidates"]}
        a = by["t-h-1"]
        self.assertTrue(a["typical_unknown"])
        self.assertEqual(a["typical_alternatives"]["last_year"][0]["date"], "2025-11-04")
        self.assertEqual(a["typical_line"], "例年の時期は分かりません(2025年11/4の記録(試験の花畑)では「コスモスは見頃です」)")
        b = by["t-h-3"]
        self.assertTrue(b["typical_unknown"])
        self.assertEqual(b["typical_alternatives"]["events"][0]["name"], "試験の菊まつり")
        self.assertEqual(b["typical_line"], "例年の時期は分かりません(今年の行事「試験の菊まつり」は10/31〜11/23)")
        c = by["t-h-2"]
        self.assertTrue(c["typical_unknown"])
        self.assertEqual(c["typical_alternatives"], {"events": [], "last_year": [], "event_periods_not_typical": []})
        self.assertEqual(c["typical_line"], "例年の時期は分かりません")

    def test_known_typical_has_no_mark(self):
        spots = copy.deepcopy(SPOTS)
        spots["spots"][-3]["typical"] = [{"text": "10月中旬～11月上旬", "kind": "コスモス", "publisher": "試験の協会",
                                          "url": "https://hana.example.org/", "source_class": "official"}]
        f = O.facts("flowers", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=spots, catalogs=CATALOGS)
        a = next(c for c in f["candidates"] if c["id"] == "t-h-1")
        self.assertFalse(a["typical_unknown"])
        self.assertIsNone(a["typical_alternatives"])

    def test_birds_season_unknown_mark(self):
        f = O.facts("birds", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)
        self.assertTrue(all(c["season_unknown"] for c in f["candidates"]))
        self.assertTrue(all(c["typical_unknown"] is False for c in f["candidates"]))
        self.put_all(D[0], "2026-10-31T07:14:00+09:00")
        f = O.facts("birds", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)
        self.assertTrue(all(not c["season_unknown"] for c in f["candidates"]))


if __name__ == "__main__":
    unittest.main()
