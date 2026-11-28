"""台帳で承認済みの現況のページが、資料の自動の読み直しに届くこと(2026-11-28 の直す案 1〜9)。合成データ(通信しない)。"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import auto_refresh as AU
from ikimonobiyori import brief_refresh as BR
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as V
from ikimonobiyori import observations as O
from ikimonobiyori import pending_sources as PS
from ikimonobiyori import research as RS

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=JST)
BLOG = "https://www.kanagawaparks.com/kurihama/blog/"
ISEHARA = "https://isehara-kanko.com/news/flower/13991/"
SAGAMIHARA = "https://www.kanagawa-park.or.jp/sagamihara/feed/feed-flower.php"


def cand(name, rank=None, subject=None):
    return {"name": name, "rank": rank, "subject": subject}


def targets(cands, **kw):
    kw.setdefault("max_pages", 50)
    return BR.targets("試験の質問", cands, now=NOW, **kw)


class Reachable(unittest.TestCase):
    def test_every_approved_status_page_is_reachable_from_some_place(self):
        """承認済みの現況ページは、必ずどれかの候補から届く(台帳の covers を名所に結ぶ。実際の対象選びを通す)。"""
        index, ledger = BR.place_index(), BR.ledger_pages()
        self.assertTrue(ledger)
        reached = set()
        for p in index:
            if any(AU.url_key(x["url"]) not in reached for x in BR.pages_for([p["name"]], p["subject"], index=index, ledger=ledger)):
                got = targets([cand(p["name"], 1, p["subject"])], max_pages=200)
                reached |= {AU.url_key(x["url"]) for x in got}
        self.assertEqual([s["id"] for s in ledger if AU.url_key(s["url"]) not in reached], [])


class Targets(unittest.TestCase):
    def test_covers_link_pages_that_are_not_in_the_place_pages(self):
        self.assertIn(BLOG, [x["url"] for x in targets([cand("くりはま花の国", 1, "flowers")])])
        self.assertIn(ISEHARA, [x["url"] for x in targets([cand("大山寺・大山阿夫利神社下社", 1, "autumn_leaves")])])

    def test_freshness_is_per_page(self):
        first = [x["url"] for x in targets([cand("くりはま花の国", 1, "flowers")])]
        top = next(u for u in first if u != BLOG)
        O.record([{"subject": "flowers", "spot": "obs-hana-0004", "state": "試験の状態", "state_date": "2026-11-28", "url": top,
                   "publisher": "試験の発行元", "source_class": "official", "basis": "page"}], now=NOW - timedelta(hours=1))
        after = [x["url"] for x in targets([cand("くりはま花の国", 1, "flowers")])]
        self.assertNotIn(top, after)
        self.assertIn(BLOG, after)

    def test_candidates_without_subject_use_flower_ledger_for_flower_species(self):
        got = targets([cand("くりはま花の国"), cand("県立相模原公園"), cand("三溪園")], species_words=["ツバキ", "サザンカ"], subjects=["flowers"])
        urls = [x["url"] for x in got]
        self.assertIn(BLOG, urls)
        self.assertIn(SAGAMIHARA, urls)
        self.assertNotIn("https://www.sankeien.or.jp/news/10921/", urls)        # 紅葉の台帳のページは読まない

    def test_asked_place_comes_first_then_asked_flower(self):
        cs = [cand("花菜ガーデン", 1, "flowers"), cand("京成バラ園", 2, "flowers"), cand("大山寺・大山阿夫利神社下社", 14, "autumn_leaves")]
        self.assertEqual(targets(cs, asked_names=["大山寺・大山阿夫利神社下社"])[0]["name"], "大山寺・大山阿夫利神社下社")
        got = targets([cand("京成バラ園", 1, "flowers"), cand("くりはま花の国", 2, "flowers")], species_words=["ツバキ"])
        self.assertEqual(got[0]["url"], BLOG)

    def test_rebuild_does_not_add_held_pages_but_reads_newly_approved_ones(self):
        cs = [cand("くりはま花の国", 1, "flowers"), cand("県立相模原公園", 2, "flowers"), cand("京成バラ園", 3, "flowers")]
        all_urls = [x["url"] for x in targets(cs)]
        self.assertGreaterEqual(len(all_urls), 3)
        a = [x["url"] for x in targets(cs, max_pages=1, hold_hours=2)]
        self.assertEqual(a, all_urls[:1])
        self.assertEqual([x["url"] for x in targets(cs, max_pages=1, hold_hours=2)], a)
        newer = {"url": "https://new.example.jp/flower/", "publisher": "試験", "ledger": "flowers", "id": "test-new", "approved_on": "2026-11-28",
                 "covers": [{"name": "くりはま花の国"}], "flower_kinds": []}
        pages = BR.ledger_pages() + [newer]
        with mock.patch.object(BR, "ledger_pages", lambda: pages):
            self.assertIn(newer["url"], [x["url"] for x in targets(cs, max_pages=5, hold_hours=2)])

    def test_brief_targets_do_not_need_a_plan_or_search_step(self):
        """資料の経路(facts.json)や調べた印に関係なく、資料の候補から読み直しの対象を選ぶ。"""
        got = GB._refresh_targets("大山の紅葉はどうかな?", {"subjects": ["autumn_leaves"]},
                                  [cand("大山寺・大山阿夫利神社下社", 14, "autumn_leaves")], NOW, None, GB.cfg())
        self.assertIn(ISEHARA, [x["url"] for x in got])


class AltText(unittest.TestCase):
    HTML = ('<html><body><a><span>11/27(金)試験の山の様子です。</span> <span>まだ見頃ですが、落葉が目立つように。 お早</span></a>'
            '<img alt="11/27(金)試験の山の様子です。\nまだ見頃ですが、落葉が目立つように。 お早めにどうぞ。" src="a.jpg">'
            '<img alt="ロゴ" src="b.png"><p>本文の行はそのまま残る</p></body></html>')

    def test_full_alt_is_added_and_truncated_copy_removed(self):
        text = AU.with_alt(RS.html_text(self.HTML), self.HTML)
        body, _, alts = text.partition("-----")
        self.assertIn("お早めにどうぞ。", alts)
        self.assertNotIn("お早", body)
        self.assertIn("本文の行はそのまま残る", body)
        self.assertNotIn("- ロゴ", text)

    def test_only_listed_pages_get_alt(self):
        self.assertEqual(AU._alt_pages(), {AU.url_key(ISEHARA)})
        self.assertNotIn("お早めにどうぞ", RS.html_text(self.HTML))

    def test_truncated_post_text_is_rejected(self):
        ep = {"own_account": True, "own_account_basis": "フッターの案内", "account": "試験", "posted_on": "2026-11-27", "text": "まだ見頃ですが…"}
        errs = O.embedded_post_errors({"embedded_post": ep}, O.load_policy())
        self.assertTrue([e for e in errs if "途中で切れて" in e])


class FlowerKinds(unittest.TestCase):
    def place(self):
        return next(c for c in O.all_candidates("flowers") if c["name"] == "くりはま花の国")

    def rows(self, *states):
        return [{"state": s, "state_norm": n, "state_date": d, "read_at": d + "T10:00:00+09:00", "source_class": "official",
                 "url": "https://x.example.jp/", "host": "x.example.jp", "kind": k} for s, n, d, k in states]

    def test_spot_and_catalog_kinds_are_united(self):
        self.assertTrue({"コスモス", "ツバキ"} <= set(self.place()["flower_kinds"]))

    def test_ended_kind_applies_only_to_that_flower(self):
        rows = self.rows(("コスモス: 2分咲き", "見頃前", "2026-10-27", "コスモス"), ("コスモスまつり終了について", "見頃過ぎ", "2026-11-16", None))
        got, ended = O.ended_kinds(self.place(), rows, "flowers")
        self.assertEqual(ended, {"コスモス"})
        self.assertEqual(got, [])

    def test_record_without_flower_name_keeps_whole_place_ended(self):
        rows = self.rows(("今季の公開は終了しました", "見頃過ぎ", "2026-11-16", None))
        self.assertEqual(O.ended_kinds(self.place(), rows, "flowers"), (rows, set()))


class MonthList(unittest.TestCase):
    def rec(self, **kw):
        return {"subject": "flowers", "name": "試験の庭園", "kind": "サザンカ", "listed_months": [10, 11], "url": "https://x.example.jp/autumn/",
                "publisher": "試験市", "source_class": "official", "basis": "page", **kw}

    def test_record_without_state_or_typical(self):
        self.assertEqual(O.validate(self.rec(), O.load_policy()), [])
        self.assertTrue(O.validate(self.rec(typical="10月～11月"), O.load_policy()))
        self.assertTrue(O.validate(self.rec(listed_months=[13]), O.load_policy()))

    def test_brief_line_and_verify(self):
        O.record([self.rec()], now=NOW)
        F = mock.Mock()
        GB._month_list_facts(F, "サザンカはどこで見られる?", {}, [], NOW, None, GB.cfg())
        lines = [c.args[1] for c in F.add.call_args_list if "試験の庭園" in c.args[1]]
        self.assertEqual(len(lines), 1)
        self.assertIn("10月・11月の花の一覧に名前が載っています", lines[0])
        self.assertNotIn("例年", lines[0])
        brief = {"facts": [{"id": "F001", "fields": {"month_list": "10,11"}}]}
        bad = [{"ids": ["F001"], "clean": "例年は10月から11月の花です。", "line": 1}]
        ok = [{"ids": ["F001"], "clean": "10月・11月の花の一覧に名前が載っています。", "line": 1}]
        self.assertEqual([e["code"] for e in V.month_list_errors(bad, brief, GB.cfg())], ["month_list_as_typical"])
        self.assertEqual(V.month_list_errors(ok, brief, GB.cfg()), [])

    def test_kind_removed_by_catalog_needs_confirmation(self):
        r = self.rec(name="新宿御苑")
        self.assertTrue([e for e in O.validate(r, O.load_policy()) if "理由をつけて外している" in e])
        self.assertEqual(O.validate({**r, "excluded_kind_confirmed": "月の一覧として記録する"}, O.load_policy()), [])


class GeneralTalk(unittest.TestCase):
    CARDS = [{"id": "K001", "link": "この種の話", "category": "種の解説"}, {"id": "K002", "link": "小話", "category": "名前・歴史・文化"},
             {"id": "K003", "link": "この場所の話", "category": "地形・地質・火山"}, {"id": "K004", "link": "一般の話(テーマ)", "category": "季節の仕組み"}]

    def errors(self, sents, route="plan"):
        rows = [{"ids": i, "clean": t, "line": n} for n, (i, t) in enumerate(sents)]
        return V.general_talk_errors(rows, {"route": route, "cards": self.CARDS}, GB.cfg())

    def test_two_pass_three_fail(self):
        two = [(["K001"], "花びらは1枚ずつ散ります。"), (["K001"], "鳥が蜜を吸います。"), ([], "場所の話。"), (["K002"], "名前の由来です。")]
        self.assertEqual(self.errors(two), [])
        self.assertEqual([e["code"] for e in self.errors(two + [(["K004"], "色づく仕組みです。")])], ["too_many_general_talk"])

    def test_safety_place_and_knowledge_routes_do_not_count(self):
        base = [(["K001"], "花びらは1枚ずつ散ります。"), (["K002"], "名前の由来です。")]
        extra = [(["K001"], "葉にはチャドクガの幼虫がいることがあります。"), (["K003"], "中腹に下社があります。"), (["F001"], "見頃です。")]
        self.assertEqual(self.errors(base + extra), [])
        self.assertEqual(self.errors(base + [(["K004"], "仕組みです。")], route="knowledge"), [])


class ReadFirst(unittest.TestCase):
    def test_approved_status_page_is_auto_read(self):
        self.assertFalse(PS.not_auto_read(ISEHARA))
        self.assertFalse(PS.not_auto_read("https://nowhere.example.jp/"))
        with mock.patch.object(BR, "reachable_urls", lambda: set()):
            self.assertTrue(PS.not_auto_read(ISEHARA))


if __name__ == "__main__":
    unittest.main()
