"""名所カタログとプロファイルの検査器(段階13。ikimonobiyori/catalog.py)。通信なし。
正しい例が通り、不正な例(出典のない例年値、細かすぎる位置、未知の timing_type など)がすべて拒否されること。"""
import contextlib
import copy
import io
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import helpers as H
from helpers import ROOT

from ikimonobiyori import catalog, paths
from ikimonobiyori.profiles import load_profiles

PROFILE_IDS = {"autumn_leaves", "birds", "fireflies", "cherry_blossom", "higanbana", "sunflower", "bioluminescence"}


def entry(**kw):
    e = {"id": "kouyou-0001", "name": "試験の渓谷", "subjects": ["autumn_leaves"], "timing_type": "temperature", "kind": "point",
         "point": {"lat": 35.12345, "lon": 139.12345, "elevation_m": 900}, "location_precision": "exact", "status": "candidate",
         "sources": [{"url": "https://example.org/a", "checked_on": "2026-10-21"}]}
    e.update(kw)
    return e


def doc(*entries, subject="autumn_leaves"):
    return {"schema": "ikimono-site-catalog/1", "subject": subject, "entries": list(entries)}


class Catalog(unittest.TestCase):
    POLICY = catalog.load_policy()

    def errs(self, d, name=None):
        return catalog.check_catalog(d, name=name or d.get("subject"), profile_ids=PROFILE_IDS, policy=self.POLICY)

    def assertRejected(self, d, needle=None, name=None):
        errs = self.errs(d, name)
        self.assertTrue(errs, "拒否されるはず")
        if needle:
            self.assertTrue(any(needle in e for e in errs), errs)

    def test_the_repository_catalog_and_profiles_pass(self):
        res = catalog.check_all()
        self.assertEqual([(p.name, e) for p, e in res if e], [])
        names = sorted(f"{p.parent.name}/{p.name}" for p, _ in res)
        self.assertIn("catalog/autumn_leaves.yaml", names)
        self.assertEqual(len([n for n in names if n.startswith("profiles/")]), 9)        # 段階16 C で wintering_birds、段階17 フェーズ4 で flowers を足した
        self.assertNotIn("catalog/policy.yaml", names)                       # 方針のファイルはカタログとして検査しない

    def test_cli_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(catalog.main(["check"]), 0)
        self.assertIn("OK  catalog/autumn_leaves.yaml", out.getvalue())
        d = Path(tempfile.mkdtemp(prefix="ikimono-cat-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "autumn_leaves.yaml").write_text(yaml.safe_dump(doc(entry(typical_window={"start": "11-01", "end": "11-15"})), allow_unicode=True), encoding="utf-8")
        with contextlib.redirect_stdout(out):
            self.assertEqual(catalog.main(["check", "--catalog-dir", str(d)]), 1)
        self.assertIn("NG  ", out.getvalue())

    def test_valid_examples_pass(self):
        self.assertEqual(self.errs(doc(entry())), [])
        self.assertEqual(self.errs(doc(entry(status="approved", approved_at="2026-10-21",
                                             typical_window={"start": "11-01", "end": "11-15", "source_url": "https://example.org/t"}))), [])
        self.assertEqual(self.errs(doc(entry(status="retired", retired_at="2026-10-21", retired_reason="立入禁止"))), [])
        self.assertEqual(self.errs(doc(entry(typical_window={"start": "12-20", "end": "01-10", "source_url": "https://example.org/t"}))), [])   # 年をまたぐ
        self.assertEqual(self.errs(doc(entry(typical_window={"start": "02-29", "end": "03-05", "source_url": "https://example.org/t"}))), [])
        self.assertEqual(self.errs(doc(entry(site_ref="yamabiyori:m012"))), [])

    def test_typical_window_without_a_source_is_rejected(self):
        self.assertRejected(doc(entry(typical_window={"start": "11-01", "end": "11-15"})), "source_url")
        self.assertRejected(doc(entry(typical_window={"start": "11-01", "end": "11-15", "source_url": ""})))
        self.assertRejected(doc(entry(typical_window={"start": "11-01", "end": "11-15", "source_url": "見た"})))

    def test_impossible_or_malformed_dates_are_rejected(self):
        self.assertRejected(doc(entry(typical_window={"start": "02-30", "end": "03-05", "source_url": "https://example.org/t"})), "存在しない日付")
        self.assertRejected(doc(entry(typical_window={"start": "11-1", "end": "11-15", "source_url": "https://example.org/t"})))
        self.assertRejected(doc(entry(typical_window={"start": "13-01", "end": "11-15", "source_url": "https://example.org/t"})))
        self.assertRejected(doc(entry(status="approved", approved_at="2026-02-30")), "日付でない")

    def test_unknown_timing_type_kind_status_or_precision_is_rejected(self):
        self.assertRejected(doc(entry(timing_type="weather")))
        self.assertRejected(doc(entry(kind="mountain")))
        self.assertRejected(doc(entry(status="draft")))
        self.assertRejected(doc(entry(location_precision="area_5km")))

    def test_sources_are_required(self):
        e = entry()
        del e["sources"]
        self.assertRejected(doc(e), "sources")
        self.assertRejected(doc(entry(sources=[])))
        self.assertRejected(doc(entry(sources=[{"title": "URL なし"}])))

    def test_approved_needs_approved_at(self):
        self.assertRejected(doc(entry(status="approved")), "approved_at")

    def test_examples_cannot_be_approved(self):
        self.assertRejected(doc(entry(example=True, status="approved", approved_at="2026-10-21")), "例")

    def test_too_fine_locations_are_rejected_for_birds_and_fireflies(self):
        for subject, eid in (("birds", "yacho-0001"), ("fireflies", "hotaru-0001")):
            with self.subTest(subject=subject):
                base = dict(id=eid, subjects=[subject], timing_type="frequency" if subject == "birds" else "temperature")
                self.assertRejected(doc(entry(**base), subject=subject), "細かすぎる")
                self.assertRejected(doc(entry(**base, location_precision="area_1km", point={"lat": 35.12, "lon": 139.12}), subject=subject), "細かすぎる")
                self.assertEqual(self.errs(doc(entry(**base, location_precision="area_10km", point={"lat": 35.1, "lon": 139.1}), subject=subject)), [])

    def test_coordinates_must_match_the_precision(self):
        self.assertRejected(doc(entry(id="yacho-0001", subjects=["birds"], timing_type="frequency", location_precision="area_10km",
                                      point={"lat": 35.12, "lon": 139.1}), subject="birds"), "point.lat")
        self.assertRejected(doc(entry(location_precision="area_1km", point={"lat": 35.123, "lon": 139.12})), "point.lat")
        self.assertEqual(self.errs(doc(entry(location_precision="area_1km", point={"lat": 35.12, "lon": 139.1}))), [])

    def test_public_venue_allows_exact_for_fireflies_only(self):
        venue = {"source_url": "https://example.org/hotaru-kanshoukai"}
        ff = dict(id="hotaru-0001", subjects=["fireflies"], timing_type="managed")
        self.assertEqual(self.errs(doc(entry(**ff, public_venue=venue), subject="fireflies")), [])
        self.assertRejected(doc(entry(**ff, public_venue={"note": "URL なし"}), subject="fireflies"))       # 公開会場の出典が要る
        self.assertRejected(doc(entry(**ff, public_venue=venue, sensitive=True), subject="fireflies"), "sensitive")   # 希少種は例外が効かない
        bd = dict(id="yacho-0001", subjects=["birds"], timing_type="frequency")
        self.assertRejected(doc(entry(**bd, public_venue=venue), subject="birds"), "細かすぎる")             # 野鳥は例外なし

    def test_sensitive_entries_need_area_10km(self):
        self.assertRejected(doc(entry(sensitive=True)), "sensitive")
        self.assertEqual(self.errs(doc(entry(sensitive=True, location_precision="area_10km", point={"lat": 35.1, "lon": 139.1}))), [])

    def test_multi_subject_entries_use_the_coarsest_floor(self):
        self.assertRejected(doc(entry(subjects=["autumn_leaves", "birds"])), "birds")

    def test_unknown_subjects_mismatched_files_and_duplicates_are_rejected(self):
        self.assertRejected(doc(entry(subjects=["autumn_leaves", "moss"])), "未知の対象")
        self.assertRejected(doc(entry(subjects=["birds"], location_precision="area_10km", point={"lat": 35.1, "lon": 139.1})), "subjects にファイルの対象")
        self.assertRejected(doc(entry()), "ファイル名", name="birds")
        self.assertRejected(doc(entry(), entry()), "重複")
        self.assertRejected(doc(entry(), subject="moss"), "プロファイルがない", name="moss")

    def test_shape_errors(self):
        self.assertRejected({"schema": "ikimono-site-catalog/1", "subject": "autumn_leaves"})
        self.assertRejected(doc(entry(colour="red")))                         # 未知の項目
        self.assertRejected(doc(entry(id="Kouyou 1")))
        self.assertRejected(doc(entry(site_ref="m012")))
        self.assertRejected(doc(entry(point={"lat": 95, "lon": 139})))
        self.assertRejected(doc(entry(official_status_url="なし")))

    def test_description_is_used_only_when_approved_with_sources(self):
        ok = entry(status="approved", approved_at="2026-10-21", description="解説")
        self.assertEqual(catalog.usable_description(ok), "解説")
        self.assertIsNone(catalog.usable_description(entry(description="解説")))                                      # candidate
        self.assertIsNone(catalog.usable_description({**ok, "sources": []}))
        self.assertIsNone(catalog.usable_description({k: v for k, v in ok.items() if k != "approved_at"}))
        self.assertIsNone(catalog.usable_description({**ok, "example": True}))
        self.assertIsNone(catalog.usable_description({**ok, "status": "retired"}))
        d = doc(ok, entry(id="kouyou-0002"), entry(id="kouyou-0003", status="retired"))
        self.assertEqual([e["id"] for e in catalog.approved_entries(d)], ["kouyou-0001"])

    def test_the_repository_catalog_has_only_approved_real_entries(self):
        # 段階14b(ユーザーの指示 2026-10-22): 本番のカタログの実在の名所は承認済みだけ。説明用の例(example: true)は candidate のまま
        d = yaml.safe_load((paths.CATALOG_DIR / "autumn_leaves.yaml").read_text(encoding="utf-8"))
        real = [e for e in d["entries"] if not e.get("example")]
        examples = [e for e in d["entries"] if e.get("example")]
        self.assertTrue(real)
        for e in real:
            self.assertEqual(e["status"], "approved", e["id"])
            self.assertTrue(e.get("approved_at") and e["sources"], e["id"])
        for e in examples:
            self.assertEqual(e["status"], "candidate", e["id"])
        self.assertEqual([e["id"] for e in catalog.approved_entries(d)], [e["id"] for e in real])


class ProfileTimingType(unittest.TestCase):
    WANT = {"autumn_leaves": "temperature", "birds": "frequency", "cherry_blossom": "temperature", "higanbana": "calendar",
            "sunflower": "managed", "fireflies": "temperature", "bioluminescence": "episodic",
            "wintering_birds": "calendar",                                        # 段階16 C で足した対象(指示書 フェーズ5)
            "flowers": "managed"}                                                 # 段階17 フェーズ4 で足した対象(指示書)

    def test_every_profile_has_the_designed_timing_type(self):
        self.assertEqual({k: p["timing_type"] for k, p in load_profiles().items()}, self.WANT)

    def test_unknown_or_missing_timing_type_is_rejected(self):
        p = copy.deepcopy(load_profiles()["autumn_leaves"])
        self.assertEqual(catalog.check_profile(p), [])
        p["timing_type"] = "weather"
        self.assertTrue(catalog.check_profile(p))
        del p["timing_type"]
        self.assertTrue(catalog.check_profile(p))

    def test_the_engine_does_not_read_the_catalog_or_timing_type(self):
        src = (ROOT / "ikimonobiyori" / "engine.py").read_text(encoding="utf-8")
        self.assertNotIn("timing_type", src)
        self.assertNotIn("catalog", src)


class Drafts(unittest.TestCase):
    """段階14b の下書き(data/catalog/drafts/)。承認前の件は提案に使わない。本番のカタログとは分ける。"""
    DIR = paths.CATALOG_DIR / "drafts"

    def load(self):
        return yaml.safe_load((self.DIR / "autumn_leaves.yaml").read_text(encoding="utf-8"))

    def test_the_drafts_pass_the_checker(self):
        res = catalog.check_all(catalog_dir=self.DIR)
        self.assertEqual([(p.name, e) for p, e in res if e], [])
        self.assertIn("autumn_leaves.yaml", [p.name for p, _ in res])

    def test_drafts_are_unapproved_and_not_used(self):
        # フェーズ3 の後: 下書きには保留(と却下)だけが残る。承認済みは本番のカタログへ移した
        d = self.load()
        self.assertTrue(d["entries"])
        self.assertEqual({e["status"] for e in d["entries"]} - {"candidate", "retired"}, set())
        self.assertFalse(any(e.get("approved_at") or e.get("example") for e in d["entries"]))
        self.assertEqual(catalog.approved_entries(d), [])
        self.assertTrue(all(catalog.usable_description(e) is None for e in d["entries"]))

    def test_drafts_have_official_sources_and_only_autumn_leaves(self):
        for e in self.load()["entries"]:
            self.assertEqual(e["subjects"], ["autumn_leaves"], e["id"])
            self.assertTrue(e["sources"], e["id"])
            tw = e.get("typical_window")
            if tw:
                self.assertIn(tw["source_url"], [s["url"] for s in e["sources"]], e["id"])     # 時期の出典は sources にもある

    def test_no_entry_is_both_approved_and_in_the_drafts(self):
        main = yaml.safe_load((paths.CATALOG_DIR / "autumn_leaves.yaml").read_text(encoding="utf-8"))
        self.assertEqual({e["id"] for e in main["entries"]} & {e["id"] for e in self.load()["entries"]}, set())

    def test_approved_real_entries_are_in_range_and_have_a_point(self):
        pol = catalog.load_policy()
        main = yaml.safe_load((paths.CATALOG_DIR / "autumn_leaves.yaml").read_text(encoding="utf-8"))
        for e in catalog.approved_entries(main):
            self.assertIn("point", e, e["id"])
            self.assertLessEqual(catalog.nearest_origin_km(pol, e["point"])[0], pol["range_limit"]["max_km"])

    def test_the_default_catalog_dir_does_not_read_the_drafts(self):
        names = [p.parent.name + "/" + p.name for p, _ in catalog.check_all()]
        self.assertNotIn("drafts/autumn_leaves.yaml", names)


class RangeLimit(unittest.TestCase):
    POLICY = catalog.load_policy()

    def test_points_beyond_250km_are_rejected(self):
        osaka = entry(point={"lat": 34.70, "lon": 135.50, "elevation_m": 10})
        errs = catalog.check_catalog(doc(osaka), name="autumn_leaves", profile_ids=PROFILE_IDS, policy=self.POLICY)
        self.assertTrue(any("範囲外" in e for e in errs), errs)
        near = entry(point={"lat": 35.69, "lon": 139.71, "elevation_m": 40})
        self.assertEqual(catalog.check_catalog(doc(near), name="autumn_leaves", profile_ids=PROFILE_IDS, policy=self.POLICY), [])

    def test_the_limit_comes_from_the_policy(self):
        self.assertEqual(self.POLICY["range_limit"]["max_km"], 250)
        km, origin = catalog.nearest_origin_km(self.POLICY, {"lat": 35.466, "lon": 139.622})
        self.assertEqual((round(km), origin), (0, "横浜"))
        self.assertIsNone(catalog.nearest_origin_km({}, {"lat": 0, "lon": 0}))


if __name__ == "__main__":
    unittest.main()
