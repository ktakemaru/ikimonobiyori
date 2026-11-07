"""段階48 第1部: 答えの組み立て(狙い別・結論が先・見込みは根拠つき)の手順がスキルと AGENTS.md・CLAUDE.md にあり、
その形の答え(合成)が generic 検査を通る。通信しない。"""
import unittest
from pathlib import Path

import helpers as H  # noqa: F401

from ikimonobiyori import ask_verify

ROOT = Path(__file__).resolve().parent.parent

SAMPLE = """週末は、色づき始めの庭園で秋の入口を楽しめそうです。
今回のおすすめは3つです。
## 近場で手軽に
1. 昭和記念公園 日本庭園 — 色づき始め(11/3時点、ウォーカープラスなど公式ではありません)。見頃予測は11月中旬で、週末はまだ序盤の見込みです。
## 絶景を狙う
2. 箱根 — 色づき始め(10/29〜11/3時点)。駐車場の混雑は確認できていません。
## 歩いて楽しむ
3. 大山 — 見ごろから色づき始め(10/18時点、神奈川県)。10/18の記録なので古い情報です。
出典: https://example.test/a
"""


class AnswerComposition(unittest.TestCase):
    def test_procedure_text_in_all_three_places(self):
        for p in (".claude/skills/ikimono-weekend/SKILL.md", "AGENTS.md", "CLAUDE.md"):
            s = (ROOT / p).read_text(encoding="utf-8")
            for needle in ("答えの組み立て(段階48", "狙い別の節", "今週末の見込み", "確認できていません"):
                self.assertIn(needle, s, p)

    def test_composed_sample_passes_generic_check(self):
        r = ask_verify.generic_check(SAMPLE)
        self.assertTrue(r["ok"], r["errors"])
        self.assertGreaterEqual(r["candidates"], 3)


if __name__ == "__main__":
    unittest.main()
