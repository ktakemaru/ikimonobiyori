"""段階42: 野草・高山植物の指定なしの質問（全体の見ごろ）、ページの先頭の結論と末尾の質問、作業の事情を答えに出さない検査。通信しない。"""
import re
import unittest
from datetime import datetime, timezone, timedelta

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify, guide, wildflower as W, wildflower_page as P

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone(timedelta(hours=9)))
JPEG = (b"\xff\xd8\xff" + b"0" * 50)


def photo_for(name):
    if name in ("コマクサ", "エイザンスミレ"):
        return ({"image_type": "jpeg", "attribution": "(c) 試験, some rights reserved", "license": "CC-BY", "photo_page": "https://www.inaturalist.org/photos/1"}, JPEG)
    return None


def text_of(html):
    return re.sub(r"<[^>]+>", "\n", re.sub(r"<style.*?</style>", "", html, flags=re.S))


class Overview(unittest.TestCase):
    def setUp(self):
        self.p = guide.load_policy()

    def test_not_now_leads_with_the_usual_season(self):
        r = W.overview(month=11)
        self.assertFalse(r["alpine_now"])
        self.assertTrue(r["conclusion"].startswith("いまは高山の花の見ごろではありません。例年の見ごろは7月〜8月です"))
        for place in ("乗鞍岳", "燕岳", "横岳", "硫黄岳"):
            self.assertIn(place, r["conclusion"])

    def test_in_season_says_so(self):
        r = W.overview(month=7)
        self.assertTrue(r["alpine_now"])
        self.assertTrue(r["conclusion"].startswith("7月は高山の花の見ごろです"))

    def test_species_cover_alpine_sites_and_areas(self):
        r = W.overview(month=11)
        alpine = {e["name"] for e in r["species"] if e["section"] == "alpine"}
        self.assertEqual(alpine, {"コマクサ", "ハクサンイチゲ", "クロユリ", "ミヤマキンポウゲ", "メイゲツソウ"})
        low_places = {pl["place"] for e in r["species"] if e["section"] == "lowland" for pl in e["places"]}
        self.assertIn("丹沢", low_places)
        # 種ごとに 1 件。データのない種（花暦にない種）は作らない
        names = [(e["section"], e["name"]) for e in r["species"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("チングルマ", {e["name"] for e in r["species"]})

    def test_cli_without_area_or_site_gives_the_overview(self):
        class A:
            site = area = date = None
            month = 11
            json = False
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(W.wildflower_cmd(A), 0)
        self.assertIn("いまは高山の花の見ごろではありません", buf.getvalue())

    def test_page_has_conclusion_first_cards_and_one_question_last(self):
        r = W.overview(month=11)
        html = P.build_overview(r, policy=self.p, now=NOW, photo_for=photo_for)
        t = [l.strip() for l in text_of(html).split("\n") if l.strip()]
        self.assertEqual(t[2], r["conclusion"])                    # 見出しの次が結論
        self.assertGreaterEqual(html.count('role="img"'), 2)       # 写真つきのカード（高山の花・山麓の野草）
        self.assertNotIn("<svg", html)
        self.assertNotIn("<script", html)
        self.assertEqual(html.rstrip().count("？"), html.count("？"))
        self.assertIn(self.p["wildflower"]["page"]["next_question_overview"], html)
        self.assertTrue(html.index(self.p["wildflower"]["page"]["next_question_overview"]) > html.index("注意"))
        self.assertEqual(sum(1 for l in t if l.endswith("？") or "？" in l), 1)   # 好みの質問は 1 つだけ
        self.assertEqual(P.self_check(html), [])

    def test_single_site_page_leads_with_the_conclusion_only(self):
        r = W.query(site="m041", month=7, with_photo=False)
        html = P.build(r, policy=self.p, now=NOW, photo_for=photo_for)
        t = [l.strip() for l in text_of(html).split("\n") if l.strip()]
        self.assertEqual(t[2], r["conclusion"])
        self.assertNotIn("花は採らず", r["conclusion"])
        self.assertIn(self.p["wildflower"]["page"]["next_question"], html)


class NoWorkTalk(unittest.TestCase):
    def test_parenthesised_work_notes_are_rejected(self):
        for s in ("(コードは変更していないので、テストは実行していません。)",
                  "（コードは変更していないので、テストは実行していません。）",
                  "（今回は実行していません）",
                  "(変更していません)"):
            res = ask_verify.generic_check("乗鞍岳でコマクサが見られます。\n" + s + "\n")
            self.assertFalse(res["ok"], s)
            self.assertTrue(any(e["code"] == "dev_term" for e in res["errors"]), s)

    def test_plain_wildflower_answer_passes_the_work_talk_check(self):
        t = W.overview(month=11)["text"]
        errs = [e for e in ask_verify.generic_check(t)["errors"] if e["code"] not in ("ask_back_only", "too_few_candidates")]
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
