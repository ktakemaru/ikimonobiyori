"""段階23: ガイド型の名所の蓄積(出どころの区分・独立した出どころの数え方・信頼の段階・実在・範囲・候補の記録・見直し・回数)。
通信なし。合成のデータだけ(実在の URL の形は使うが、読まない)。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, guide, paths
from ikimonobiyori.fetch import ParseError, wikidata

P = guide.load_policy()
CP = catalog.load_policy()
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 25, 9, 0, tzinfo=JST)
# 合成の代表点(東京の近く = 範囲内、遠く = 範囲外)
PLACES = {("東京都", "試験区"): {"prefecture": "東京都", "municipality": "試験区", "lat": 35.70, "lon": 139.70, "qid": "Q1"},
          ("試験県", "遠い町"): {"prefecture": "試験県", "municipality": "遠い町", "lat": 34.00, "lon": 135.00, "qid": "Q2"}}


def item(url, name="試験の公園", theme="桜", pref="東京都", muni="試験区", **kw):
    return {"theme": theme, "name": name, "prefecture": pref, "municipality": muni, "url": url, **kw}


def recs(*items, now=NOW):
    return [guide.make_candidate(it, P, now) for it in items]


def build(rows, reviews=None, places=PLACES):
    return {e["name"]: e for e in guide.build_entries(rows, places, P, CP, reviews)}


class Classify(unittest.TestCase):
    def test_classes_by_host(self):
        self.assertEqual(guide.classify("https://www.gotokyo.org/jp/spot/1/", P), ("A", "東京観光財団"))
        self.assertEqual(guide.classify("https://www.kankyo.metro.tokyo.lg.jp/documents/x.pdf", P), ("B", "東京都"))
        self.assertEqual(guide.classify("https://www.city.example.lg.jp/kanko/a.html", P)[0], "A")
        self.assertEqual(guide.classify("https://www.city.example.lg.jp/kanko/a.pdf", P)[0], "B")      # 公的なドメインの PDF は資料
        self.assertEqual(guide.classify("https://rurubu.jp/andmore/spot/1", P), ("C", "るるぶ"))
        self.assertEqual(guide.classify("https://banzokubiology.com/?p=1", P)[0], "D")
        self.assertEqual(guide.classify("https://unknown.example.com/x", P), ("C", "example.com"))     # 表にないホストは C

    def test_same_publisher_on_other_hosts(self):
        self.assertEqual(guide.classify("https://kids.rurubu.jp/article/1/", P)[1], guide.classify("https://rurubu.jp/a", P)[1])
        self.assertEqual(guide.classify("https://summer.walkerplus.com/x", P)[1], guide.classify("https://www.walkerplus.com/article/1/", P)[1])
        self.assertEqual(guide.classify("https://sp.jorudan.co.jp/hanami/1", P)[1], "ジョルダン")
        self.assertNotEqual(guide.classify("https://ameblo.jp/user-a/entry-1.html", P)[1], guide.classify("https://ameblo.jp/user-b/entry-1.html", P)[1])


class Independent(unittest.TestCase):
    def test_same_publisher_counts_once(self):
        e = build(recs(item("https://rurubu.jp/a"), item("https://kids.rurubu.jp/b"), item("https://www.walkerplus.com/c")))["試験の公園"]
        self.assertEqual(e["independent_sources"], 2)
        self.assertEqual(e["tier"], "reference")

    def test_copied_articles_count_once(self):
        e = build(recs(item("https://www.gotokyo.org/x"), item("https://www.jalan.net/y"),
                       item("https://matcha-jp.com/z", copies_of="https://www.jalan.net/y")))["試験の公園"]
        self.assertEqual(e["independent_sources"], 2)
        self.assertEqual(e["tier"], "reference")

    def test_one_personal_blog_with_many_pages_counts_once(self):
        e = build(recs(item("https://banzokubiology.com/?p=1"), item("https://banzokubiology.com/?p=2"), item("https://banzokubiology.com/x")))["試験の公園"]
        self.assertEqual((e["independent_sources"], e["classes"]), (1, ["D"]))
        self.assertFalse(e["exists_confirmed"])
        self.assertEqual(e["approval"]["state"], "candidate")


class Tiers(unittest.TestCase):
    def test_curated_needs_three_independent_and_one_non_personal(self):
        e = build(recs(item("https://www.gotokyo.org/x"), item("https://www.jalan.net/y"), item("https://banzokubiology.com/z")))["試験の公園"]
        self.assertEqual((e["tier"], e["independent_sources"], e["approval"]["state"], e["approval"]["by"]), ("curated", 3, "provisional", "auto-rule"))
        d_only = build(recs(item("https://banzokubiology.com/a"), item("https://ameblo.jp/u1/a"), item("https://ameblo.jp/u2/a")))["試験の公園"]
        self.assertEqual((d_only["independent_sources"], d_only["tier"]), (3, "reference"))      # 個人の発信だけは参考

    def test_verified_from_a_dated_status_of_the_operator(self):
        e = build(recs(item("https://www.gotokyo.org/x", status={"state": "見ごろ", "date": "2026-10-24"})))["試験の公園"]
        self.assertEqual(e["tier"], "verified")
        self.assertEqual(e["approval"]["state"], "provisional")
        self.assertEqual(e["latest_status"]["state"], "見ごろ")
        c = build(recs(item("https://www.jalan.net/x", status={"state": "見ごろ", "date": "2026-10-24"})))["試験の公園"]
        self.assertEqual(c["tier"], "reference")                                                   # メディアの「見ごろ」では確認済みにしない

    def test_verified_from_a_user_visit(self):
        rows = recs(item("https://www.jalan.net/x"))
        eid = rows[0] and guide.entry_id("桜", "東京都", "試験の公園")
        e = build(rows, reviews={eid: {"id": eid, "state": "visited", "at": NOW.isoformat(), "by": "user"}})["試験の公園"]
        self.assertEqual(e["tier"], "verified")

    def test_kinds_and_season_shown_only_with_two_independent_sources(self):
        se = {"text": "11月中旬〜12月中旬", "from": "11月中旬", "to": "12月中旬"}
        e = build(recs(item("https://www.gotokyo.org/x", kinds=["冬桜"], season=se), item("https://www.jalan.net/y", kinds=["冬桜", "十月桜"]),
                       item("https://rurubu.jp/z", season={"text": "11月下旬", "from": "11月下旬", "to": "11月下旬"})))["試験の公園"]
        k = {x["kind"]: x for x in e["kinds"]}
        self.assertEqual((k["冬桜"]["independent_sources"], k["冬桜"]["shown"], k["十月桜"]["shown"]), (2, True, False))
        self.assertEqual((e["season"]["text"], e["season"]["window"], e["season"]["shown"]), (se["text"], {"start": "11-11", "end": "12-20"}, True))


class RangeAndExistence(unittest.TestCase):
    def test_range_in_out_pending(self):
        rows = recs(item("https://www.gotokyo.org/x"), item("https://www.jalan.net/y"), item("https://rurubu.jp/z"),
                    item("https://www.gotokyo.org/x", name="遠くの公園", pref="試験県", muni="遠い町"),
                    item("https://www.jalan.net/y2", name="遠くの公園", pref="試験県", muni="遠い町"),
                    item("https://rurubu.jp/z2", name="遠くの公園", pref="試験県", muni="遠い町"),
                    item("https://www.gotokyo.org/x3", name="不明の公園", muni="知らない町"), item("https://www.jalan.net/y3", name="不明の公園", muni="知らない町"),
                    item("https://rurubu.jp/z3", name="不明の公園", muni="知らない町"))
        b = build(rows)
        self.assertEqual(b["試験の公園"]["range"]["status"], "in_range")
        self.assertEqual(b["試験の公園"]["range"]["km"] % guide.val(P["distance_step_km"]), 0)          # 10 km 単位
        self.assertEqual((b["遠くの公園"]["range"]["status"], b["遠くの公園"]["approval"]["state"]), ("out_of_range", "candidate"))
        self.assertEqual((b["不明の公園"]["range"], b["不明の公園"]["approval"]["state"]), ({"status": "pending"}, "candidate"))
        self.assertIn("範囲は未確認(市区町村の代表点がない)", b["不明の公園"]["approval"]["reasons"])

    def test_find_keeps_out_of_range_apart(self):
        rows = recs(*(item(u, name="遠くの公園", pref="試験県", muni="遠い町") for u in ("https://www.gotokyo.org/x", "https://www.jalan.net/y", "https://rurubu.jp/z")))
        got = guide.find(guide.build_entries(rows, PLACES, P, CP), themes={"桜"}, policy=P)
        self.assertEqual((len(got["recommend"]), len(got["out_of_range"])), (0, 1))

    def test_point_must_match_prefecture(self):
        self.assertTrue(guide.accept_point({"lat": 1.0, "description": "埼玉県児玉郡の町"}, "埼玉県"))
        self.assertFalse(guide.accept_point({"lat": 1.0, "description": "広島県の市"}, "東京都"))       # 同じ名前の別の市を取らない
        self.assertFalse(guide.accept_point({"lat": None, "description": "東京都の市"}, "東京都"))
        self.assertEqual(guide.place_titles("東京都", "港区")[1], "港区 (東京都)")


class Season(unittest.TestCase):
    def test_parse_and_wrap(self):
        w = guide.season_window({"text": "x", "from": "12月下旬", "to": "2月末"})
        self.assertEqual(w, ("12-21", "02-29"))
        self.assertTrue(guide.in_window("01-15", w))
        self.assertFalse(guide.in_window("03-15", w))
        self.assertEqual(guide.season_window({"text": "通年", "year_round": True}), "year_round")
        self.assertIsNone(guide.season_window({"text": "x", "from": "早春"}))
        self.assertEqual(guide.days_until_start(date(2026, 10, 25), ("11-11", "12-20")), 17)
        self.assertEqual(guide.days_until_start(date(2026, 11, 25), ("11-11", "12-20")), 0)

    def test_find_upcoming(self):
        mk = lambda name, fr, to: [item(u, name=name, season={"text": f"{fr}〜{to}", "from": fr, "to": to})
                                   for u in ("https://www.gotokyo.org/" + name, "https://www.jalan.net/" + name, "https://rurubu.jp/" + name)]
        rows = recs(*mk("今の公園", "10月下旬", "12月上旬"), *mk("次の公園", "11月中旬", "12月中旬"), *mk("春の公園", "3月下旬", "4月上旬"))
        got = guide.find(guide.build_entries(rows, PLACES, P, CP), themes={"桜"}, on=date(2026, 10, 25), policy=P)
        self.assertEqual([e["name"] for e in got["recommend"]], ["今の公園"])
        self.assertEqual([e["name"] for e in got["upcoming"]], ["次の公園"])
        self.assertEqual([e["name"] for e in got["other_season"]], ["春の公園"])


class Records(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s23-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {paths.ENV_DATA_DIR: str(self.d)}

    def test_validation_rejects_body_time_and_sns(self):
        self.assertEqual(guide.validate_item(item("https://www.jalan.net/x"), P), [])
        self.assertTrue(guide.validate_item({**item("https://www.jalan.net/x"), "body": "本文"}, P))
        self.assertTrue(guide.validate_item({**item("https://www.jalan.net/x"), "read_at": "2030-01-01T00:00:00+09:00"}, P))   # 時刻は受け取らない
        self.assertTrue(guide.validate_item(item("https://x.com/someone/status/1"), P))
        self.assertTrue(guide.validate_item(item("https://www.jalan.net/x", note="あ" * (guide.val(P["record"]["max_note_chars"]) + 1)), P))
        self.assertTrue(guide.validate_item(item("https://www.jalan.net/x", theme="未知"), P))
        self.assertTrue(guide.validate_item(item("https://www.jalan.net/x", season={"text": "春", "from": "春"}), P))

    def test_record_uses_the_clock_and_the_data_dir(self):
        with mock.patch.dict(os.environ, self.env), mock.patch.object(guide, "clock_now", return_value=NOW):
            n, dup, new = guide.record_candidates([item("https://www.jalan.net/x"), item("https://www.jalan.net/x")], policy=P)
            self.assertEqual((n, dup), (1, 1))
            self.assertEqual(new[0]["read_at"], NOW.isoformat())
            self.assertEqual((new[0]["read_by"], new[0]["class"]), ("summary", "C"))
            self.assertEqual(guide.record_candidates([item("https://www.jalan.net/x")], policy=P)[:2], (0, 1))
        self.assertTrue((self.d / "guide" / "candidates.jsonl").is_file())

    def test_cli_warns_and_ignores_read_at(self):
        batch = self.d / "b.json"
        batch.write_text(json.dumps([item("https://www.jalan.net/x")], ensure_ascii=False), encoding="utf-8")
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(guide, "clock_now", return_value=NOW), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            self.assertEqual(guide.main(["record-candidate", "--batch", str(batch), "--read-at", "2030-01-01T00:00:00+09:00"]), 0)
        self.assertIn("--read-at は使わない", err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["rows"][0]["read_at"], NOW.isoformat())

    def test_reject_is_remembered(self):
        rows = recs(item("https://www.gotokyo.org/x"), item("https://www.jalan.net/y"), item("https://rurubu.jp/z"))
        eid = guide.entry_id("桜", "東京都", "試験の公園")
        with mock.patch.dict(os.environ, self.env):
            guide.review(eid, "rejected", reason="閉園")
            rv = guide.load_reviews(include_runtime=True)
        e = build(rows, reviews=rv)["試験の公園"]
        self.assertEqual((e["approval"]["state"], e["approval"]["by"]), ("rejected", "user"))
        self.assertEqual(guide.find([e], themes={"桜"}, policy=P)["recommend"], [])
        with self.assertRaises(ValueError):
            guide.review("../x", "rejected")

    def test_budget_stops(self):
        pol = {**P, "budget": {**P["budget"], "collect": {"search": 2, "fetch": 1}, "answer": {"search": 1, "fetch": 1}}}
        with mock.patch.dict(os.environ, self.env):
            guide.log_request("search", "collect", "冬桜", policy=pol)
            guide.log_request("search", "collect", "寒桜", policy=pol)
            with self.assertRaises(ValueError):
                guide.log_request("search", "collect", "河津桜", policy=pol)
            guide.log_request("fetch", "collect", "https://x", question="Q1", policy=pol)
            with self.assertRaises(ValueError):
                guide.log_request("fetch", "collect", "https://y", question="Q1", policy=pol)
            u = guide.usage(policy=pol)
        self.assertEqual((u["collect"]["search"]["used"], u["by_question"]["Q1"]["fetch"]), (2, 1))

    def test_unanswered_is_local_and_timed_by_the_clock(self):
        with mock.patch.dict(os.environ, self.env), mock.patch.object(guide, "clock_now", return_value=NOW):
            row = guide.record_unanswered("夜光虫はどこで見られる?")
        self.assertEqual(row["at"], NOW.isoformat())
        self.assertTrue((self.d / "guide" / P["unanswered_file"]).is_file())


class Seed(unittest.TestCase):
    TEXT = ("## A-3. 桜\n\n| ID | 名所 | 所在 | 出どころのURL |\n|---|---|---|---|\n"
            "| S01 | 試験の公園 | 東京都試験区 | https://rurubu.jp/a / https://www.jalan.net/b |\n| S99 | 対応なし | x | https://rurubu.jp/c |\n")

    def test_seed_rows_become_items_per_url(self):
        rows = guide.parse_seed(self.TEXT)
        mapping = {"rows": {"S01": {"theme": "桜", "name": "試験の公園", "prefecture": "東京都", "municipality": "試験区", "kinds": ["冬桜"]}}}
        items, skipped = guide.seed_items(rows, mapping)
        self.assertEqual([i["url"] for i in items], ["https://rurubu.jp/a", "https://www.jalan.net/b"])
        self.assertEqual((items[0]["origin"], items[0]["seed_id"], skipped), ("seed", "S01", ["S99"]))
        self.assertTrue(all(guide.validate_item(i, P) == [] for i in items))


class Wikidata(unittest.TestCase):
    DOC = {"entities": {"Q1": {"id": "Q1", "sitelinks": {"jawiki": {"title": "試験町"}}, "descriptions": {"ja": {"value": "東京都の町"}},
                               "claims": {"P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 35.7, "longitude": 139.7}}}}]}},
                        "-1": {"missing": ""}}}

    def test_parse(self):
        got = wikidata.parse_entities(self.DOC)
        self.assertEqual(got["試験町"], {"qid": "Q1", "lat": 35.7, "lon": 139.7, "description": "東京都の町"})
        with self.assertRaises(ParseError):
            wikidata.parse_entities({"x": 1})
        self.assertIn("www.wikidata.org", wikidata.entities_url(["試験町"]))

    def test_stops_on_429(self):
        calls = []

        def get(url):
            calls.append(url)
            return 429, "", {}
        got, rep = wikidata.read_points(["a", "b", "c"], http_get=get, cfg={"live": {"min_interval_s": 0}}, max_requests=5, batch=1, sleep=lambda s: None)
        self.assertEqual((len(calls), rep["status"], got), (1, "HTTP 429", {}))

    def test_live_is_refused_under_test(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(guide.main(["places-fetch", "--live", "--max-requests", "1"]), 2)
        self.assertIn("テスト中", err.getvalue())

    def test_the_host_is_only_in_the_guide_list(self):
        from ikimonobiyori.config import load_config
        hosts = load_config()["live"]["allowed_hosts_by_subject"]
        self.assertEqual(hosts["guide_places"], ["www.wikidata.org"])
        self.assertEqual([k for k, v in hosts.items() if "www.wikidata.org" in v], ["guide_places"])


class KindsAndBuckets(unittest.TestCase):
    def test_kind_notes_have_no_place_and_need_two_sources(self):
        k = {"scope": "kind", "theme": "冬鳥", "name": "試験の鳥", "kinds": ["試験の鳥"], "season": {"text": "冬", "from": "12月", "to": "2月"}}
        self.assertEqual(guide.validate_item({**k, "url": "https://www.jalan.net/a"}, P), [])
        one = build(recs({**k, "url": "https://www.jalan.net/a"}))["試験の鳥"]
        self.assertEqual((one["range"]["status"], one["approval"]["state"]), ("not_applicable", "candidate"))
        two = build(recs({**k, "url": "https://www.jalan.net/a"}, {**k, "url": "https://rurubu.jp/b"}))["試験の鳥"]
        self.assertEqual(two["approval"]["state"], "provisional")
        got = guide.find([two], themes={"冬鳥"}, policy=P)
        self.assertEqual(([e["name"] for e in got["kind_notes"]], got["recommend"]), (["試験の鳥"], []))

    def test_unknown_season_and_single_source_kind_are_not_recommended(self):
        three = ("https://www.gotokyo.org/x", "https://www.jalan.net/y", "https://rurubu.jp/z")
        rows = recs(*(item(u, kinds=["梅"] if i else ["梅", "ツバキ"]) for i, u in enumerate(three)))
        es = guide.build_entries(rows, PLACES, P, CP)
        got = guide.find(es, themes={"桜"}, on=date(2026, 2, 1), policy=P)
        self.assertEqual([e["name"] for e in got["no_season"]], ["試験の公園"])           # 時期が分からないものは、対象の日に合うと言わない
        got = guide.find(es, themes={"桜"}, kinds=["ツバキ"], policy=P)
        self.assertEqual((got["recommend"], [e["name"] for e in got["reference"]]), ([], ["試験の公園"]))   # 1 件だけの種類ではおすすめにしない
        self.assertEqual([e["name"] for e in guide.find(es, themes={"桜"}, kinds=["梅"], policy=P)["recommend"]], ["試験の公園"])


class CommittedData(unittest.TestCase):
    """data/guide/ に置いた記録・代表点・見直しから作り直した結果が、置いたカタログと一致する(手で直していない)。本文を含まない。"""

    def test_catalog_is_rebuilt_from_the_records(self):
        recs_ = guide.all_records(include_runtime=False)
        places = guide.load_places(include_runtime=False)
        entries = guide.build_entries(recs_, places, P, CP, guide.load_reviews(include_runtime=False))
        key = lambda e: e["id"]
        self.assertEqual(sorted(json.loads(json.dumps(entries, ensure_ascii=False)), key=key), sorted(guide.committed_entries(), key=key))

    def test_records_hold_facts_only(self):
        fields = set(P["record"]["fields"])
        for r in guide.all_records(include_runtime=False):
            self.assertLessEqual(set(r), fields, r["url"])
            it = {k: v for k, v in r.items() if k in P["record"]["input_fields"]}
            self.assertEqual(guide.validate_item(it, P), [], r["url"])
            self.assertEqual((r["class"], r["publisher"]), guide.classify(r["url"], P), r["url"])
            self.assertTrue(guide.sources_mod_parse(r["read_at"]).utcoffset() is not None)

    def test_places_come_from_wikidata_only(self):
        for p in guide.load_places(include_runtime=False).values():
            self.assertEqual(p["source"], "wikidata")
            self.assertRegex(p["qid"], r"^Q[0-9]+$")


class Review(unittest.TestCase):
    def test_review_lists_provisional_first_and_folds_candidates(self):
        rows = recs(item("https://www.gotokyo.org/x"), item("https://www.jalan.net/y"), item("https://rurubu.jp/z"),
                    item("https://rurubu.jp/w", name="参考の公園"))
        md = guide.review_markdown(guide.build_entries(rows, PLACES, P, CP), P)
        self.assertIn("## 桜(名所: 仮承認 1 件・候補 1 件)", md)
        self.assertLess(md.index("試験の公園"), md.index("<details>"))
        self.assertGreater(md.index("参考の公園"), md.index("<details>"))
        self.assertIn(guide.entry_id("桜", "東京都", "試験の公園"), md)

    def test_reject_cli_writes_under_the_data_dir(self):
        d = Path(tempfile.mkdtemp(prefix="ikimono-s23r-"))
        self.addCleanup(shutil.rmtree, d, True)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {paths.ENV_DATA_DIR: str(d)}), contextlib.redirect_stdout(out):
            self.assertEqual(guide.main(["reject", "g-0123456789", "--reason", "閉園"]), 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "rejected")
        self.assertTrue((d / "guide" / "reviews.jsonl").is_file())

    def test_the_review_document_lists_every_provisional_place(self):
        md = (H.ROOT / "docs" / "stage23-review.md").read_text(encoding="utf-8")
        for e in guide.committed_entries():
            if guide.approved(e):
                self.assertIn(e["id"], md)


class Steps(unittest.TestCase):
    """段階23 フェーズ5: 3 つのファイルの同じ節に、ガイド型の答え方がある(一致は test_sources.Procedure が確かめる)。"""

    def test_the_guide_steps_are_in_the_skill(self):
        s = (H.ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("### 現況型とガイド型(段階23)", "### ガイド型の答え方(段階23)", "guide find --word", "検索せずに答える", "**仮**(検索で集めたもの)",
                       "独立した出どころが 1 件も見つからないときだけ", "「補足」として最大 2 行まで", "「これから」の欄", "guide unanswered",
                       "聞き返さない", "`--read-at` は渡さない"):
            self.assertIn(needle, s)
        self.assertNotIn("よいですか」と聞く", s)

    def test_new_words_map_to_themes(self):
        for w in ("渡り鳥", "冬鳥", "白鳥", "ハクチョウ", "カモ", "ツル", "ホタル", "蛍", "桜", "早咲き", "冬桜", "寒桜", "河津桜", "十月桜",
                  "さざんか", "ロウバイ", "ツバキ", "梅", "水仙", "カワセミ"):
            self.assertIsNotNone(guide.theme_of(w, P), w)
        self.assertIsNone(guide.theme_of("恐竜", P))


if __name__ == "__main__":
    unittest.main()
