"""段階62 第9部: 閉館した施設・不採用の情報源・作り直したカード。通信なし・合成データ。"""
import unittest
from datetime import date
from pathlib import Path

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as AV
from ikimonobiyori import knowledge as K
from ikimonobiyori import observations as O
from ikimonobiyori import visitor_centers as VC

ROOT = Path(__file__).resolve().parents[1]


class Miyagase(unittest.TestCase):
    def test_closed_center_is_kept_but_not_used_even_if_approved(self):
        c = next(x for x in VC.load_centers() if x["id"] == "miyagase-vc")
        self.assertEqual(c["closed"]["date"], "2016-03-31")
        self.assertEqual(c["approval"]["status"], "pending")                     # 承認の状態は変えていない
        self.assertEqual(VC.usable_center(dict(c, approval={"status": "approved", "approved_by": "user"}), date(2026, 11, 8)), (False, "closed"))


class BirdResearch(unittest.TestCase):
    def test_rejected_and_blocked(self):
        doc = yaml.safe_load((ROOT / "ikimonobiyori/data/sources/secondary/birds.yaml").read_text(encoding="utf-8"))
        s = next(x for x in doc["sources"] if x["id"] == "bird-research-season-front")
        self.assertTrue(s["note"].startswith("不採用(本人の判断 2026-11-08)"))
        pol = O.load_policy()
        self.assertTrue(O._blocked_host("www.bird-research.jp", pol))
        self.assertIn("blocked_source", {e["code"] for e in AV.source_rule_errors("出典 https://www.bird-research.jp/?page_id=2209", AV.load_rules())})
        card = {"title": "試験", "category": "季節の仕組み", "place": "試験", "facts": ["試験"], "condition": {}, "rights": "事実のみ", "confidence": "紹介",
                "usage": "ガイドの目", "source": {"name": "バードリサーチ", "url": "https://www.bird-research.jp/?page_id=2209", "checked_on": "2026-11-08"}}
        self.assertTrue(any("使わない" in e for e in K.validate(card)))


class RetiredCards(unittest.TestCase):
    def test_retired_card_is_hidden(self):
        card = {"title": "試験", "confidence": "紹介", "source": {"name": "試験"}, "retired": {"on": "2026-11-08", "reason": "試験"}}
        self.assertEqual(K.usable(card, []), (False, "retired"))
        self.assertTrue(K.usable(dict(card, retired=None), [])[0])


if __name__ == "__main__":
    unittest.main()
