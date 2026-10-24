"""紅葉の地点の集合(段階14b): --site-set mountains(既定)/ catalog / both。偽の http_get だけ。通信なし。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H

from ikimonobiyori import catalog, main as imain, profiles as ip

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
MOUNTAINS, _ = ip.load_sites()
CATALOG = catalog.catalog_sites(catalog.load_catalog("autumn_leaves"))


def distinct_points(*site_sets):
    """取得の回数の期待: 同じ座標の地点は 1 回の取得を共有する(段階19 で、粗い座標を共有する地点が増えた)。"""
    return len({(s["lat"], s["lon"]) for sites in site_sets for s in sites.values()})


def resp():
    t0 = datetime(2026, 10, 11)
    return {"latitude": 0, "longitude": 0, "daily": {"time": [(t0 + timedelta(days=i)).date().isoformat() for i in range(8)],
                                                   "temperature_2m_min": [5.0] * 8}}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return 200, json.dumps(resp())


def request_file():
    p = Path(tempfile.mkdtemp()) / "r.json"
    p.write_text(json.dumps({"schema": "biyori-request/1", "request_id": "sets", "intent": "weekend_outing",
                             "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-17T23:59:00+09:00"},
                             "origin": {"name": "x", "lat": 35.0, "lon": 139.0}, "interests": ["autumn_leaves"]}), encoding="utf-8")
    return p


def run(*extra):
    out, http = Path(tempfile.mkdtemp()) / "o.json", FakeHttp()
    rc = imain.main(["--request", str(request_file()), "--live", "--max-requests", "200", "--now", NOW.isoformat(),
                     "--cache-dir", tempfile.mkdtemp(), "--out", str(out), *extra], http_get=http)
    return rc, (json.loads(out.read_text(encoding="utf-8")) if rc == 0 else None), http


class CatalogSites(unittest.TestCase):
    def test_only_approved_entries_with_a_point(self):
        doc = catalog.load_catalog("autumn_leaves")
        approved = {e["id"] for e in catalog.approved_entries(doc) if e.get("point")}
        self.assertEqual(set(CATALOG), approved)
        self.assertTrue(len(CATALOG) >= 10)
        self.assertFalse(any(k.startswith("kouyou-example") for k in CATALOG))
        self.assertFalse(set(CATALOG) & set(MOUNTAINS))                                   # id が 76 地点と重ならない

    def test_candidates_are_never_sites(self):
        doc = {"schema": "ikimono-site-catalog/1", "subject": "autumn_leaves",
               "entries": [{"id": "kouyou-9999", "name": "x", "subjects": ["autumn_leaves"], "timing_type": "temperature", "kind": "point",
                            "point": {"lat": 35.0, "lon": 139.0}, "location_precision": "exact", "status": "candidate",
                            "sources": [{"url": "https://example.org"}]}]}
        self.assertEqual(catalog.catalog_sites(doc), {})
        self.assertEqual(catalog.catalog_sites(None), {})

    def test_site_ref_points_to_the_catalog(self):
        for sid, s in CATALOG.items():
            self.assertEqual(s["site_ref"], f"ikimonobiyori:{sid}")


class SiteSets(unittest.TestCase):
    def test_default_is_the_76_mountains(self):
        rc, doc, http = run()
        self.assertEqual(rc, 0)
        self.assertEqual(len(http.calls), len(MOUNTAINS))
        self.assertEqual({p["details"]["site_id"] for p in doc["proposals"]}, set(MOUNTAINS))
        self.assertFalse(any("sources" in p["place"] or "landmark" in p["details"] for p in doc["proposals"]))
        rc2, doc2, _ = run("--site-set", "mountains")
        self.assertEqual([p["id"] for p in doc2["proposals"]], [p["id"] for p in doc["proposals"]])

    def test_catalog_set_gives_valid_proposals_with_place_and_sources(self):
        rc, doc, http = run("--site-set", "catalog")
        self.assertEqual(rc, 0)
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual(len(http.calls), distinct_points(CATALOG))
        self.assertEqual({p["details"]["site_id"] for p in doc["proposals"]}, set(CATALOG))
        for p in doc["proposals"]:
            s = CATALOG[p["details"]["site_id"]]
            pl = p["place"]
            self.assertEqual((pl["name"], pl["lat"], pl["lon"], pl["elevation_m"], pl["location_precision"]),
                             (s["name"], s["lat"], s["lon"], s["elevation_m"], s["location_precision"]))
            self.assertEqual(pl["site_ref"], f"ikimonobiyori:{s['id']}")
            self.assertTrue(pl["sources"] and all(x["url"].startswith("https://") for x in pl["sources"]))
            self.assertEqual(p["details"]["landmark"]["id"], s["id"])
            self.assertTrue(p["uncertainty"]["known_limits"])                             # 段階14 の不合格の注記もそのまま出す
            self.assertNotEqual(p["suitability"]["band"], "go")                          # validated: false のまま

    def test_both_is_the_union(self):
        rc, doc, http = run("--site-set", "both")
        self.assertEqual(rc, 0)
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual(len(http.calls), distinct_points(MOUNTAINS, CATALOG))
        self.assertEqual({p["details"]["site_id"] for p in doc["proposals"]}, set(MOUNTAINS) | set(CATALOG))

    def test_sites_list_works_within_the_set(self):
        sid = sorted(CATALOG)[0]
        rc, doc, http = run("--site-set", "catalog", "--sites", sid)
        self.assertEqual((rc, len(http.calls)), (0, 1))
        rc, _, _ = run("--site-set", "catalog", "--sites", "m001")                       # 76 地点は catalog の集合にない
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
