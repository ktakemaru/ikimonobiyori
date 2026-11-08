"""段階67: 段階65・66の判断の反映(承認欄 A〜G)・答えの細かな崩れ・山のカードの答え。合成データ(通信しない)。"""
import unittest

import nonet  # noqa: F401  (通信を禁じる)

from ikimonobiyori import sources


class Part1ApprovalsB_E(unittest.TestCase):
    """承認欄 B・E(本人の判断 2026-11-09)。承認済みの id を明示して確かめる。"""

    def test_showakinen_sources_and_host_are_approved_by_the_user(self):
        from ikimonobiyori import regional
        for subj, sid in (("autumn_leaves", "showakinen-flower-information"), ("flowers", "showakinen-flower-information-flowers")):
            src = next(s for s in sources.load_registry(subj)["sources"] if s["id"] == sid)
            ap = src["approval"]
            self.assertEqual((ap["status"], ap["approved_by"], ap["approved_on"]), ("approved", "user", "2026-11-09"), sid)
            self.assertIn("本人の指示による記入", ap["reason"])
            self.assertIn("状態の語(30字以内)・日付・URL だけ", ap["reason"])
            self.assertEqual((src["readable"]["status"], src["readable"]["robots"], src["terms"]["status"]), ("ok", "allows", "no_prohibition_found"), sid)
        self.assertIn("showakinen-koen.jp", regional.load_policy()["approved_hosts"]["hosts"])

    def test_okutama_and_oze_are_approved_without_species(self):
        from ikimonobiyori import visitor_centers as V
        cs = {c["id"]: c for c in V.load_centers()}
        for i in ("okutama-vc", "oze-fnd"):
            ap = cs[i]["approval"]
            self.assertEqual((ap["status"], ap["approved_by"], ap["approved_on"]), ("approved", "user", "2026-11-09"), i)
            self.assertEqual(V.allowed_fields(cs[i]), ["state", "date", "url", "hours"], i)
            self.assertEqual(V.validate_center(cs[i]), [], i)


if __name__ == "__main__":
    unittest.main()
