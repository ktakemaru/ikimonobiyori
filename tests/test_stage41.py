"""段階41: 野草・高山植物の写真つきページ、八ヶ岳・北アルプス(一部の地点)の花暦。通信しない。"""
import unittest
from datetime import datetime, timezone, timedelta

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, wildflower as W, wildflower_page as P

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone(timedelta(hours=9)))
JPEG = (b"\xff\xd8\xff" + b"0" * 50)


def photo_for(name):
    if name == "コマクサ":
        return ({"image_type": "jpeg", "attribution": "(c) 試験, some rights reserved", "license": "CC-BY", "photo_page": "https://www.inaturalist.org/photos/1"}, JPEG)
    return None


class Partial(unittest.TestCase):
    def test_partial_sites_have_rows_only_for_their_place(self):
        self.assertEqual([f["name"] for f in W.query(site="m004", month=7, with_photo=False)["flowers"]], ["コマクサ"])
        names = {f["name"] for f in W.query(site="m041", month=7, with_photo=False)["flowers"]}
        self.assertIn("ハクサンイチゲ", names)
        self.assertEqual({f["name"] for f in W.query(site="m036", month=7, with_photo=False)["flowers"]}, {"コマクサ"})

    def test_other_sites_of_the_area_stay_preparing(self):
        self.assertEqual(W.query(site="m002", month=7, with_photo=False)["status"], "preparing")
        self.assertEqual(W.query(site="m037", month=7, with_photo=False)["flowers"], [])


class Page(unittest.TestCase):
    def setUp(self):
        self.p = guide.load_policy()

    def test_photo_card_and_name_only_rows_without_drawings(self):
        r = W.query(site="m041", month=7, with_photo=False)
        html = P.build(r, policy=self.p, now=NOW, photo_for=photo_for)
        self.assertIn("コマクサ", html)
        self.assertIn("ハクサンイチゲ", html)
        self.assertNotIn("<svg", html)
        self.assertNotIn("<script", html)
        self.assertEqual(html.count('role="img"'), 1)           # 写真があるのはコマクサだけ。ほかは名前だけの行
        self.assertNotIn("写真なし", html)

    def test_protected_species_get_no_photo(self):
        r = W.query(area="丹沢", month=6, with_photo=False)
        called = []
        P.build(r, policy=self.p, now=NOW, photo_for=lambda n: called.append(n))
        prot = {f["name"] for f in r["flowers"] if f["protected"]}
        self.assertTrue(prot)
        self.assertFalse(prot & set(called))
        self.assertFalse(prot & set(P.photo_names(r)))

    def test_prefetch_list_has_popular_alpine_flowers(self):
        names = self.p["photos"]["prefetch"]["野草"]
        for n in ("コマクサ", "ハクサンイチゲ", "チングルマ", "ミヤマキンバイ", "ミヤマクロユリ", "シナノキンバイ", "ヨツバシオガマ", "ニッコウキスゲ", "ヤマオダマキ"):
            self.assertIn(n, names)


if __name__ == "__main__":
    unittest.main()


class HanaHyakumeizan(unittest.TestCase):
    def test_marks_and_the_bonus_source(self):
        sites = W.sites_by_id()
        self.assertTrue(sites["m029"].get("hana_hyakumeizan"))
        self.assertFalse(sites["m041"].get("hana_hyakumeizan"))
        row = {"area": "高尾", "sites": ["m029"], "src": ["tkp"]}
        self.assertIn("hhm", W.effective_src(row))
        self.assertNotIn("hhm", W.effective_src({"area": "高尾", "sites": ["m029", "m041"], "src": ["tkp"]}))
        self.assertNotIn("hhm", W.effective_src({"area": "高尾", "src": ["tkp"]}))

    def test_the_bonus_alone_never_makes_a_row_established(self):
        d = W.load()
        # 実在する出どころ 1 件の行 + 選定 = 2 件だが、選定だけの行（実在の出どころ 0）は作れない
        for r in d["rows"]:
            self.assertTrue(r["src"], r)
