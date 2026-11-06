"""段階56b: 施設ごとの『使う項目』（台帳の allowed_fields）。通信しない。合成データ。
承認（approval.status・approved_by）は触らない。台帳の高尾・御岳ビジターセンターだけ、種名を除く。"""
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as AV
from ikimonobiyori import visitor_centers as V
from test_stage55 import APPR, VP, center, report

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 7)
NAME = "試験自然観察センター"
LINE_ALL = "試験自然観察センター発信、11/5時点: 紅葉が見ごろ（ジョウビタキ・シメ）"
LINE_NO_SPECIES = "試験自然観察センター発信、11/5時点: 紅葉が見ごろ"


class LedgerSetting(unittest.TestCase):
    def test_only_takao_and_mitake_are_restricted_and_without_species(self):
        cs = {c["id"]: c for c in V.load_centers()}
        restricted = {i for i, c in cs.items() if c.get("allowed_fields") is not None}
        self.assertEqual(restricted, {"takao-vc", "mitake-vc"})
        for i in restricted:
            self.assertEqual(V.allowed_fields(cs[i], VP), ["state", "date", "url", "hours"])      # 状態の語・日付・URL・開館時間のみ
            self.assertNotIn("species", V.allowed_fields(cs[i], VP))
            self.assertEqual(V.validate_center(cs[i], VP), [])
        for i, c in cs.items():                                                                   # 既定は全項目（既存の挙動）
            if i not in restricted:
                self.assertEqual(V.allowed_fields(c, VP), VP["fields"], i)
                self.assertFalse(V.restricted(c, VP), i)

    def test_approvals_are_untouched(self):
        for c in V.load_centers():
            self.assertEqual(c["approval"]["status"], "pending", c["id"])            # 承認は本人が行う
            self.assertNotIn("approved_by", c["approval"], c["id"])

    def test_validation_of_allowed_fields(self):
        self.assertEqual(V.validate_center(center(allowed_fields=["state", "date", "url"]), VP), [])
        self.assertTrue(V.validate_center(center(allowed_fields=["state", "date", "url", "story"]), VP))     # 知らない項目
        self.assertTrue(V.validate_center(center(allowed_fields=["state", "species", "url"]), VP))           # date を外せない
        self.assertTrue(V.validate_center(center(allowed_fields=["state", "date"]), VP))                     # url を外せない
        self.assertTrue(V.validate_center(center(allowed_fields="state"), VP))                               # 配列でない


class LineAndRecord(unittest.TestCase):
    def test_default_center_is_unchanged(self):
        c = center(approval=APPR, hours="9:00〜16:30")
        rows = V.fact_rows(TODAY, centers=[c], reports=[report()])
        self.assertEqual(rows[0]["line"], LINE_ALL)
        self.assertEqual(rows[0]["hours_line"], "開館時間・休館日: 9:00〜16:30")
        self.assertNotIn("allowed_fields", rows[0])                                    # 既定の施設の行に印は付かない
        self.assertNotIn("withheld_species", rows[0])

    def test_restricted_center_drops_species_and_keeps_the_rest(self):
        c = center(approval=APPR, hours="9:00〜16:30", allowed_fields=["state", "date", "url", "hours"])
        rows = V.fact_rows(TODAY, centers=[c], reports=[report()])
        self.assertEqual(rows[0]["line"], LINE_NO_SPECIES)
        self.assertEqual(rows[0]["withheld_species"], ["ジョウビタキ", "シメ"])
        self.assertEqual(rows[0]["hours_line"], "開館時間・休館日: 9:00〜16:30")
        self.assertEqual(rows[0]["url"], "https://nature.example.org/news/1")

    def test_hours_can_be_withheld_too(self):
        c = center(approval=APPR, hours="9:00〜16:30", allowed_fields=["state", "date", "url"])
        r = V.fact_rows(TODAY, centers=[c], reports=[report()])[0]
        self.assertIsNone(r["hours"])
        self.assertIsNone(r["hours_line"])
        self.assertEqual(r["withheld_hours"], "9:00〜16:30")

    def test_state_can_be_withheld(self):
        c = center(approval=APPR, allowed_fields=["date", "species", "url"])
        line = V.report_line(c, report(), VP)
        self.assertNotIn("紅葉が見ごろ", line)
        self.assertIn("ジョウビタキ・シメ", line)

    def test_record_rejects_a_field_the_center_does_not_use(self):
        c = center(approval=APPR, allowed_fields=["state", "date", "url", "hours"])
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "IKIMONOBIYORI_DATA_DIR": d}
            out = V.record_reports([report(), report(species=None)], env=env, policy=VP, centers=[c])
            self.assertEqual(out["written"], 1)
            self.assertEqual(len(out["rejected"]), 1)
            self.assertIn("species", out["rejected"][0]["errors"][0])
            self.assertEqual([r.get("species") for r in V.read_reports(env, VP)], [None])


class VerifierEnforcesIt(unittest.TestCase):
    def facts(self, **kw):
        c = center(approval=APPR, hours="9:00〜16:30", **kw)
        return {"visitor_centers": V.fact_rows(TODAY, centers=[c], reports=[report()])}

    def codes(self, text, facts):
        return [e["code"] for e in AV.visitor_center_errors(text, facts)]

    def test_species_in_the_line_of_a_restricted_center_fails(self):
        f = self.facts(allowed_fields=["state", "date", "url", "hours"])
        bad = LINE_ALL + "(https://nature.example.org/news/1)。\n"
        self.assertIn("visitor_center_field_not_allowed", self.codes(bad, f))
        only_name = LINE_NO_SPECIES + "、ジョウビタキが記録されています(https://nature.example.org/news/1)。\n"
        self.assertIn("visitor_center_field_not_allowed", self.codes(only_name, f))             # 括弧がなくても、除いた種名が出たら落とす
        ok = LINE_NO_SPECIES + "(https://nature.example.org/news/1)。開館時間・休館日: 9:00〜16:30。\n"
        self.assertEqual(self.codes(ok, f), [])

    def test_the_default_center_may_still_write_species(self):
        f = self.facts()
        self.assertEqual(self.codes(LINE_ALL + "(https://nature.example.org/news/1)。\n", f), [])

    def test_withheld_hours_fail(self):
        f = self.facts(allowed_fields=["state", "date", "url"])
        self.assertIn("visitor_center_field_not_allowed", self.codes(LINE_NO_SPECIES + "。開館時間・休館日: 9:00〜16:30。\n", f))
        self.assertEqual(self.codes(LINE_NO_SPECIES + "。\n", f), [])

    def test_check_runs_it_in_the_whole_answer_check(self):
        f = {"subjects": {"flowers": {"subject": "flowers", "candidates": []}}, "visitor_centers": self.facts(allowed_fields=["state", "date", "url", "hours"])["visitor_centers"]}
        r = AV.check("今週末は花を見に行けそうです。\n" + LINE_ALL + "(https://nature.example.org/news/1)。\n", f)
        self.assertIn("visitor_center_field_not_allowed", [e["code"] for e in r["answer_errors"]])


class DecodeHtml(unittest.TestCase):
    def test_shift_jis_page_without_a_declaration_is_decoded(self):
        raw = "埼玉県自然学習センター 今週のようす ハクチョウ".encode("cp932")
        text, enc = V.decode_html(raw)
        self.assertEqual((text, enc), ("埼玉県自然学習センター 今週のようす ハクチョウ", "cp932"))
        text, enc = V.decode_html("北本自然観察公園".encode("utf-8"))
        self.assertEqual(enc, "utf-8")
        self.assertEqual(V.decode_html(raw, declared="cp932")[1], "cp932")

    def test_undecodable_bytes_are_not_read_as_if_readable(self):
        with self.assertRaises(ValueError):
            V.decode_html(b"\xff\xfe\xfd\x81", declared=None, fallbacks=("utf-8",))


if __name__ == "__main__":
    unittest.main()
