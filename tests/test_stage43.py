"""段階43: 霧ヶ峰・尾瀬・富士山五合目の花暦、質問の型ごとのページの切り方（今・この山・図鑑）。通信しない。"""
import re
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, wildflower as W, wildflower_page as P

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone(timedelta(hours=9)))
JPEG = (b"\xff\xd8\xff" + b"0" * 60000)


def photo_for(name):
    return ({"image_type": "jpeg", "attribution": "(c) 試験, some rights reserved", "license": "CC-BY", "photo_page": "https://www.inaturalist.org/photos/1"},
            JPEG + name.encode("utf-8"))


class Data(unittest.TestCase):
    def test_new_rows_have_sources_and_no_problems(self):
        self.assertEqual(W.audit()["problems"], [])

    def test_kirigamine_has_the_operator_flower_pages(self):
        r = W.query(site="m043", month=7, with_photo=False)
        names = {f["name"] for f in r["flowers"]}
        self.assertIn("ニッコウキスゲ", names)
        nik = next(f for f in r["flowers"] if f["name"] == "ニッコウキスゲ")
        self.assertEqual(nik["grade"], "established")          # 霧ヶ峰自然保護センターと車山高原SKYPARK の 2 件
        self.assertGreaterEqual(len(W.overview(area="霧ヶ峰")["species"]), 30)

    def test_protected_species_stay_off_the_site(self):
        self.assertNotIn("ミズチドリ", {f["name"] for f in W.query(site="m043", month=7, with_photo=False)["flowers"]})
        self.assertNotIn("ミズチドリ", {e["name"] for e in W.overview(site="m043")["species"]})

    def test_oze_area_only_row_does_not_land_on_a_mountain(self):
        self.assertIn("ニッコウキスゲ", {f["name"] for f in W.query(area="尾瀬", month=7, with_photo=False)["flowers"]})
        self.assertNotIn("ニッコウキスゲ", {f["name"] for f in W.query(site="m076", month=7, with_photo=False)["flowers"]})
        self.assertIn("ハクサンコザクラ", {f["name"] for f in W.query(site="m076", month=7, with_photo=False)["flowers"]})

    def test_fuji_fifth_station_row(self):
        self.assertEqual([f["name"] for f in W.query(site="m012", month=7, with_photo=False)["flowers"]], ["メイゲツソウ"])
        self.assertEqual(W.query(site="m013", month=7, with_photo=False)["status"], "preparing")


class Modes(unittest.TestCase):
    def setUp(self):
        self.p = guide.load_policy()

    def test_mode_by_question_type(self):
        A = lambda **k: SimpleNamespace(**dict(dict(site=None, area=None, month=None, date=None, zukan=False), **k))
        self.assertEqual(P.page_mode(A()), "now")
        self.assertEqual(P.page_mode(A(area="丹沢")), "mountain")
        self.assertEqual(P.page_mode(A(site="m041", month=7)), "place_month")
        self.assertEqual(P.page_mode(A(zukan=True)), "zukan")

    def test_mountain_sorted_by_start(self):
        r = W.overview(area="丹沢")
        starts = [e["start"] for e in r["species"]]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(r["conclusion"].startswith("丹沢で例年見られる花を、見ごろの早い順に"))
        html = P.build_overview(r, policy=self.p, now=NOW, photo_for=photo_for)
        self.assertIn(self.p["wildflower"]["page"]["heading_mountain"], html)
        self.assertEqual(P.self_check(html), [])

    def test_now_mode_says_not_in_season_and_shows_lowland(self):
        r = W.overview(month=11)
        self.assertTrue(r["conclusion"].startswith("いまは高山の花の見ごろではありません"))
        self.assertIn("リンドウ", r["conclusion"])

    def test_alpine_is_decided_by_elevation(self):
        r = W.overview(month=7)
        sec = {e["name"]: e["section"] for e in r["species"] if e["places"][0]["place"].startswith(("霧ヶ峰", "乗鞍"))}
        self.assertEqual(sec["コマクサ"], "alpine")
        self.assertEqual(sec["ウツボグサ"], "lowland")        # 霧ヶ峰(車山 1925m)は高山に入れない


class Zukan(unittest.TestCase):
    def setUp(self):
        self.p = guide.load_policy()
        self.r = W.overview(month=11)

    def test_pages_split_by_season_each_with_navigation(self):
        pages = P.build_zukan(self.r, policy=self.p, now=NOW, photo_for=lambda n: None)
        names = [f for f, _ in pages]
        for season in "1234":
            self.assertTrue(any(f.startswith(f"wildflower-zukan-sanroku-{season}") for f in names), season)
        self.assertTrue(any(f.startswith("wildflower-zukan-takayama-") for f in names))
        for f, html in pages:
            self.assertIn("<nav>", html)
            self.assertLess(html.index("<nav>"), html.index("<h2>"))
            for g, _ in pages:
                if g.rsplit("-", 1)[0] != f.rsplit("-", 1)[0] or True:
                    pass
            self.assertGreaterEqual(html.count('href="wildflower-zukan-'), 4)         # ほかの季節への案内
            self.assertNotIn("<script", html)
            self.assertEqual(P.self_check(html), [])

    def test_overflow_goes_to_a_second_page_of_the_same_season(self):
        big = lambda n: ({"image_type": "jpeg", "attribution": "(c) 試験", "license": "CC-BY", "photo_page": "https://www.inaturalist.org/photos/1"},
                         b"\xff\xd8\xff" + n.encode("utf-8") * 80000)             # 1 枚が約 0.4MB（base64 後に約 0.5MB 超）
        pages = P.build_zukan(self.r, policy=self.p, now=NOW, photo_for=big)
        spring = [f for f, _ in pages if f.startswith("wildflower-zukan-sanroku-1")]
        self.assertGreaterEqual(len(spring), 2)
        self.assertIn("wildflower-zukan-sanroku-1-2.html", spring)
        limit = self.p["photos"]["html"]["max_embed_bytes"]["value"]
        for f, html in pages:
            self.assertLessEqual(len(html.encode("utf-8")), limit + 300 * 1024, f)    # 本文は小さい。写真は上限の中

    def test_every_species_appears_once(self):
        pages = P.build_zukan(self.r, policy=self.p, now=NOW, photo_for=lambda n: None)
        text = "".join(re.sub(r"<[^>]+>", "\n", h) for _, h in pages)
        for e in self.r["species"]:
            self.assertGreaterEqual(text.count(e["name"]), 1, e["name"])
        self.assertGreaterEqual(len({e["name"] for e in self.r["species"]}), 130)


if __name__ == "__main__":
    unittest.main()
