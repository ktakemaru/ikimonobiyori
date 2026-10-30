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


U1, U2, U3 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/", "https://www.city.example.lg.jp/kanko/a.html"


def found_for(theme, items, on=date(2026, 10, 30)):
    es = list(build(recs(*items)).values())
    return guide.find(es, themes={theme}, on=on, policy=P), es


class BirdSeasonDefault(unittest.TestCase):
    """フェーズB: 野鳥は、表示してよい時期の窓が無ければ通年が目安(おすすめ)。冬鳥・ほかのテーマは変えない。"""

    def test_policy_row_has_the_approval(self):
        row = P["season_default_by_theme"]["野鳥"]
        self.assertEqual((row["window"], row["provisional"]), ("year_round", False))
        self.assertIn("2026-10-30", row["source"])
        for theme in ("冬鳥", "桜", "花", "ホタル", "紅葉"):
            self.assertNotIn(theme, P["season_default_by_theme"])

    def test_birds_without_a_window_are_recommended_with_a_plain_note(self):
        found, _ = found_for("野鳥", [item(U1, name="試験の沼", theme="野鳥"), item(U2, name="試験の沼", theme="野鳥")])
        self.assertEqual([e["name"] for e in found["recommend"]], ["試験の沼"])
        self.assertEqual(found["no_season"], [])
        text = guide.render_answer(found, P)
        self.assertIn("例年の時期: " + P["answer"]["season_default"]["plain"], text)
        self.assertEqual(guide.forbidden_in_answer(text, P), [])

    def test_birds_with_one_source_season_show_that_sentence_in_brackets(self):
        found, _ = found_for("野鳥", [item(U1, name="試験の沼", theme="野鳥", season=WINTER), item(U2, name="試験の沼", theme="野鳥")])
        self.assertEqual(len(found["recommend"]), 1)
        text = guide.render_answer(found, P)
        self.assertIn("通年が目安（出どころ1件の記載: 11月〜2月）", text)

    def test_winter_birds_without_a_window_stay_unknown(self):
        found, _ = found_for("冬鳥", [item(U1, name="試験の沼", theme="冬鳥"), item(U2, name="試験の沼", theme="冬鳥")])
        self.assertEqual(found["recommend"], [])
        self.assertEqual([e["name"] for e in found["no_season"]], ["試験の沼"])

    def test_other_themes_without_a_window_stay_unknown(self):
        found, _ = found_for("桜", [item(U1, name="試験の沼", theme="桜"), item(U2, name="試験の沼", theme="桜"), item(U3, name="試験の沼", theme="桜")])
        self.assertEqual(found["recommend"], [])
        self.assertEqual(len(found["no_season"]), 1)

    def test_birds_with_a_shown_window_follow_the_window(self):
        two = [item(U1, name="試験の沼", theme="野鳥", season=WINTER), item(U2, name="試験の沼", theme="野鳥", season=WINTER)]
        in_win, _ = found_for("野鳥", two, on=date(2026, 12, 15))
        self.assertEqual(len(in_win["recommend"]), 1)
        self.assertNotIn("season_default", in_win["recommend"][0])
        before, _ = found_for("野鳥", two, on=date(2026, 9, 20))
        self.assertEqual((len(before["recommend"]), len(before["upcoming"])), (0, 1))     # 窓に従う(これから)
        out, _ = found_for("野鳥", two, on=date(2026, 5, 1))
        self.assertEqual((len(out["recommend"]), len(out["other_season"])), (0, 1))

    def test_a_single_source_place_is_still_reference_not_recommended(self):
        found, _ = found_for("野鳥", [item(U1, name="一件の池", theme="野鳥")])
        self.assertEqual(found["recommend"], [])
        self.assertEqual(len(found["reference"]), 1)


if __name__ == "__main__":
    unittest.main()
