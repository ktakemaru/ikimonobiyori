"""山の名前を挙げた質問の仕上げ(指示書 docs/mountain-named-2-instructions.md。2026-11-28)。通信しない。
第 2 部: 足した候補が今年の現況・例年の時期の事実を連れてこなかったときは「調べる」を残す。
第 3 部: 資料の asked_mountain と、Markdown の先頭の「聞かれた山の名所」の節。"""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
Q = {"tsukuba": "今週末、筑波山で紅葉を見たい", "mitake": "御岳山の紅葉はどう?", "mitake_plan": "今週末、御岳山で紅葉を見たい",
     "jinba": "陣馬山の紅葉はどう?", "oyama": "今週末、大山で紅葉を見たい", "kiri_hana": "霧ヶ峰の花の見どころを教えて",
     "takao": "今週末、高尾山で紅葉を見たい", "mitake_all": "御岳山の見どころを教えて", "plain": "今週末の紅葉の情報は?"}
RESEARCH = "調べる: 「{}」の名所・カード・事実がない"

_ORIG_CFG = GB.cfg


def _off():
    c = copy.deepcopy(_ORIG_CFG())
    c["mountain_named_candidates"]["enabled"] = False
    return c


class MountainNamed2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-mountain-named-2-")
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        GB._HOSTS = None
        cls.on = {k: GB.build(q, now=NOW) for k, q in Q.items()}
        with mock.patch.object(GB, "cfg", _off):
            cls.off = {k: GB.build(q, now=NOW) for k, q in Q.items()}
            cls.off_md = {k: GB.render_md(d) for k, d in cls.off.items()}
        cls.md = {k: GB.render_md(d) for k, d in cls.on.items()}
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    # 第 2 部
    def test_research_kept_when_no_fact_was_brought(self):
        for k in ("mitake", "mitake_plan"):
            self.assertIn(RESEARCH.format("御岳山"), self.on[k]["missing"], k)
            self.assertEqual(self.on[k]["missing"], self.off[k]["missing"], k)          # 足す前と同じ形
            self.assertEqual(self.on[k]["research"], self.off[k]["research"], k)

    def test_research_gone_when_facts_were_brought(self):
        for k, name in (("tsukuba", "筑波山"), ("jinba", "陣馬山"), ("oyama", "大山")):
            self.assertIn(RESEARCH.format(name), self.off[k]["missing"], k)
            self.assertNotIn(RESEARCH.format(name), self.on[k]["missing"], k)

    def test_cands_for_needs(self):
        c = GB.cfg()
        M = c["mountain_named_candidates"]
        r = {"name": "試験の山", M["mark_key"]: M["mark_value"]}
        plain = {"name": "試験の庭"}
        self.assertEqual(GB._cands_for_needs([plain, r], [], c), [plain])
        self.assertEqual(GB._cands_for_needs([plain, r], [{"place": "試験の山", "kind": "typical"}], c), [plain, r])
        self.assertEqual(GB._cands_for_needs([plain, r], [{"place": "試験の山", "kind": "event"}], c), [plain])   # 現況・例年の時期のほかは数えない

    # 第 3 部
    def test_asked_mountain_present_only_when_added(self):
        for k in Q:
            self.assertIn("asked_mountain", self.on[k], k)
            self.assertIsNone(self.off[k]["asked_mountain"], k)
        for k in ("takao", "mitake_all", "plain"):
            self.assertIsNone(self.on[k]["asked_mountain"], k)

    def test_asked_mountain_points_to_existing_values(self):
        for k, ref in (("tsukuba", "m057"), ("mitake", "m031"), ("oyama", "m027"), ("kiri_hana", "m043")):
            am = self.on[k]["asked_mountain"]
            self.assertEqual(am["site_ref"], f"yamabiyori:{ref}", k)
            self.assertTrue(am["name"], k)
            rows = {r["name"]: r for r in self.on[k]["candidates"]}
            fids = {f["id"] for f in self.on[k]["facts"]}
            for x in am["candidates"]:
                self.assertIn(x["name"], rows, k)
                self.assertEqual(x["outlook"], rows[x["name"]].get("outlook"), k)
                self.assertLessEqual(set(x["facts"]), fids, k)
        self.assertEqual(self.on["mitake"]["asked_mountain"]["candidates"][0]["facts"], [])
        self.assertTrue(self.on["tsukuba"]["asked_mountain"]["candidates"][0]["facts"])

    def test_section_before_candidates(self):
        A = GB.cfg()["mountain_named_candidates"]["asked_section"]
        for k in ("tsukuba", "mitake", "oyama", "kiri_hana"):
            md = self.md[k]
            self.assertIn(A["heading"], md, k)
            self.assertIn(A["lead"], md, k)
            sec = md.index(A["heading"])
            self.assertLess(sec, md.index("## 候補と順位"), k)
            body = md[sec:md.index("## 候補と順位")].splitlines()
            cand_lines = [ln for ln in body if ln and ln != A["heading"] and ln != A["lead"]]
            self.assertTrue(cand_lines, k)
            for ln in cand_lines:                                       # 候補の一覧・事実の一覧と同じ行(そのまま)
                self.assertGreaterEqual(md.count(ln), 2, (k, ln))

    def test_no_section_without_asked_mountain(self):
        A = GB.cfg()["mountain_named_candidates"]["asked_section"]
        for k in ("takao", "mitake_all", "plain"):
            self.assertNotIn(A["heading"], self.md[k], k)
            self.assertEqual(self.md[k], self.off_md[k], k)

    def test_candidates_unchanged_by_section(self):
        for k in Q:
            self.assertEqual(json.dumps(self.on[k]["rules"], ensure_ascii=False), json.dumps(self.off[k]["rules"], ensure_ascii=False), k)
            d = dict(self.on[k], asked_mountain=None)
            self.assertNotIn(GB.cfg()["mountain_named_candidates"]["asked_section"]["heading"], GB.render_md(d), k)


if __name__ == "__main__":
    unittest.main()
