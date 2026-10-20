"""提案の出力が変わらないこと(ゴールデン。tests/golden.py に記録の経緯と比較の規則)。通信なし。
G4 は adapter と同じ形の子プロセス(main.py --cache-only)で、書き込み先を環境変数 IKIMONOBIYORI_DATA_DIR で渡す経路と --cache-dir の経路の両方。"""
import unittest

import golden as G
import helpers as H
from helpers import ROOT, run_child_env


class Golden(unittest.TestCase):
    GOLD = G.load_golden()

    def check(self, docs):
        for name, doc in docs.items():
            with self.subTest(name=name):
                self.assertIn(name, self.GOLD)
                self.assertIsNone(G.diff(self.GOLD[name], doc))

    def test_the_golden_set_is_complete(self):
        self.assertEqual(sorted(self.GOLD), ["g1_synthetic_autumn", "g1_synthetic_birds", "g1_synthetic_both", "g2_recorded_autumn",
                                             "g4_child_autumn_leaves", "g4_child_birds", "g4_composed"])
        self.assertEqual(len(self.GOLD["g1_synthetic_both"]["proposals"]), 16)

    def test_goldens_are_valid_proposals(self):
        for name, doc in self.GOLD.items():
            with self.subTest(name=name):
                self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])

    def test_g1_g2_in_process(self):
        self.check(G.build_inproc())

    def launch(self, cmd, extra):
        r = run_child_env(cmd, extra, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.returncode

    def test_g4_child_process_with_the_data_dir_env(self):
        self.check(G.build_g4(self.launch, data_dir_env=True))

    def test_g4_child_process_with_an_explicit_cache_dir(self):
        self.check(G.build_g4(self.launch))


if __name__ == "__main__":
    unittest.main()
