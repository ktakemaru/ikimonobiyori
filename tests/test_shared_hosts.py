"""複数の公園が使うホストの発行元の名前・場所を分けた花の記録の花の名前(2026-11-28 の残る問題 1・3)。通信しない。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import observations as O
from ikimonobiyori import publisher as P

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=JST)
BASE = "https://www.kanagawaparks.com/"
PARKS = {"kurihama/": "くりはま", "verny/blog/": "ヴェルニー", "odawarafg/": "小田原"}


def others(token):
    return [t for t in PARKS.values() if t != token]


class Name(unittest.TestCase):
    def test_shared_host_name_comes_from_the_same_park_path(self):
        for path, token in [*PARKS.items(), ("kurihama/blog/", "くりはま"), ("kurihama/news/2026102708571710610.html", "くりはま"),
                            ("verny/", "ヴェルニー")]:
            name = P.name(BASE + path)
            if name is None:
                continue
            for other in others(token):
                self.assertNotIn(other, name, path)
        self.assertIn("くりはま", P.name(BASE + "kurihama/"))                       # 以前は同じホストの最初の行(小田原)
        self.assertIn("ヴェルニー", P.name(BASE + "verny/blog/"))
        self.assertIn("小田原", P.name(BASE + "odawarafg/"))

    def test_unknown_park_on_a_shared_host_gets_no_other_parks_name(self):
        self.assertIsNone(P.name(BASE + "shiken-no-koen/"))
        self.assertEqual(P.name(BASE + "shiken-no-koen/", {"sources": []}, "試験の公園(作り物)"), "試験の公園")

    def test_every_known_page_on_a_shared_host_has_a_name(self):
        """複数の公園が使うホストの、名所と台帳のページは、どれも名前が決まる(出典の行にドメインを出さない)。"""
        from ikimonobiyori import brief_refresh as BR
        urls = {u for p in BR.place_index() for u in p["pages"] if u and P.shared_depth(u)}
        urls |= {s["url"] for s in BR.ledger_pages() if P.shared_depth(s["url"])}
        self.assertTrue(urls)
        self.assertEqual(sorted(u for u in urls if not P.name(u)), [])

    def test_every_listed_shared_host_resolves_by_path(self):
        for url, token, bad in [("https://www.kanagawa-park.or.jp/sagamihara/flower.html", "相模原", ["境川", "秦野"]),
                                ("https://www.tokyo-park.or.jp/park/kyu-furukawa/news/index.html", "東京都公園協会", ["六義園", "葛西"])]:
            name = P.name(url)
            self.assertIn(token, name)
            for b in bad:
                self.assertNotIn(b, name)
        self.assertEqual(P.site_key(BASE + "kurihama/blog/"), "kanagawaparks.com/kurihama")
        self.assertEqual(P.site_key("https://www.nikko-kankou.org/flowering/autumn-leaves"), "nikko-kankou.org")

    def test_host_names_are_split_by_park(self):
        hn = GB.host_names()
        self.assertNotIn("kanagawaparks.com", hn)
        for path, token in [("kurihama/", "くりはま"), ("verny/", "ヴェルニー")]:
            names = hn[P.site_key(BASE + path)]
            for other in others(token):
                self.assertFalse([n for n in names if other in n], (path, other))


class LineFacts(unittest.TestCase):
    def test_lines_of_two_parks_do_not_cross(self):
        """今日の資料にあった取り違え(くりはまのページに「ヴェルニー公園」や小田原の指定管理者)が起きない。"""
        text = "\n".join(["くりはま花の国(横須賀市): 例年の時期は分かりません", "ヴェルニー公園: 今年の情報は確認できていません",
                          "くりはま花の国: お知らせ「コスモスまつり終了について」(11月16日配信)", "", "出典",
                          "- " + BASE + "kurihama/", "- " + BASE + "verny/blog/", ""])
        F = GB._Facts(GB.cfg(), set())
        GB._line_facts(F, text, GB.cfg(), {})
        self.assertEqual(len(F.rows), 3)
        for r in F.rows:
            token = "ヴェルニー" if r["content"].startswith("ヴェルニー") else "くりはま"
            if r.get("url"):
                self.assertIn("verny" if token == "ヴェルニー" else "kurihama", r["url"], r["content"])
            for other in others(token):
                self.assertNotIn(other, r.get("source") or "", r["content"])

    def test_species_spot_publisher_is_the_same_park(self):
        from ikimonobiyori import season_place as SP
        self.assertIn("くりはま", SP._publisher(BASE + "kurihama/"))


class FlowerName(unittest.TestCase):
    def setUp(self):
        self.old = os.environ["IKIMONOBIYORI_DATA_DIR"]
        os.environ["IKIMONOBIYORI_DATA_DIR"] = tempfile.mkdtemp(prefix="ikimono-flower-")
        self.addCleanup(os.environ.__setitem__, "IKIMONOBIYORI_DATA_DIR", self.old)

    def test_state_gets_the_flower_name_only_when_missing(self):
        self.assertEqual(O.state_with_kind("開花中", "サザンカ"), "サザンカ: 開花中")
        self.assertEqual(O.state_with_kind("つばき園では曙が開花しました", "ツバキ"), "つばき園では曙が開花しました")
        self.assertEqual(O.state_with_kind("開花中", None), "開花中")

    def test_brief_facts_name_the_flower(self):
        O.record([{"subject": "flowers", "name": "県立相模原公園", "city": "相模原市", "kind": "サザンカ", "state": "開花中", "part": "シャラノキゲート付近",
                   "state_date": "2026-11-27", "url": "https://www.kanagawa-park.or.jp/sagamihara/feed/feed-flower.php", "publisher": "試験の指定管理者",
                   "source_class": "official"}], now=NOW - timedelta(minutes=5))
        d = GB.build("横浜から行ける場所で、花を見たい。見頃の花と場所を教えて。", now=NOW)
        rows = [f for f in d["facts"] if "相模原公園" in f["content"] and "開花中" in f["content"]]
        self.assertTrue(rows)
        for f in rows:
            self.assertIn("サザンカ", f["content"])


if __name__ == "__main__":
    unittest.main()
