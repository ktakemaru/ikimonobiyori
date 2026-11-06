"""段階54: 山と溪谷オンライン掲載情報の取り扱い（第1部）ほか。合成データ・通信しない。"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O, ask_verify as AV

POL = O.load_policy()
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=JST)
URL = "https://www.yamakei-online.com/mt_info/info_detail.php?info_id=9999"      # 合成（実在の記事の文章は使わない）


def rec(**kw):
    base = {"subject": "autumn_leaves", "name": "試験山", "city": "試験市", "state": "紅葉まだほんのり", "state_date": "2026-11-05",
            "url": URL, "publisher": "試験ビジターセンター(山と溪谷オンライン)", "source_class": "secondary"}
    base.update(kw)
    return base


class Restricted(unittest.TestCase):
    def test_short_phrase_passes(self):
        self.assertEqual(O.validate(rec(), POL), [])

    def test_long_or_sentence_rejected(self):
        self.assertTrue(O.validate(rec(state="紅葉は山頂付近で色づき始めていますが麓ではまだ緑が目立ちますが全体としては見頃に向かっています"), POL))
        self.assertTrue(O.validate(rec(state="色づき始め。日没は16時です"), POL))

    def test_safety_sentence_rejected(self):
        for w in ("日没は16時ごろ", "一方通行です", "通行止めあり"):
            self.assertTrue(O.validate(rec(state=w), POL), w)

    def test_forbidden_fields(self):
        self.assertTrue(O.validate(rec(practical="駐車場は満車"), POL))
        self.assertTrue(O.validate(rec(typical="11月上旬"), POL))

    def test_other_hosts_unaffected(self):
        r = rec(url="https://example.org/a", state="x" * 60, source_class="official")
        self.assertEqual(O.validate(r, POL), [])

    def test_pending_source_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "IKIMONOBIYORI_DATA_DIR": d}
            out = O.record([rec()], env=env, policy=POL, now=NOW)
            self.assertEqual(len(out["written"]) if isinstance(out["written"], list) else out["written"], 1)
            self.assertEqual(O.read_records("autumn_leaves", env=env, policy=POL), [])          # 承認待ちの間は材料にしない
            approved = json.loads(json.dumps(POL))
            approved["record"]["restricted_sources"]["approved"] = True
            self.assertEqual(len(O.read_records("autumn_leaves", env=env, policy=approved)), 1)

    def test_stored_record_has_only_phrase_date_url(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "IKIMONOBIYORI_DATA_DIR": d}
            r = rec(state="紅葉まだほんのり")
            O.record([r], env=env, policy=POL, now=NOW)
            row = json.loads(open(O.log_path("autumn_leaves", env, POL), encoding="utf-8").readline())
            self.assertEqual(row["state"], "紅葉まだほんのり")
            self.assertNotIn("practical", row)

    def test_verifier_flags_long_restricted_fact(self):
        facts = {"subjects": {"autumn_leaves": {"subject": "autumn_leaves", "candidates": [
            {"name": "試験山", "current": {"state": "見頃", "state_raw": "あ" * 40, "url": URL}}]}}}
        self.assertTrue(AV.restricted_source_errors(facts))
        facts["subjects"]["autumn_leaves"]["candidates"][0]["current"]["state_raw"] = "紅葉まだほんのり"
        self.assertEqual(AV.restricted_source_errors(facts), [])


if __name__ == "__main__":
    unittest.main()
