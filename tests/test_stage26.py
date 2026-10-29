"""段階26: 退役した出どころの URL(船橋市のページ)・追記・対応表。通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import CP, PLACES, item, recs

P = guide.load_policy()
FUNA = "https://www.city.funabashi.lg.jp/kids/facilities/p000586.html"
C1, C2 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/"


class RetiredUrl(unittest.TestCase):
    def test_funabashi_page_is_retired_with_a_reason_without_the_instruction(self):
        r = guide.load_retired(P)["urls"]
        self.assertEqual(r[FUNA], "ページ内に指示文(段階25、2026-10-30)")

    def test_it_is_not_counted_but_other_urls_are(self):
        build = lambda rows: {e["name"]: e for e in guide.build_entries(rows, PLACES, P, CP)}["試験の池"]
        a = build(recs(item(FUNA, name="試験の池", theme="野鳥"), item(C1, name="試験の池", theme="野鳥")))
        self.assertEqual((a["independent_sources"], a["tier"]), (2, "reference"))             # 記録はされるが、定評にはならない
        b = build(recs(item(C2, name="試験の池", theme="野鳥"), item(C1, name="試験の池", theme="野鳥")))
        self.assertEqual(b["tier"], "curated")                                                # 他の URL は今までどおり

    def test_the_funabashi_place_stays_reference(self):
        import yaml
        d = [e for e in guide.committed_entries() if e["name"] == "ふなばし三番瀬海浜公園"][0]
        self.assertEqual(d["tier"], "reference")


import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

from ikimonobiyori import paths  # noqa: E402

PL = dict(PLACES)
PL[("東京都", "追記区")] = {"prefecture": "東京都", "municipality": "追記区", "lat": 35.71, "lon": 139.71, "qid": "Q3"}
PL[("試験県", "遠い町")] = PLACES[("試験県", "遠い町")]


class Annotate(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s26-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = mock.patch.dict(os.environ, {paths.ENV_DATA_DIR: str(self.d)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _record(self, *items):
        n, dup, _ = guide.record_candidates(list(items), policy=P)
        return n

    def _mine(self, annotated=True):
        return next(r for r in guide.all_records(annotated=annotated) if r["name"] == "追記の沼")

    def _ann(self, **kw):
        base = dict(theme="野鳥", name="追記の沼", prefecture="東京都", url=C1, summary="ページの記載の要約")
        return {**base, **kw}

    def test_annotation_adds_a_municipality_and_changes_the_range(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "url": C1})
        before = {e["name"]: e for e in guide.build_entries(guide.all_records(), PL, P, CP)}["追記の沼"]
        self.assertEqual(before["range"]["status"], "pending")
        n, rows = guide.annotate([self._ann(municipality="追記区")], policy=P)
        self.assertEqual(n, 1)
        after = {e["name"]: e for e in guide.build_entries(guide.all_records(), PL, P, CP)}["追記の沼"]
        self.assertEqual(after["range"]["status"], "in_range")

    def test_unknown_municipality_stays_unconfirmed(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "url": C1})
        guide.annotate([self._ann(municipality="代表点のない町")], policy=P)                  # 通信しない: 代表点が無ければ未確認のまま
        e = {e["name"]: e for e in guide.build_entries(guide.all_records(), PL, P, CP)}["追記の沼"]
        self.assertEqual(e["range"]["status"], "pending")

    def test_same_publisher_annotation_does_not_add_a_source(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "municipality": "追記区", "url": C1})
        guide.annotate([self._ann(kinds=["カモ"]), self._ann(kinds=["カモ", "カワセミ"], summary="別の要約")], policy=P)
        e = {e["name"]: e for e in guide.build_entries(guide.all_records(), PL, P, CP)}["追記の沼"]
        self.assertEqual(e["independent_sources"], 1)
        self.assertEqual({k["kind"]: k["independent_sources"] for k in e["kinds"]}, {"カモ": 1, "カワセミ": 1})     # 1 件のまま(答えには出ない)
        self.assertFalse(any(k["shown"] for k in e["kinds"]))

    def test_two_publishers_saying_the_same_kind_are_shown(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "municipality": "追記区", "url": C1},
                     {"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "municipality": "追記区", "url": C2})
        guide.annotate([self._ann(kinds=["カモ"]), self._ann(url=C2, kinds=["カモ"])], policy=P)
        e = {e["name"]: e for e in guide.build_entries(guide.all_records(), PL, P, CP)}["追記の沼"]
        self.assertTrue(next(k for k in e["kinds"] if k["kind"] == "カモ")["shown"])

    def test_the_history_is_kept_and_the_record_is_unchanged(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "url": C1})
        raw0 = self._mine(False)
        guide.annotate([self._ann(municipality="追記区", summary="所在が書かれていた")], policy=P)
        raw1 = self._mine(False)
        self.assertEqual(raw0, raw1)                                                       # 元の記録は変わらない
        merged = self._mine()
        for k in ("url", "class", "publisher", "host", "read_at"):
            self.assertEqual(merged[k], raw0[k])
        hist = guide.all_annotations()
        self.assertEqual((hist[0]["summary"], hist[0]["url"], hist[0]["municipality"]), ("所在が書かれていた", C1, "追記区"))
        self.assertIn("at", hist[0])
        self.assertTrue((self.d / "guide" / "annotations.jsonl").is_file())

    def test_rejects_forbidden_changes_and_missing_targets(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "url": C1})
        for bad in (self._ann(municipality="追記区", publisher="偽"), self._ann(municipality="追記区", **{"class": "A"}),
                    self._ann(url="https://example.org/none", municipality="追記区"), self._ann(), self._ann(municipality="追記区", summary="")):
            with self.assertRaises(ValueError):
                guide.annotate([bad], policy=P)
        self.assertFalse((self.d / "guide" / "annotations.jsonl").exists())

    def test_municipality_already_recorded_is_not_overwritten(self):
        self._record({"theme": "野鳥", "name": "追記の沼", "prefecture": "東京都", "municipality": "試験区", "url": C1})
        guide.annotate([self._ann(municipality="追記区")], policy=P)
        self.assertEqual(self._mine()["municipality"], "試験区")

    def test_committed_annotations_file_exists(self):
        self.assertTrue(guide.ANNOTATIONS_PATH.is_file())
