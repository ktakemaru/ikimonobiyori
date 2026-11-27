"""山の名前を挙げた質問で、その山の名所を候補に入れる(指示書 docs/mountain-named-instructions.md。2026-11-28)。通信しない。
今ある候補は外さず順番も変えない・対象の合わない名所は入れない・対象を絞らない質問には入れない・設定で切ると直す前と同じ資料。"""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from jsonschema import Draft202012Validator

from ikimonobiyori import guide_brief as GB

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
SCHEMA = json.loads((H.ROOT / "ikimonobiyori" / "schemas" / "guide-brief.schema.json").read_text(encoding="utf-8"))
Q = {"tsukuba": "今週末、筑波山で紅葉を見たい", "mitake": "御岳山の紅葉はどう?", "oyama": "今週末、大山で紅葉を見たい",
     "kiri_hana": "霧ヶ峰の花の見どころを教えて", "kiri_kouyou": "今週末、霧ヶ峰で紅葉を見たい", "takao": "今週末、高尾山で紅葉を見たい",
     "takao_all": "高尾山の見どころを教えて", "mitake_all": "御岳山の見どころを教えて", "plain": "今週末の紅葉の情報は?"}


_ORIG_CFG = GB.cfg


def _off():
    c = copy.deepcopy(_ORIG_CFG())
    c["mountain_named_candidates"]["enabled"] = False
    return c


def strip(d):
    d = dict(d)
    d.pop("generator", None)
    return json.dumps(d, ensure_ascii=False, indent=1)


class MountainNamed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-mountain-named-")
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        GB._HOSTS = None
        cls.on = {k: GB.build(q, now=NOW) for k, q in Q.items()}
        with mock.patch.object(GB, "cfg", _off):
            cls.off = {k: GB.build(q, now=NOW) for k, q in Q.items()}
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def added(self, k):
        M = GB.cfg()["mountain_named_candidates"]
        return [r for r in self.on[k]["candidates"] if r.get(M["mark_key"]) == M["mark_value"]]

    def test_asked_mountains_uses_sites_names(self):
        ix = GB._place_index()
        self.assertEqual(GB._asked_mountains("今週末、筑波山で紅葉を見たい", ix), ["yamabiyori:m057"])    # 括弧の前の部分(筑波山(女体山))
        self.assertEqual(GB._asked_mountains("大山の紅葉はどう?", ix), ["yamabiyori:m027"])
        self.assertEqual(GB._asked_mountains("筑波山から紅葉を見に行きたい", ix), [])                        # 出発地として挙げた名前は除く
        self.assertEqual(GB._asked_mountains("丹沢で今咲いている花は?", ix), [])                            # sites.yaml の名前でない地名(丹沢山とは別)

    def test_linked_mountain_is_added_at_the_end(self):
        for k, ref in (("tsukuba", "m057"), ("mitake", "m031"), ("kiri_hana", "m043")):
            a = self.added(k)
            self.assertEqual(len(a), 1, k)
            self.assertEqual(a[0]["mountain_site_ref"], f"yamabiyori:{ref}", k)
            self.assertIs(self.on[k]["candidates"][-1], a[0], k)          # 末尾に足す

    def test_existing_candidates_are_kept_in_order(self):
        for k in Q:
            before = [(r["name"], r["rank"], r["basis"]) for r in self.off[k]["candidates"]]
            after = [(r["name"], r["rank"], r["basis"]) for r in self.on[k]["candidates"]]
            self.assertEqual(after[: len(before)], before, k)
            self.assertLessEqual(len(after) - len(before), 1, k)

    def test_ranked_row_is_the_plan_row(self):
        r = self.added("tsukuba")[0]
        self.assertEqual((r["place_id"], r["basis"], r["subject"]), ("ikimonobiyori:kouyou-0015", "typical", "autumn_leaves"))
        self.assertIsInstance(r["rank"], int)
        self.assertGreater(r["rank"], GB.cfg()["max_candidates"])           # 計画の順位(上限より下)のまま。順位を作らない
        self.assertTrue(r["outlook"])

    def test_oyama_through_catalog_ref(self):
        r = self.added("oyama")
        self.assertEqual([x["place_id"] for x in r], ["ikimonobiyori:obs-kouyou-0019"])    # catalog_ref 先 kouyou-0020 が m027
        self.assertIsNone(r[0]["mountain_site_ref"])                        # 観察の名所に mountain_site_ref は書いていない(第 1 部は取り消し)

    def test_town_row_for_highlights(self):
        r = self.added("kiri_hana")[0]
        self.assertEqual((r["basis"], r["place_id"]), ("town", "ikimonobiyori:hana-0037"))
        self.assertIsNone(r["rank"])

    def test_not_added(self):
        for k in ("kiri_kouyou", "takao", "takao_all", "mitake_all", "plain"):
            self.assertEqual(self.added(k), [], k)                          # 対象の合わない・もう候補にある・対象を絞らない・山の名前が無い
            self.assertEqual(strip(self.on[k]), strip(self.off[k]), k)

    def test_takao_once(self):
        names = [r["name"] for r in self.on["takao"]["candidates"]]
        self.assertEqual(names.count("高尾山"), 1)

    def test_off_is_the_same_as_before_for_unchanged_parts(self):
        for k in Q:
            self.assertNotIn(GB.cfg()["mountain_named_candidates"]["mark_key"], json.dumps(self.off[k], ensure_ascii=False), k)

    def test_markdown_has_no_mark(self):
        M = GB.cfg()["mountain_named_candidates"]
        for k in Q:
            md = GB.render_md(self.on[k])
            self.assertNotIn(M["mark_key"], md, k)
            self.assertNotIn("yamabiyori", md, k)

    def test_schema(self):
        for k, d in self.on.items():
            self.assertEqual([e.message for e in Draft202012Validator(SCHEMA).iter_errors(d)], [], k)


if __name__ == "__main__":
    unittest.main()
