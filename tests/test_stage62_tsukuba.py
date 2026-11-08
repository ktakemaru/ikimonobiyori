"""段階62 第7部: 筑波実験植物園(名所カタログ・座標つき・候補)と「今週のみごろ」の情報源(承認待ち)。通信なし。"""
import unittest
from pathlib import Path

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O

ROOT = Path(__file__).resolve().parents[1]
URL = "https://tbg.kahaku.go.jp/migoro-event/syokubutsu/index.html"


class Tsukuba(unittest.TestCase):
    def test_catalog_entry_with_confirmed_point_and_no_approval(self):
        doc = yaml.safe_load((ROOT / "ikimonobiyori/data/catalog/flowers.yaml").read_text(encoding="utf-8"))
        e = next(x for x in doc["entries"] if x["name"] == "筑波実験植物園")
        self.assertEqual(e["point"], {"lat": 36.1014, "lon": 140.112, "elevation_m": None})
        self.assertEqual((e["status"], e["tags"]["city"], e["tags"]["prefecture"]), ("candidate", "つくば市", "茨城県"))
        self.assertNotIn("approved_by", e)
        self.assertIn("通年", e["flower_windows"][0]["note"])
        self.assertIn("Q3162410", e["tags"]["source"])

    def test_source_is_pending_and_records_are_gated(self):
        s = next(x for x in O.load_policy()["record"]["pending_sources"] if x["id"] == "tbg-kahaku-migoro")
        self.assertEqual(s["approval"]["status"], "pending")
        self.assertEqual((s["url"], s["subject"], s["site_candidate"]), (URL, "flowers", "hana-0041"))
        self.assertIn("許可なく複製", s["terms"])
        self.assertEqual(O.ledger_status_of(URL), "pending")
        rec = {"url": URL, "source_class": "official", "state": "見ごろ"}
        self.assertTrue(O._ledger_gated(rec, "flowers", O.load_policy()))          # 承認されるまで答えの材料にしない


if __name__ == "__main__":
    unittest.main()
