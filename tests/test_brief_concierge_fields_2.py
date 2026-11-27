"""資料(ask brief)のコンシェル向けの項目の仕上げ(指示書 docs/brief-concierge-fields-2-instructions.md。2026-11-27)。通信しない。
第 2 部: 座標の細かさ coord_precision と、野鳥の観察の名所の座標を野鳥のプロファイルの位置の粗さに丸めて出すこと(丸める前の値をどこにも出さない)。"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from jsonschema import Draft202012Validator

from ikimonobiyori import catalog as CM
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import proposals as PR
from ikimonobiyori.engine import round_coord
from ikimonobiyori.profiles import load_profiles

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
SCHEMA = json.loads((H.ROOT / "ikimonobiyori" / "schemas" / "guide-brief.schema.json").read_text(encoding="utf-8"))
BIRD_Q = ["今週末、野鳥を見に行きたい", "今週末のおすすめは?"]


def bird_spots(ix):
    return [s for s in ix["spots"].values() if s["subject"] in GB.cfg()["concierge_fields"]["spot_coords_coarsen_subjects"]]


def raw_of(s):
    return next(((x["lat"], x["lon"]) for x in (s.get("point"), s.get("bird_range"))
                 if isinstance(x, dict) and x.get("lat") is not None and x.get("source")), None)


class Briefs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-brief-fields-2-")
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        GB._HOSTS = None
        cls.docs = [GB.build(q, now=NOW) for q in BIRD_Q]
        for d in cls.docs:
            GB.save(d)                                   # 資料の置き場所(briefs/)に書いたものも見る
        cls.ix = GB._place_index()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def test_schema(self):
        for d in self.docs:
            self.assertEqual([e.message for e in Draft202012Validator(SCHEMA).iter_errors(d)], [], d["question"])

    def test_coord_precision_follows_the_source(self):
        n = {"catalog": 0, "via": 0, "coarse": 0}
        for d in self.docs:
            for r in d["candidates"]:
                if r["lat"] is None:
                    self.assertIsNone(r["coord_precision"], r["name"])
                    continue
                sid = r["place_id"].split(":", 1)[1]
                if r["coord_source"] == "catalog":
                    self.assertEqual(r["coord_precision"], self.ix["catalog"][sid].get("location_precision"))
                    n["catalog"] += 1
                elif r["coord_source"] == "catalog_via_spot":
                    self.assertEqual(r["coord_precision"], self.ix["catalog"][self.ix["spots"][sid]["catalog_ref"]].get("location_precision"))
                    n["via"] += 1
                elif r["coord_source"] == "observation_spot":
                    self.assertIsNone(r["coord_precision"])         # 観察の名所の point には細かさが書かれていない(推測しない)
                else:
                    self.assertEqual(r["coord_source"], "observation_spot_coarsened")
                    n["coarse"] += 1
        self.assertTrue(all(n.values()), n)

    def test_bird_spot_coordinates_are_coarsened_with_the_profile_precision(self):
        prec = load_profiles()["birds"]["care"]["location_precision"]
        self.assertEqual(PR.coarse_precision(None, load_profiles()["birds"], CM.load_policy()), prec)
        seen = 0
        for d in self.docs:
            for r in d["candidates"]:
                if r["coord_source"] != "observation_spot_coarsened":
                    continue
                s = self.ix["spots"][r["place_id"].split(":", 1)[1]]
                raw = raw_of(s)
                self.assertEqual((r["lat"], r["lon"], r["coord_precision"]), (round_coord(raw[0], prec), round_coord(raw[1], prec), prec), r["name"])
                seen += 1
        self.assertGreaterEqual(seen, 5)

    def test_raw_bird_coordinates_appear_nowhere(self):
        """丸める前の値(丸めると変わるもの)は、資料の JSON にも、データ置き場に書いた資料(JSON・Markdown)にも出ない(絶対ルール 7)。"""
        prec = load_profiles()["birds"]["care"]["location_precision"]
        raws = {raw for s in bird_spots(self.ix) if (raw := raw_of(s)) and (round_coord(raw[0], prec), round_coord(raw[1], prec)) != raw}
        self.assertGreaterEqual(len(raws), 5)
        files = [p for p in Path(self.tmp.name).rglob("*") if p.is_file() and p.suffix in (".json", ".md", ".jsonl")]
        self.assertTrue(any(p.parent.name == "briefs" for p in files))
        docs = list(self.docs)
        for p in files:
            t = p.read_text(encoding="utf-8")
            for lat, lon in raws:                                       # 文として(緯度と経度の組。ほかの名所の値と 1 つだけ一致することはある)
                self.assertNotRegex(t, rf"{lat:.2f}\D{{1,40}}{lon:.2f}", p.name)
            if p.suffix == ".json":
                docs.append(json.loads(t))
            elif p.suffix == ".jsonl":
                docs += [json.loads(x) for x in t.splitlines() if x.strip()]

        def walk(x):
            if isinstance(x, dict):
                if "lat" in x and "lon" in x:
                    yield (x["lat"], x["lon"])
                for v in x.values():
                    yield from walk(v)
            elif isinstance(x, list):
                for v in x:
                    yield from walk(v)
        pairs = {pt for d in docs for pt in walk(d)}
        self.assertTrue(pairs)
        self.assertEqual(pairs & raws, set())

    def test_coarsened_distance_is_within_the_rounding(self):
        pol = CM.load_policy()
        for d in self.docs:
            for r in d["candidates"]:
                if r["coord_source"] == "observation_spot_coarsened" and r.get("distance_km") is not None:
                    km = CM.range_from(pol, {"lat": r["lat"], "lon": r["lon"]}, d["origin"])["km"]
                    self.assertLess(abs(km - r["distance_km"]), 8, r["name"])   # 小数 1 桁に丸めると 1 点が最大およそ 7km 動く


class PlaceOf(unittest.TestCase):
    def setUp(self):
        self.c = GB.cfg()
        self.ix = GB._place_index()

    def place(self, sid, ix=None):
        return GB._place_of({"name": "試験", GB.PLACE_SRC_KEY: sid}, ix or self.ix, self.c)

    def test_catalog_precision_is_copied(self):
        e = self.ix["catalog"]["yacho-0001"]
        self.assertEqual(self.place("yacho-0001")["coord_precision"], e["location_precision"])

    def test_catalog_via_spot_keeps_priority_for_bird_spot(self):
        p = self.place("obs-yacho-0003")                                  # 横浜自然観察の森: catalog_ref のカタログの座標のまま
        e = self.ix["catalog"]["yacho-0004"]
        self.assertEqual((p["lat"], p["lon"], p["coord_source"], p["coord_precision"]),
                         (e["point"]["lat"], e["point"]["lon"], "catalog_via_spot", e["location_precision"]))

    def test_bird_spot_without_coordinates(self):
        self.assertIsNone(raw_of(self.ix["spots"]["obs-yacho-0005"]))
        p = self.place("obs-yacho-0005")
        self.assertEqual((p["place_id"], p["lat"], p["coord_source"], p["coord_precision"]), ("ikimonobiyori:obs-yacho-0005", None, None, None))

    def test_unknown_precision_gives_no_coordinates(self):
        ix = dict(self.ix, coarse={})                                     # プロファイルが読めなかったとき
        p = self.place("obs-yacho-0002", ix)
        self.assertEqual((p["lat"], p["lon"], p["coord_source"], p["coord_precision"]), (None, None, None, None))
        self.assertIsNone(GB._coarsened((35.39, 139.55), "exact"))       # 丸める桁が決まっていない粗さでは、元の値を出さない
        self.assertIsNone(GB._coarsened((35.39, 139.55), None))

    def test_profile_failure_gives_empty_coarse_table(self):
        with mock.patch("ikimonobiyori.profiles.load_profiles", side_effect=ValueError("x")):
            self.assertEqual(GB._coarse_precisions(), {})

    def test_proposal_place_uses_the_same_rule(self):
        pol = CM.load_policy()
        prof = load_profiles()["birds"]
        e = {"id": "t", "name": "t", "point": {"lat": 35.123, "lon": 139.456}, "location_precision": "exact"}
        pl = PR.place_of(e, prof, pol)
        self.assertEqual((pl["lat"], pl["lon"], pl["location_precision"]), (35.1, 139.5, "area_10km"))   # 件(exact)とプロファイル(area_10km)の粗い方
        self.assertEqual(PR.coarse_precision("area_10km", {"care": {"location_precision": "exact"}}, pol), "area_10km")
        self.assertIsNone(PR.coarse_precision(None, {}, pol))


if __name__ == "__main__":
    unittest.main()
