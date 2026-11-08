"""段階67: 段階65・66の判断の反映(承認欄 A〜G)・答えの細かな崩れ・山のカードの答え。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

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


class Part1OfficialByPublisherKind(unittest.TestCase):
    """承認欄 C: 町・市・県・国の自身のページは、通信先の承認とは別に「公式」と表示する。ドメインは出さない。"""

    def test_municipal_and_national_domains_are_official(self):
        from ikimonobiyori import publisher as P
        for u in ("https://www.town.ninomiya.kanagawa.jp/0000001281.html", "https://www.city.satte.lg.jp/x.html",
                  "https://www.city.atami.lg.jp/hana/", "https://www.city.odawara.kanagawa.jp/a", "https://www.pref.saitama.lg.jp/a",
                  "https://www.env.go.jp/park/", "https://www.town.matsuda.kanagawa.jp/a", "https://www.vill.example.lg.jp/"):
            self.assertTrue(P.is_official(u), u)
        for u in ("https://www.jorudan.co.jp/a", "https://www.bepal.net/a", "https://www.ashikaga.co.jp/", "https://kouyou.example.com/"):
            self.assertFalse(P.is_official(u), u)
        self.assertTrue(P.is_official("https://example.org/", publisher_kind="municipality"))
        self.assertFalse(P.is_official("https://example.org/", publisher_kind="tourism_association"))

    def test_publisher_name_is_not_a_domain(self):
        from ikimonobiyori import publisher as P
        e = {"tags": {"prefecture": "神奈川県", "city": "二宮町"}}
        self.assertEqual(P.name("https://www.town.ninomiya.kanagawa.jp/0000001281.html", e), "二宮町")
        self.assertEqual(P.name("https://www.pref.example.lg.jp/a", {"tags": {"prefecture": "試験県", "city": "試験町"}}), "試験県")
        self.assertEqual(P.name("https://www.showakinen-koen.jp/flower-information/"), "国営昭和記念公園")
        self.assertIsNone(P.name("https://unknown.example.org/a"))
        self.assertEqual(P.name("https://unknown.example.org/a", title="試験協会 梅の案内"), "試験協会")
        self.assertIsNone(P.name("https://unknown.example.org/a", title="unknown.example.org"))
        self.assertIsNone(P.clean("town.ninomiya.kanagawa.jp"))
        self.assertEqual(P.clean("二宮町"), "二宮町")

    def test_catalog_window_of_a_town_page_reads_official_with_the_town_name(self):
        from ikimonobiyori import observations as O
        e = {"id": "hana-t", "name": "試験の公園", "tags": {"prefecture": "神奈川県", "city": "二宮町"},
             "sources": [{"url": "https://www.town.ninomiya.kanagawa.jp/1.html", "title": "二宮町 花ごよみ"}],
             "flower_windows": [{"kind": "菜の花", "start": "01-01", "end": "02-28", "source_url": "https://www.town.ninomiya.kanagawa.jp/1.html",
                                 "source_host": "www.town.ninomiya.kanagawa.jp", "source_class": "secondary", "unapproved_host": True}]}
        t = O._typical_from_catalog(e)[0]
        self.assertEqual((t["publisher"], t["publisher_official"], t["source_class"]), ("二宮町", True, "secondary"))   # 通信先の区分は変えない

    def test_season_place_line_says_the_town_name_not_the_domain(self):
        from ikimonobiyori import season_place as SP
        t = SP.cfg()["text"]
        r = {"official": SP._official("https://www.town.ninomiya.kanagawa.jp/1.html", False), "publisher": "二宮町"}
        self.assertTrue(r["official"])
        line = t["typical"].format(text="1月上旬〜2月下旬", publisher=r["publisher"])
        self.assertEqual(line, "・例年の時期: 1月上旬〜2月下旬(二宮町)")
        self.assertNotIn("kanagawa.jp", line)

    def test_stage64_65_town_pages_in_the_catalog_read_official(self):
        """段階64・65で足した名所(二宮町・松田町・熱海市)の例年の時期は「公式」・町や市の名前で出る(通信先の区分は secondary のまま)。"""
        from ikimonobiyori import catalog as CM, observations as O
        ents = {e["id"]: e for e in CM.load_catalog("flowers")["entries"]}
        for i, pub in (("hana-0047", "二宮町"), ("hana-0048", "松田町"), ("hana-0049", "熱海市")):
            t = O._typical_from_catalog(ents[i])[0]
            self.assertEqual((t["publisher"], t["publisher_official"]), (pub, True), i)
        from ikimonobiyori import publisher as P
        for i in ("hana-0052", "hana-0053"):                     # 曽我梅林(小田原市)・権現堂桜堤(幸手市)の出典も自治体のページ
            self.assertTrue(P.is_official(ents[i]["sources"][0]["url"]), i)

    def test_target_week_line_without_a_publisher_has_no_stray_comma(self):
        from datetime import date
        from ikimonobiyori import answer_plan as AP
        c = {"current": None, "typical": [{"start": "11-10", "end": "11-30", "publisher": None, "source_class": "secondary", "publisher_official": True}]}
        ln = AP.target_week_line(c, date(2026, 11, 9))
        if ln:
            self.assertIn("(公式)", ln)
            self.assertNotIn("(、", ln)


if __name__ == "__main__":
    unittest.main()
