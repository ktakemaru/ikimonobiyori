"""資料(ask brief)のコンシェル向けの項目(指示書 docs/brief-concierge-fields-instructions.md。2026-11-27)。通信しない。
候補の place_id・lat・lon・coord_source・site_ref と、資料を作った版 generator。スキーマ ikimonobiyori/schemas/guide-brief.schema.json。"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from jsonschema import Draft202012Validator

from ikimonobiyori import __version__
from ikimonobiyori import guide_brief as GB

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
SCHEMA = json.loads((H.ROOT / "ikimonobiyori" / "schemas" / "guide-brief.schema.json").read_text(encoding="utf-8"))
QUESTIONS = ["今週末、高尾山で紅葉を見たい", "今週末の紅葉の情報は?", "丹沢で今咲いている花は?", "八ヶ岳の見どころを教えて",
             "高尾山の見どころを教えて", "今週末、野鳥を見に行きたい", "今週末のおすすめは?", "神奈川と東京で紅葉の見ごろを教えて"]


def schema_errors(doc):
    return [f"{'/'.join(map(str, e.path))}: {e.message[:160]}" for e in Draft202012Validator(SCHEMA).iter_errors(doc)]


class EightBriefs(unittest.TestCase):
    """指示書 第 0 部の 8 つの質問の資料(空のデータ置き場。リポジトリのデータだけ)。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-brief-fields-")
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        GB._HOSTS = None
        cls.docs = [GB.build(q, now=NOW) for q in QUESTIONS]

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def test_schema(self):
        for d in self.docs:
            self.assertEqual(schema_errors(d), [], d["question"])

    def test_every_candidate_has_the_keys_and_no_working_key(self):
        n = 0
        for d in self.docs:
            for r in d["candidates"]:
                n += 1
                for k in GB.PLACE_KEYS:
                    self.assertIn(k, r)
                self.assertNotIn(GB.PLACE_SRC_KEY, r)
                self.assertEqual([k for k in r if k.startswith("_")], [])
                self.assertEqual(r["lat"] is None, r["lon"] is None)
                self.assertEqual(r["lat"] is None, r["coord_source"] is None)
        self.assertGreater(n, 50)

    def test_not_in_markdown_or_rules(self):
        for d in self.docs:
            md = GB.render_md(d)
            for r in d["candidates"]:
                if r["place_id"]:
                    self.assertNotIn(r["place_id"], md)
                if r["lat"] is not None:
                    self.assertNotIn(repr(r["lat"]), md)
            self.assertNotIn("generator", md)
            self.assertNotIn("place_id", " ".join(d["rules"]))

    def test_coordinates_are_copied_from_the_catalog(self):
        r = next(r for r in self.docs[0]["candidates"] if r["name"] == "国営昭和記念公園(日本庭園)")
        e = GB._place_index()["catalog"]["kouyou-0024"]
        self.assertEqual((r["place_id"], r["lat"], r["lon"], r["coord_source"]),
                         ("ikimonobiyori:kouyou-0024", e["point"]["lat"], e["point"]["lon"], "catalog"))

    def test_distance_is_unchanged_by_the_new_fields(self):
        from ikimonobiyori import catalog as CM
        pol = CM.load_policy()
        for d in self.docs:
            for r in d["candidates"]:
                if r["lat"] is not None and r.get("distance_km") is not None:
                    km = CM.range_from(pol, {"lat": r["lat"], "lon": r["lon"]}, d["origin"])["km"]
                    self.assertLess(abs(km - r["distance_km"]), 2, r["name"])     # 足した座標と、今までの距離が食い違わない(8 つの資料で確かめた)


class PlaceOf(unittest.TestCase):
    def setUp(self):
        self.c = GB.cfg()
        self.ix = GB._place_index()

    def place(self, **r):
        return GB._place_of({"name": "試験", **r}, self.ix, self.c)

    def test_spot_with_point(self):
        s = self.ix["spots"]["obs-kouyou-0088"]
        self.assertEqual(self.place(**{GB.PLACE_SRC_KEY: "obs-kouyou-0088"}),
                         {"place_id": "ikimonobiyori:obs-kouyou-0088", "lat": s["point"]["lat"], "lon": s["point"]["lon"],
                          "coord_source": "observation_spot", "site_ref": None})     # 高尾山。sites.yaml の m029 とは、文の注記しかないので結ばない

    def test_spot_catalog_ref(self):
        s = self.ix["spots"]["obs-yacho-0003"]
        e = self.ix["catalog"][s["catalog_ref"]]
        p = self.place(**{GB.PLACE_SRC_KEY: "obs-yacho-0003"})
        self.assertEqual((p["lat"], p["lon"], p["coord_source"]), (e["point"]["lat"], e["point"]["lon"], "catalog_via_spot"))

    def test_bird_spot_coordinates_are_not_copied(self):
        self.assertTrue(self.ix["spots"]["obs-yacho-0002"].get("bird_range"))
        p = self.place(**{GB.PLACE_SRC_KEY: "obs-yacho-0002"})
        self.assertEqual(p["place_id"], "ikimonobiyori:obs-yacho-0002")
        self.assertIsNone(p["lat"])                                    # 絶対ルール 7: 野鳥のプロファイルの粗さより細かい座標は写さない

    def test_spot_point_without_source_is_not_copied(self):
        s = self.ix["spots"]["obs-kouyou-0095"]
        self.assertTrue(s.get("point") and not s["point"].get("source"))
        p = self.place(**{GB.PLACE_SRC_KEY: "obs-kouyou-0095"})
        self.assertEqual((p["place_id"], p["lat"], p["coord_source"]), ("ikimonobiyori:obs-kouyou-0095", None, None))   # 出典のない座標は写さない

    def test_candidate_status_catalog_entry_is_copied(self):
        e = self.ix["catalog"]["hana-0009"]
        self.assertEqual(e["status"], "candidate")
        p = self.place(**{GB.PLACE_SRC_KEY: "hana-0009"})
        self.assertEqual((p["lat"], p["lon"], p["coord_source"]), (e["point"]["lat"], e["point"]["lon"], "catalog"))   # 順位に使われている件はそのまま写す

    def test_no_source_id(self):
        self.assertEqual(self.place(), dict.fromkeys(GB.PLACE_KEYS))
        self.assertEqual(self.place(**{GB.PLACE_SRC_KEY: "g-0000000000"}), dict.fromkeys(GB.PLACE_KEYS))

    def test_mountain_site_gives_site_ref_only(self):
        p = self.place(mountain_site="乗鞍岳(剣ヶ峰)")
        self.assertEqual(p["site_ref"], "yamabiyori:m041")
        self.assertIsNone(p["lat"])                                    # 山の座標を名所の座標にしない
        self.assertIsNone(p["place_id"])


class MergedCandidates(unittest.TestCase):
    def setUp(self):
        self.c = GB.cfg()

    def run_merge(self, pre):
        cands = [{"name": "A", "merged_from": ["B"], GB.PLACE_SRC_KEY: "x"}]
        merges = [{"name": "A", "merged_from": ["B"]}]
        GB.attach_place_fields(cands, merges, pre, self.c)
        return cands[0], merges[0]

    def p(self, pid=None, lat=None, ref=None):
        return {"place_id": pid, "lat": lat, "lon": lat, "coord_source": "catalog" if lat is not None else None, "site_ref": ref}

    def test_one_side_has_id(self):
        r, m = self.run_merge({"A": self.p(), "B": self.p("ikimonobiyori:k1", 35.0)})
        self.assertEqual((r["place_id"], r["lat"], m["place_from"]), ("ikimonobiyori:k1", 35.0, "B"))
        self.assertNotIn(GB.PLACE_SRC_KEY, r)
        self.assertNotIn("place_conflict", m)

    def test_ids_disagree(self):
        r, m = self.run_merge({"A": self.p("ikimonobiyori:k1", 35.0), "B": self.p("ikimonobiyori:k2", 36.0)})
        self.assertEqual({k: r[k] for k in GB.PLACE_KEYS}, dict.fromkeys(GB.PLACE_KEYS))
        self.assertIsNone(m["place_from"])
        self.assertEqual([x["place_id"] for x in m["place_conflict"]["members"]], ["ikimonobiyori:k1", "ikimonobiyori:k2"])
        self.assertEqual(m["place_conflict"]["reason"], self.c["concierge_fields"]["merge_conflict_reason"])

    def test_same_id_and_site_ref_from_other(self):
        r, m = self.run_merge({"A": self.p("ikimonobiyori:k1", 35.0), "B": self.p(ref="yamabiyori:m001")})
        self.assertEqual((r["place_id"], r["site_ref"], m["place_from"]), ("ikimonobiyori:k1", "yamabiyori:m001", "A"))


def fake_git(cmd, head, status, top=None):
    if "--show-toplevel" in cmd:
        return (top or str(H.ROOT)) + "\n"
    return head + "\n" if "rev-parse" in cmd else status


class Generator(unittest.TestCase):
    def test_id_and_content_do_not_depend_on_generator(self):
        with mock.patch.object(GB, "_wall_clock", return_value=datetime(2026, 11, 27, 21, 0, 1, tzinfo=JST)), \
                mock.patch.object(GB, "_git_state", return_value=("a" * 40, False)):
            a = GB.build("今週末、高尾山で紅葉を見たい", now=NOW)
        with mock.patch.object(GB, "_wall_clock", return_value=datetime(2026, 11, 28, 6, 0, 0, tzinfo=JST)), \
                mock.patch.object(GB, "_git_state", return_value=("a" * 40, False)):
            b = GB.build("今週末、高尾山で紅葉を見たい", now=NOW)
        self.assertEqual(a["generator"], {"name": "ikimonobiyori", "version": __version__, "commit": "a" * 40, "dirty": False,
                                          "generated_at": "2026-11-27T21:00:01+09:00"})
        self.assertEqual(b["generator"]["generated_at"], "2026-11-28T06:00:00+09:00")
        self.assertEqual(a["id"], GB.brief_id("今週末、高尾山で紅葉を見たい", NOW))
        self.assertEqual(a["id"], b["id"])
        strip = lambda d: {k: v for k, v in d.items() if k != "generator"}
        self.assertEqual(strip(a), strip(b))                               # generated_at のほかは同じ資料
        self.assertEqual(list(a)[:3], ["schema", "generator", "id"])

    def test_git_state_reads_commit_and_dirty(self):
        calls = []

        def run(cmd, **kw):
            calls.append((cmd, kw))
            out = fake_git(cmd, "0123456789abcdef0123456789abcdef01234567", " M README.md\n")
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        self.assertEqual(GB._git_state(run=run), ("0123456789abcdef0123456789abcdef01234567", True))
        self.assertTrue(all(isinstance(c, list) and c[0] == "git" and c[2] == str(H.ROOT / "ikimonobiyori") for c, _ in calls))   # 引数の配列・パッケージのフォルダから
        self.assertTrue(all(kw.get("timeout") for _, kw in calls))
        self.assertTrue(all(c[3] == "--no-optional-locks" for c, _ in calls))   # git が索引を書き直さない(書き込み先の決まり)

    def test_git_state_clean_and_failures(self):
        ok = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=fake_git(cmd, "f" * 40, ""), stderr="")
        self.assertEqual(GB._git_state(run=ok), ("f" * 40, False))
        other = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=fake_git(cmd, "f" * 40, "", top=str(H.ROOT / "tests")), stderr="")
        self.assertEqual(GB._git_state(run=other), (None, None))      # パッケージがそのリポジトリの直下にない(実行用のコピーなど)

        def boom(cmd, **kw):
            raise FileNotFoundError("git")
        self.assertEqual(GB._git_state(run=boom), (None, None))
        bad = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal")
        self.assertEqual(GB._git_state(run=bad), (None, None))

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        self.assertEqual(GB._git_state(run=slow), (None, None))

    def test_no_git_call_under_test_by_default(self):
        self.assertEqual(os.environ.get("BIYORI_UNDER_TEST"), "1")
        self.assertEqual(GB._git_state(), (None, None))

    def test_test_clock_uses_now_and_real_clock_otherwise(self):
        self.assertEqual(GB.generator_info(NOW)["generated_at"], NOW.isoformat())        # テスト専用の時計(tests/nonet.py)
        from ikimonobiyori import sources as S
        wall = datetime(2026, 11, 27, 21, 5, 0, tzinfo=JST)
        with mock.patch.dict(os.environ, {"IKIMONOBIYORI_TEST_CLOCK": "0"}), mock.patch.object(S, "clock_now", return_value=wall):
            g = GB.generator_info(NOW)
        self.assertEqual(g["generated_at"], wall.isoformat())                           # ふだんはパソコンの時計(now とは別)

    def test_generator_without_git(self):
        with mock.patch.object(GB, "_git_state", return_value=(None, None)):
            g = GB.generator_info()
        self.assertEqual((g["commit"], g["dirty"], g["version"]), (None, None, __version__))
        self.assertRegex(g["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
