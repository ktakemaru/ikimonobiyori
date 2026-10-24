"""段階19: 推定の座標で足した地点は使わない。座標未確認の地点は下書き(candidate)のまま、承認済みのカタログに入れない。通信なし。"""
import unittest

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, paths, sources

DRAFT_IDS = [f"kouyou-{i:04d}" for i in range(36, 62)]          # 0036〜0055(推定で足して戻した 20 地点)と 0056〜0061
DRAFTS = {e["id"]: e for e in yaml.safe_load((paths.CATALOG_DIR / "drafts" / "autumn_leaves.yaml").read_text(encoding="utf-8"))["entries"]}
CAT = {e["id"]: e for e in catalog.approved_entries(catalog.load_catalog("autumn_leaves"))}


class Unconfirmed(unittest.TestCase):
    def test_unconfirmed_places_are_candidates_without_a_point(self):
        for i in DRAFT_IDS:
            if i in CAT:                                         # 公式ページの地図の埋め込みの座標を確認できて承認した地点(後述のテスト)
                continue
            self.assertEqual((DRAFTS[i]["status"], "point" in DRAFTS[i]), ("candidate", False), i)

    def test_no_approved_entry_uses_an_estimated_point(self):
        for i, e in CAT.items():
            if i in DRAFT_IDS:
                self.assertIn("公式ページの地図の埋め込み", e["tags"]["source"], i)


if __name__ == "__main__":
    unittest.main()
