"""段階27: ガイド型の答えをコードの出力で完結させる(フェーズA)・野鳥の既定の時期(フェーズB)・野鳥の現況の読み方(フェーズC)。
通信なし。実データはリポジトリの写し(committed)だけを読む。"""
import re
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from test_stage23 import P, item, recs, build

WINTER = {"text": "11月〜2月", "from": "11月", "to": "2月末"}
BIRD_THEMES = ("野鳥", "冬鳥")
ROOT = Path(__file__).resolve().parent.parent
DATES = [date(2026, 10, 30), date(2026, 1, 15), date(2026, 5, 10), date(2026, 8, 1)]


def committed_found(theme_word, on):
    themes = guide.theme_of(theme_word, P)["themes"]
    return guide.find(guide.committed_entries(), themes=set(themes), on=on, policy=P), set(themes)


def place_lines(text):
    """答えの本文から、名所の行(「1. **名** …」「- 名 …」)の名前だけを取り出す。"""
    out = []
    for ln in text.splitlines():
        m = re.match(r"^\d+\. \*\*(.+?)\*\*\(", ln) or re.match(r"^- (.+)\([^()]*\) — ", ln)
        if m:
            out.append(m.group(1))
    return out


class WholeAnswerFromCode(unittest.TestCase):
    """フェーズA: 定評の名所は、どの日でも欄のどこかに必ず 1 回出る。種名は表示してよいものだけ。凡例は 1 回。"""

    def test_every_curated_bird_place_appears_exactly_once(self):
        entries = [e for e in guide.committed_entries()
                   if e["theme"] in BIRD_THEMES and e.get("scope", "place") == "place" and e["tier"] == "curated"
                   and e["range"]["status"] != "out_of_range" and (e["range"].get("by_origin") or {}).get("横浜", {}).get("status") != "out_of_range"]
        self.assertGreater(len(entries), 20)
        for on in DATES:
            found, themes = committed_found("野鳥", on)
            text = guide.render_answer(found, P, themes=themes)
            names = place_lines(text)
            for e in entries:
                self.assertEqual(names.count(e["name"]), 1, f"{on} {e['name']}")

    def test_species_in_the_text_are_only_the_ones_the_catalog_allows(self):
        found, themes = committed_found("野鳥", date(2026, 10, 30))
        text = guide.render_answer(found, P, themes=themes)
        rows = {ln for ln in text.splitlines() if " — " in ln}
        checked = 0
        for key in ("recommend", "upcoming", "other_season", "no_season", "reference"):
            for e in found[key]:
                line = next(r for r in rows if e["name"] in r.split(" — ")[0])
                after = line.split(" — ", 1)[1]
                m = re.search(r"種類: ([^、]+)", after)
                said = set(m.group(1).split("・")) if m else set()
                for k in e["kinds"]:
                    checked += 1
                    if k["shown"]:
                        self.assertIn(k["kind"], said, e["name"])
                    else:
                        self.assertNotIn(k["kind"], said, f"{e['name']} {k['kind']}")
        self.assertGreater(checked, 5)

    def test_species_are_hidden_with_one_source_and_shown_with_two(self):
        rows = recs(item("https://rurubu.jp/andmore/spot/1", name="試験の沼", theme="野鳥", kinds=["カワセミ"]),
                    item("https://www.walkerplus.com/article/1/", name="試験の沼", theme="野鳥", kinds=["カワセミ", "ヤマセミ"]))
        e = build(rows)["試験の沼"]
        text = guide.render_answer({"recommend": [e]}, P)
        self.assertIn("カワセミ", text)
        self.assertNotIn("ヤマセミ", text)

    def test_single_legend_and_a_care_note_before_it(self):
        found, themes = committed_found("野鳥", date(2026, 10, 30))
        text = guide.render_answer(found, P, themes=themes)
        legend = P["reference_count"]["legend"]
        self.assertEqual(text.count(legend), 1)
        self.assertTrue(text.rstrip().endswith(legend))
        notes = text.split(f"## {P['answer']['headings']['notes']}\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual(len(notes), 2)                                   # 野鳥と冬鳥の 1 行ずつ(注意は 2 行まで)
        self.assertEqual(guide.forbidden_in_answer(text, P), [])

    def test_care_note_comes_from_the_profile_and_drops_the_source_remark(self):
        lines = guide.care_notes({"冬鳥"}, P, profiles={"wintering_birds": {"care": {"manners": ["餌を与えない(館林市の情報)", "静かに観察する", "三つ目は出さない"]}}})
        self.assertEqual(len(lines), 1)
        self.assertIn("餌を与えない。静かに観察する。", lines[0])
        self.assertNotIn("館林", lines[0])
        self.assertNotIn("三つ目", lines[0])
        self.assertEqual(guide.care_notes({"桜"}, P, profiles={}), [])     # 対応するプロファイルがないテーマは出さない

    def test_other_season_and_out_of_range_are_not_dropped(self):
        rows = recs(item("https://rurubu.jp/andmore/spot/1", name="試験の沼", theme="冬鳥", season=WINTER),
                    item("https://www.walkerplus.com/article/1/", name="試験の沼", theme="冬鳥", season=WINTER))
        e = build(rows)["試験の沼"]
        text = guide.render_answer({"recommend": [], "other_season": [e], "out_of_range": [e]}, P)
        self.assertIn(P["answer"]["headings"]["other_season"], text)
        self.assertNotIn(P["answer"]["headings"]["out_of_range"], text)    # 範囲の外は名指しのときだけ
        text = guide.render_answer({"recommend": [], "out_of_range": [e]}, P, show_out_of_range=True)
        self.assertIn(P["answer"]["headings"]["out_of_range"], text)

    def test_the_rule_is_in_the_skill_and_both_agent_files(self):
        for p in (".claude/skills/ikimono-weekend/SKILL.md", "AGENTS.md", "CLAUDE.md"):
            s = (ROOT / p).read_text(encoding="utf-8")
            self.assertIn("一字一句そのまま出す", s, p)


if __name__ == "__main__":
    unittest.main()
