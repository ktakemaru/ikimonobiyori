"""段階54 第9部: 回帰テストの基盤（通信しない・約5秒）。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import regress


class Regress(unittest.TestCase):
    def test_all_cases_behave_as_expected(self):
        res = regress.run_all()
        bad = [r for r in res if not r["ok"]]
        self.assertEqual(bad, [], bad)
        self.assertGreaterEqual(len(res), 20)

    def test_every_known_defect_has_a_case(self):
        doc = regress.load_cases()
        want = {"work_report", "lead_mismatch", "source_missing", "date_range", "blocked_source", "assertive_forecast", "weekday_mismatch", "pending_source"}
        got = {c for case in doc["cases"] for c in case.get("expect_fail", [])}
        self.assertTrue(want <= got, want - got)

    def test_a_bad_answer_labelled_ok_is_caught(self):
        doc = regress.load_cases()
        case = dict(next(c for c in doc["cases"] if c["id"] == "defect-date-range"), expect="ok")
        case.pop("expect_fail")
        self.assertFalse(regress.run_case(case, regress.policy_words())["ok"])


if __name__ == "__main__":
    unittest.main()
