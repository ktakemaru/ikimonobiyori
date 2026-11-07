"""段階60(指示書 docs/stage60-followup-instructions.md)。通信しない。合成データだけ。"""
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O

P = O.load_policy()
CFG = O.merge_cfg(P)
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=JST)
D = [date(2026, 11, 7), date(2026, 11, 8)]


def spot(i, name, city="試験町", point=None, **kw):
    s = {"id": i, "subject": "autumn_leaves", "name": name, "prefecture": "神奈川県", "city": city, "area": "試験",
         "typical": [{"text": "11月上旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/1", "year": 2026, "source_class": "secondary"}],
         "pages": []}
    if point:
        s["point"] = {"lat": point[0], "lon": point[1]}
    s.update(kw)
    return s


def rec(name, state="色づきはじめ", d="2026-11-06", city="試験町"):
    return {"subject": "autumn_leaves", "name": name, "city": city, "prefecture": "神奈川県", "state": state, "state_date": d,
            "url": "https://kankou.example.org/koyo", "publisher": "試験の観光協会", "source_class": "official"}


class Part1NameMerge(unittest.TestCase):
    """第1部: 同じ名所の別名(表記ゆれ)を 1 つにまとめる。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def facts(self, spots, rows):
        O.record(rows, env=self.env, now=NOW)
        return O.facts("autumn_leaves", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc={"spots": spots},
                       catalogs={"autumn_leaves": {"entries": []}})

    def names(self, f):
        return [c["name"] for c in f["candidates"]]

    def test_official_label_without_area_prefix_joins_the_listed_spot(self):
        f = self.facts([spot("t-1", "試験 山寺(長安寺)")], [rec("山寺(長安寺)"), rec("試験 山寺(長安寺)", d="2026-11-05")])
        self.assertEqual(self.names(f).count("試験 山寺(長安寺)"), 1)
        self.assertNotIn("山寺(長安寺)", self.names(f))                       # 2 回目の候補にならない
        self.assertEqual(len(f["candidates"]), 1)

    def test_variants_outside_the_list_become_one_candidate(self):
        f = self.facts([spot("t-1", "試験の湖")], [rec("宮ノ沢"), rec("試験 宮ノ沢", d="2026-11-05"), rec("試験の湖")])
        extra = [c for c in f["candidates"] if c.get("outside_list")]
        self.assertEqual(len(extra), 1)
        self.assertIn("試験 宮ノ沢", extra[0]["aliases"])                       # 別名として残す(消さない)

    def test_list_of_spots_is_not_merged_into_one_part(self):
        self.assertFalse(O.name_contained("華厳の滝", "中禅の湖・華厳の滝", CFG))
        self.assertTrue(O.name_contained("山寺(長安寺)", "試験 山寺(長安寺)", CFG))

    def test_short_names_and_ambiguous_hits_are_not_merged(self):
        self.assertFalse(O.name_contained("湯本", "試験 湯本", CFG))            # 下限の字数より短い
        cands = [O._from_spot(spot("a", "北 試験の滝"), P, {}), O._from_spot(spot("b", "南 試験の滝"), P, {})]
        self.assertIsNone(O.match_record(rec("試験の滝"), cands, P, {}))         # 2 つに当たるときは結びつけない

    def test_city_must_not_conflict(self):
        cands = [O._from_spot(spot("a", "試験 山寺(長安寺)", city="別の町"), P, {})]
        self.assertIsNone(O.match_record(rec("山寺(長安寺)", city="試験町"), cands, P, {}))

    def test_alias_dictionary_maps_official_label(self):
        cands = [O._from_spot(spot("a", "試験の美術館"), P, {})]
        self.assertIs(O.match_record(rec("試験(美術館の丘)"), cands, P, {O._key("試験(美術館の丘)"): O._key("試験の美術館")}), cands[0])
        self.assertIn("湖尻", O.place_alias_table())                             # 箱根町観光協会の地点の書き方(台帳の covers)

    def test_candidates_near_with_similar_names_are_merged_as_alias(self):
        spots = [spot("a", "試験 紅葉の谷", point=(35.0, 139.0)), spot("b", "紅葉の谷", point=(35.001, 139.001)),
                 spot("c", "紅葉の谷", city="遠い町", point=(35.5, 139.5))]
        cands = O.all_candidates("autumn_leaves", P, {"spots": spots}, {"autumn_leaves": {"entries": []}})
        ids = [c["id"] for c in cands]
        self.assertEqual(ids.count("b"), 0)                                       # 約140m・同じ町 → 別名
        self.assertIn("c", ids)                                                   # 遠い・別の町は別の名所
        a = next(c for c in cands if c["id"] == "a")
        self.assertIn("紅葉の谷", a["aliases"])
        self.assertEqual(a["merged"], ["b"])

    def test_same_point_with_different_names_is_not_merged(self):
        spots = [spot("a", "試験の湖", point=(35.0, 139.0)), spot("b", "試験の峠", point=(35.0, 139.0))]
        cands = O.all_candidates("autumn_leaves", P, {"spots": spots}, {"autumn_leaves": {"entries": []}})
        self.assertEqual({c["id"] for c in cands}, {"a", "b"})

    def test_merge_rule_values_are_in_the_policy(self):
        self.assertEqual(CFG["max_km"], 0.3)
        self.assertGreaterEqual(CFG["min"], 3)


SKELETON = """見頃に向かう可能性がある場所を選びました。
対象の日は11/7(土)・11/8(日)です。
今回のおすすめ
① 試験の湖 約42km: 今の状況は色づきはじめ(11/6時点、試験の観光協会)。例年の見頃: 11月中旬。見頃に向かう可能性があります。
② 試験の峠 約58km: 紹介サイトでは見頃とされています(11/5時点、試験サイト。公式ではありません)。見頃が続いている可能性があります。

出典
https://kankou.example.org/koyo
https://kouyou.example.com/list
"""

POLISHED = """見頃に向かう可能性がある場所を選びました。
対象の日は11/7(土)・11/8(日)です。
今回のおすすめ
① まずは試験の湖(約42km)。今の状況は色づきはじめで(11/6時点、試験の観光協会)、例年の見頃は11月中旬です。見頃に向かう可能性があります。
② 足を延ばすなら試験の峠(約58km)。紹介サイトでは見頃とされています(11/5時点、試験サイト。公式ではありません)。見頃が続いている可能性があります。

出典
https://kankou.example.org/koyo
https://kouyou.example.com/list
"""

NAMES = ["試験の湖", "試験の峠", "試験の滝", "カエデ", "イチョウ", "試験の観光協会"]


class Part2FactConsistency(unittest.TestCase):
    """第2部: 整えた文章と骨組みの事実の一致検査。"""

    def codes(self, text):
        from ikimonobiyori import polish as PL
        return [(e["code"], e["kind"]) for e in PL.check(SKELETON, text, NAMES)["errors"]]

    def test_polished_text_with_the_same_facts_passes(self):
        self.assertEqual(self.codes(POLISHED), [])

    def test_added_facts_fail(self):
        for extra, kind in (("12/1にまつりがあります。", "date"), ("駐車場は200台です。", "number"),
                            ("イチョウも見られます。", "name"), ("詳しくは https://other.example.net/ を。", "url"),
                            ("約3kmの散策路があります。", "km"), ("9:00に開きます。", "time"), ("12月上旬まで続きます。", "month")):
            text = POLISHED.replace("出典\n", extra + "\n出典\n")
            self.assertIn(("polish_added_fact", kind), self.codes(text), extra)

    def test_added_facility_name_fails(self):
        self.assertIn(("polish_added_fact", "name"), self.codes(POLISHED.replace("足を延ばすなら", "試験の滝の帰りに")))

    def test_dropped_important_facts_fail(self):
        cases = {"current_date": POLISHED.replace("(11/6時点、試験の観光協会)", "(試験の観光協会)"),
                 "phrase": POLISHED.replace("見頃が続いている可能性があります。", "見頃です。"),
                 "certainty": POLISHED.replace("。公式ではありません", ""),
                 "source": POLISHED.replace("https://kouyou.example.com/list\n", "")}
        for kind, text in cases.items():
            self.assertIn(("polish_dropped_fact", kind), self.codes(text), kind)

    def test_rewrite_limit_is_one(self):
        from ikimonobiyori import polish as PL
        use, st = PL.decide(None, SKELETON, False, True)
        self.assertEqual((use, st["attempts"]), ("retry", 1))
        use, st = PL.decide(st, SKELETON, False, True)
        self.assertEqual(use, "skeleton")                                         # 2 回目も通らなければ骨組みのまま
        use, st = PL.decide(st, SKELETON + "x", True, True)
        self.assertEqual((use, st["attempts"]), ("polished", 1))                 # 骨組みが変われば数え直す
        use, _ = PL.decide({"skeleton": SKELETON, "attempts": 1}, SKELETON, True, False)
        self.assertEqual(use, "skeleton")                                         # 通常の検査に落ちても同じ
        self.assertEqual(PL.cfg()["max_rewrites"], 1)

    def test_flow_falls_back_to_the_skeleton_after_one_rewrite(self):
        from ikimonobiyori import ask
        with tempfile.TemporaryDirectory() as d:
            f = ask.Flow(d, now=NOW, env={"IKIMONOBIYORI_DATA_DIR": d})
            bad = POLISHED.replace("(11/6時点、試験の観光協会)", "(試験の観光協会)")
            use, final, fr, _ = f.polish_check(bad, SKELETON, generic=True)
            self.assertEqual((use, final), ("retry", None))
            self.assertFalse(fr["ok"])
            use, final, _, _ = f.polish_check(bad, SKELETON, generic=True)
            self.assertEqual(use, "skeleton")
            self.assertEqual(final, SKELETON)                                     # 通らない文を除いた版ではなく、骨組みのまま
            self.assertEqual(Path(d, "final.txt").read_text(encoding="utf-8"), SKELETON)



class Part3NearFirst(unittest.TestCase):
    """第3部: 近場の節は距離を優先し、今回のおすすめに近場を少なくとも 1 件。"""

    def plan(self, cands):
        import test_stage56 as T56
        from ikimonobiyori import answer_plan as AP
        return AP.build(T56.facts_of(cands), "autumn_leaves", AP.load_policy())

    def cands(self):
        import test_stage56 as T56
        c = T56.cand
        return [c("隣の県の公園", km=30, state="色づき始め", sdate="2026-11-06", age=1, typical=("11-01", "12-05"), prefecture="東京都"),
                c("地元の森", km=8, state="色づき始め", sdate="2026-11-03", age=4, typical=("11-01", "12-05"), prefecture="埼玉県"),
                c("歩く試験山", km=60, state="見頃", sdate="2026-11-05", age=2, typical=("11-01", "11-30"), elev=900),
                c("遠い試験渓谷", km=140, state="見頃", sdate="2026-11-05", age=2, typical=("11-05", "11-25"), prefecture="栃木県"),
                c("遠い試験の滝", km=120, state="見頃", sdate="2026-11-05", age=2, typical=("11-05", "11-25"), prefecture="茨城県", city="試験村")]

    def test_near_section_is_ordered_by_distance_within_the_same_outlook(self):
        p = self.plan(self.cands())
        near = next(s for s in p["sections"] if s["aim"] == "near")
        self.assertEqual([i["name"] for i in near["items"]][:2], ["地元の森", "隣の県の公園"])   # 点数・鮮度では隣の県が上だが、近い順

    def test_at_least_one_pick_is_near(self):
        p = self.plan(self.cands())
        lim = 50
        self.assertTrue(any(x["distance_km"] is not None and x["distance_km"] <= lim for x in p["picks"]))
        self.assertIn("地元の森", [x["name"] for x in p["picks"]])

    def test_near_guarantee_replaces_the_weakest_pick(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        far = lambda n, cl: {"name": n, "distance_km": 120, "has_current": True, "cluster": cl, "outlook": "in_peak", "score": 60, "current_date": "2026-11-05"}
        near_it = {"name": "近い", "distance_km": 10, "has_current": True, "cluster": "c9", "outlook": "toward", "score": 40, "current_date": "2026-11-05"}
        chosen = [far("A", "c1"), far("B", "c2"), dict(far("C", "c3"), outlook="toward", score=30)]
        out = AP.ensure_near_pick(chosen, [{"aim": "near", "items": [near_it]}], pol)
        self.assertEqual([x["name"] for x in out], ["A", "B", "近い"])             # いちばん弱い C と入れ替える
        self.assertEqual(AP.ensure_near_pick(chosen, [], pol), chosen)            # 近場の候補がなければ変えない

    def test_no_this_year_candidates_still_stay_out_of_the_picks(self):
        import test_stage56 as T56
        cs = self.cands() + [T56.cand("すぐ近くの公園", km=3, typical=("11-01", "12-05"), prefecture="埼玉県")]
        p = self.plan(cs)
        self.assertNotIn("すぐ近くの公園", [x["name"] for x in p["picks"]])       # 今年の情報がない候補は入れない(段階58 第3部のまま)


    def test_origin_and_dates_run_without_a_work_folder(self):
        import io
        from contextlib import redirect_stdout
        from ikimonobiyori import ask
        for argv in (["origin", "--question", "大宮から紅葉を見に行きたい"], ["dates", "--question", "紅葉を見に行きたい"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ask.main(argv), 0, argv[0])


class Part5SiteWalk(unittest.TestCase):
    """第5部: サイトの辿り(通信しない。ページの中身は合成)。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def walk(self):
        from ikimonobiyori import site_walk as SW
        return SW, SW.start("t-vc", "https://vc.example.org/", extra_hosts=["docs.example.org"], env=self.env)

    def test_depth_limit(self):
        SW, st = self.walk()
        url = "https://vc.example.org/"
        for d in range(1, 6):
            nxt = f"https://vc.example.org/dayori{d}/"
            SW.add_page(st, url, [{"href": nxt, "text": "自然公園だより"}])
            url = nxt
        depths = [q["depth"] for q in st["queue"]] + [v["depth"] for v in st["visited"].values()]
        self.assertEqual(max(depths), SW.cfg()["max_depth"])                  # 深さ 3 より先は拾わない
        self.assertEqual(SW.cfg()["max_depth"], 3)

    def test_stays_on_the_same_site(self):
        SW, st = self.walk()
        SW.add_page(st, "https://vc.example.org/", [{"href": "https://other.example.net/dayori/", "text": "だより"},
                                                    {"href": "https://docs.example.org/kankou/", "text": "刊行物"},
                                                    {"href": "/about/", "text": "施設の案内"}])
        urls = [q["url"] for q in st["queue"]]
        self.assertEqual(urls, ["https://docs.example.org/kankou/"])         # 外部へは出ない・優先語のない内部リンクも辿らない

    def test_robots_disallow_is_respected(self):
        SW, st = self.walk()
        SW.set_robots(st, "User-agent: *\nDisallow: /private/\nSitemap: https://vc.example.org/sitemap.xml\nUser-agent: badbot\nDisallow: /\n")
        self.assertEqual(st["disallow"], ["/private/"])
        SW.add_page(st, "https://vc.example.org/", [{"href": "/private/dayori/", "text": "だより"}, {"href": "/news/dayori/", "text": "だより"}])
        urls = [q["url"] for q in SW.next_urls(st)]
        self.assertNotIn("https://vc.example.org/private/dayori/", urls)
        self.assertIn("https://vc.example.org/news/dayori/", urls)
        self.assertIn("https://vc.example.org/sitemap.xml", urls)            # robots.txt のサイトマップも使う
        SW.add_sitemap(st, "<urlset><url><loc>https://vc.example.org/archive/2026/</loc></url><url><loc>https://vc.example.org/pdf/vcd26aki.pdf</loc></url></urlset>")
        self.assertIn("https://vc.example.org/pdf/vcd26aki.pdf", [p["url"] for p in st["pdfs"]])

    def test_pdf_detection_and_latest_issue_needs_a_year(self):
        from ikimonobiyori import pdf_text as PT
        SW, st = self.walk()
        self.assertTrue(SW.is_pdf("https://vc.example.org/a/b.PDF"))
        self.assertTrue(SW.is_pdf("https://vc.example.org/file.pdf?v=2"))
        self.assertFalse(SW.is_pdf("https://vc.example.org/pdf/list.html"))
        SW.add_page(st, "https://vc.example.org/", [{"href": "/d/no10.pdf", "text": "だより 第10号"},
                                                    {"href": "/d/2026_10.pdf", "text": "だより 秋号"},
                                                    {"href": "/d/r7.pdf", "text": "令和7年3月号"},
                                                    {"href": "https://other.example.net/x.pdf", "text": "外部"}])
        rows = SW.record_pdfs(st, env=self.env, taken_on="2026-11-07")
        self.assertEqual(len(rows), 3)                                           # 外部の PDF は記録しない
        self.assertEqual({r["published"] for r in rows}, {None, "2026-10", "2025-03"})
        self.assertEqual(PT.latest_issue(rows)["url"], "https://vc.example.org/d/2026_10.pdf")   # 年の分からない号は最新にしない
        self.assertEqual(SW.record_pdfs(st, env=self.env), [])                   # 同じ URL は足さない
        s = SW.summary(st, env=self.env)
        self.assertEqual((s["pdfs"], s["pdfs_read"]), (3, 0))

    def test_pager_links_stay_at_the_same_depth(self):
        SW, st = self.walk()
        SW.add_page(st, "https://vc.example.org/", [{"href": "/news/page/2/", "text": "次へ"}])
        self.assertEqual(st["queue"][0]["depth"], 0)

    def test_the_module_does_not_import_network_libraries(self):
        src = (Path(__file__).resolve().parent.parent / "ikimonobiyori" / "site_walk.py").read_text(encoding="utf-8")
        for w in ("requests", "urllib.request", "http.client", "socket"):
            self.assertNotIn("import " + w, src)


class FakeGit:
    """git の呼び出しの代わり(実際の git も子プロセスも動かさない)。"""

    def __init__(self, remote="origin\thttps://github.com/ktakemaru/ikimonobiyori-knowledge.git (fetch)\n", staged_changes=True):
        self.calls, self.remote, self.staged = [], remote, staged_changes

    def __call__(self, args, **kw):
        import types
        self.calls.append(args)
        sub = args[3]
        out, rc = "", 0
        if sub == "remote":
            out = self.remote
        elif sub == "diff":
            rc = 1 if self.staged else 0
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr="")

    def subs(self):
        return [a[3] for a in self.calls]


class Part7KnowledgeBackup(unittest.TestCase):
    """第7部: ask knowledge backup(commit だけ。push しない)。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.repo = Path(self.tmp.name) / "knowledge"
        self.repo.mkdir()

    def make_repo(self):
        (self.repo / ".git").mkdir()
        (self.repo / ".gitignore").write_text("*\n!.gitignore\n!cards.jsonl\n!publications.jsonl\n", encoding="utf-8")
        (self.repo / "cards.jsonl").write_text('{"title": "試験"}\n', encoding="utf-8")
        (self.repo / "publications.jsonl").write_text('{"url": "https://example.org/a.pdf"}\n', encoding="utf-8")
        (self.repo / "photo.jpg").write_text("x", encoding="utf-8")
        (self.repo / "README.md").write_text("x", encoding="utf-8")          # 許可の一覧(.gitignore)にない

    def backup(self, git):
        from datetime import date as D
        from ikimonobiyori import knowledge_backup as KB
        return KB.backup(env=self.env, run=git, today=D(2026, 11, 7))

    def test_commits_only_when_there_are_changes(self):
        self.make_repo()
        git = FakeGit()
        rc, lines = self.backup(git)
        self.assertEqual(rc, 0)
        self.assertIn("commit", git.subs())
        commit = next(a for a in git.calls if a[3] == "commit")
        self.assertIn("知識カードのバックアップ（2026-11-07）", commit)
        self.assertIn("push は本人", lines[-1])
        git = FakeGit(staged_changes=False)
        rc, lines = self.backup(git)
        self.assertNotIn("commit", git.subs())
        self.assertEqual(lines[-1], "変更はありません")

    def test_stops_when_the_remote_is_not_the_private_repository(self):
        self.make_repo()
        for remote in ("origin\thttps://github.com/ktakemaru/ikimonobiyori.git (fetch)\n", ""):
            git = FakeGit(remote=remote)
            rc, lines = self.backup(git)
            self.assertEqual(rc, 2)
            self.assertEqual(git.subs(), ["remote"])                              # add も commit もしない
            self.assertIn("リモートが想定外", lines[0])

    def test_only_allowed_files_are_added(self):
        self.make_repo()
        (self.repo / "publications.jsonl").write_text('{"note": "C:\\\\Users\\\\someone\\\\x.pdf"}\n', encoding="utf-8")
        git = FakeGit()
        rc, lines = self.backup(git)
        add = next(a for a in git.calls if a[3] == "add")
        self.assertEqual(add[add.index("--") + 1:], [".gitignore", "cards.jsonl"])  # 写真・README(許可外)・絶対パスを含むファイルは add しない
        self.assertIn("publications.jsonl", lines[0])

    def test_never_pushes_and_never_creates_a_repository(self):
        git = FakeGit()
        rc, lines = self.backup(git)
        self.assertEqual((rc, git.calls), (2, []))                               # リポジトリがなければ何もしない
        self.assertIn("バックアップの設定がありません", lines[0])
        self.assertFalse((self.repo / ".git").exists())
        self.make_repo()
        git = FakeGit()
        self.backup(git)
        self.assertNotIn("push", git.subs())
        src = (Path(__file__).resolve().parent.parent / "ikimonobiyori" / "knowledge_backup.py").read_text(encoding="utf-8")
        self.assertNotIn('"push"', src)
        self.assertNotIn("shell=True", src)


if __name__ == "__main__":
    unittest.main()
