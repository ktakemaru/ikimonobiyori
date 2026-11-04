"""段階47(指示書 docs/stage47-sources-instructions.md): 通信なし。
- tenki.jp は答えの材料に出ない(記録できない・既にある記録も読まない・リポジトリのデータに残らない)。
- 状態を持つ記録は、「状態の記載なし」の新しい記録に隠されない。
- 神奈川県の公式の現況(かながわパークレンジャー)が公式の台帳にある。"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O
from ikimonobiyori import sources

ROOT = Path(__file__).resolve().parent.parent / "ikimonobiyori"
POLICY = O.load_policy()


def rec(**over):
    r = {"subject": "autumn_leaves", "name": "テスト園", "city": "テスト市", "state": "色づき始め", "state_date": "2026-11-03",
         "url": "https://example.test/a", "publisher": "テスト", "source_class": "secondary"}
    r.update(over)
    return r


class Tenki(unittest.TestCase):
    def test_record_rejects_tenki(self):
        self.assertTrue(O.validate(rec(url="https://tenki.jp/kouyou/3/17/"), POLICY))
        self.assertTrue(O.validate(rec(url="https://www.tenki.jp/x"), POLICY))
        self.assertFalse(O.validate(rec(), POLICY))

    def test_existing_tenki_rows_are_not_read(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            p = O.log_path("autumn_leaves", env, POLICY)
            p.parent.mkdir(parents=True)
            old = {"subject": "autumn_leaves", "name": "A", "city": "B", "state": "色づき始め", "state_date": "2026-11-03", "url": "https://tenki.jp/kouyou/3/17/",
                   "publisher": "tenki.jp", "source_class": "secondary", "host": "tenki.jp", "read_at": "2026-11-04T10:00:00+09:00"}
            ok = dict(old, url="https://example.test/a", host="example.test", publisher="テスト")
            p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in (old, ok)) + "\n", encoding="utf-8")
            rows = O.read_records("autumn_leaves", env, POLICY)
            self.assertEqual([r["host"] for r in rows], ["example.test"])

    def test_no_tenki_in_committed_data(self):
        for rel in ("data/observations/spots.yaml", "data/guide/records.jsonl", "data/guide/seed_map.yaml"):
            self.assertNotIn("//tenki.jp", (ROOT / rel).read_text(encoding="utf-8"), rel)
        cat = (ROOT / "data/guide/catalog.yaml").read_text(encoding="utf-8")
        self.assertNotIn("host: tenki.jp", cat)


class BestRecord(unittest.TestCase):
    def row(self, state, d, read_at):
        r = {"state": state, "state_date": d, "read_at": read_at, "source_class": "official"}
        r["state_norm"] = O.normalize("autumn_leaves", state, POLICY)
        return r

    def test_stateful_record_is_not_hidden_by_newer_no_state_record(self):
        a = self.row("日本庭園・カエデ類 色づき始め", "2026-11-03", "2026-11-04T09:00:00+09:00")
        b = self.row("紅葉の状態の記載なし", "2026-11-04", "2026-11-04T12:00:00+09:00")
        self.assertIs(O.best_record([a, b]), a)
        self.assertIs(O.best_record([b, a]), a)

    def test_only_no_state_records_still_returns_one(self):
        b = self.row("紅葉の状態の記載なし", "2026-11-04", "2026-11-04T12:00:00+09:00")
        self.assertIs(O.best_record([b]), b)

    def test_newest_stateful_still_wins(self):
        a = self.row("色づき始め", "2026-11-01", "2026-11-01T09:00:00+09:00")
        b = self.row("見ごろ", "2026-11-03", "2026-11-03T09:00:00+09:00")
        self.assertIs(O.best_record([a, b]), b)


class Ledger(unittest.TestCase):
    def test_kanagawa_parkranger_is_official_and_approved(self):
        reg = {s["id"]: s for s in sources.load_registry("autumn_leaves")["sources"]}
        s = reg["kanagawa-parkranger-koyo"]
        self.assertEqual(s["approval"]["status"], "approved")
        self.assertIn("pref.kanagawa.jp", s["url"])

    def test_tenki_is_not_a_read_target(self):
        sec = {s["id"]: s for s in sources.load_secondary_registry("autumn_leaves")["sources"]}
        self.assertNotEqual(sec["tenki-kouyou-kanagawa"]["approval"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
