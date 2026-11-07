"""段階39(指示書 docs/stage39-photo-wildflower-instructions.md): 写真つきページの標準化(A)と答えの質(B)。通信しない。合成のデータだけ。
A: 同じ写真は 1 回だけ埋め込む / 写真の取得(photos-ensure)はキャッシュにない種だけ・取れない種は探し直さない・上限で止まる /
   花は植物(属・雑種も)で採る / ページは結論を先頭に・写真なしは名前だけの行
B: facts を持たない経路の検査(generic_check)/ 結論を先頭に・参考は短く・時期の順 / 利用者が行った名所はおすすめに出る / 仮のテーマで記録できる"""
import json
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as V
from ikimonobiyori import guide, guide_photos
from ikimonobiyori.fetch import inat_photos
from ikimonobiyori.photo_pool import PhotoPool

POLICY = guide.load_policy()
PH = POLICY["photos"]
TODAY = date(2026, 11, 3)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20
IMG_URL = "https://inaturalist-open-data.s3.amazonaws.com/photos/111/medium.jpg"
NOSLEEP = lambda s: None  # noqa: E731


def cand(tid, sci, ja, rank="species", cls="Plantae"):
    return {"id": tid, "name": sci, "rank": rank, "preferred_common_name": ja, "iconic_taxon_name": cls}


def search(*cs):
    return json.dumps({"total_results": len(cs), "results": list(cs)})


def taxon(tid, sci, photo_id=111):
    p = {"id": photo_id, "license_code": "cc-by", "attribution": "(c) 撮影者, some rights reserved (CC BY)", "medium_url": IMG_URL}
    return json.dumps({"results": [{"id": tid, "name": sci, "default_photo": p}]})


class Net:
    """URL に含まれる語 → 応答。呼ばれた回数を数える。"""
    def __init__(self, table):
        self.table, self.calls, self.bytes_calls = table, [], []

    def get(self, url, *_a):
        self.calls.append(url)
        for k, v in self.table.items():
            if k in url:
                return (v[0], v[1], {})
        raise AssertionError(f"想定外の URL: {url}")

    def get_bytes(self, url, mx):
        self.bytes_calls.append(url)
        return 200, JPEG, {}

    @property
    def n(self):
        return len(self.calls) + len(self.bytes_calls)


class Pool(unittest.TestCase):
    META = {"image_type": "jpeg"}

    def test_the_same_photo_is_embedded_once(self):
        pool = PhotoPool()
        tags = [pool.tag(self.META, b"AAA", "カルガモ") for _ in range(3)] + [pool.tag(self.META, b"BBB", "コガモ")]
        css = pool.css()
        self.assertEqual((pool.unique, pool.refs), (2, 4))
        self.assertEqual(css.count("base64,"), 2)
        self.assertEqual(tags[0], tags[1])
        self.assertNotEqual(tags[0], tags[3])
        self.assertIn('role="img"', tags[0])

    def test_alt_is_escaped(self):
        self.assertIn("&lt;b&gt;", PhotoPool().tag(self.META, b"A", "<b>"))


class Ensure(unittest.TestCase):
    def run_ensure(self, names, net, theme="花", **kw):
        return guide_photos.ensure(names, theme=theme, policy=POLICY, http_get=net.get, http_bytes=net.get_bytes, today=TODAY, sleep=NOSLEEP, **kw)

    def setUp(self):
        self.addCleanup(lambda: None)

    def test_plant_theme_accepts_plantae_and_genus_but_birds_stay_species_only(self):
        pht = {**PH, "class_name": "Plantae", "ranks": ["species", "hybrid", "genus"]}
        row, why = inat_photos.decide("アジサイ", inat_photos.parse_search(json.loads(search(cand(1, "Hydrangea", "アジサイ", rank="genus")))), pht)
        self.assertIsNone(why)
        self.assertEqual(row["scientific"], "Hydrangea")
        row, why = inat_photos.decide("アジサイ", inat_photos.parse_search(json.loads(search(cand(1, "Hydrangea", "アジサイ", rank="genus")))), PH)
        self.assertIsNone(row)                                                    # 鳥の設定（species だけ）では採らない

    def test_new_name_is_searched_and_saved_then_second_run_makes_no_request(self):
        net = Net({"/taxa?": (200, search(cand(7001, "Hibiscus testus", "ムクゲ試験"))), "/taxa/7001": (200, taxon(7001, "Hibiscus testus"))})
        r1 = self.run_ensure(["ムクゲ試験"], net)
        self.assertEqual(r1["results"], {"ムクゲ試験": "saved"})
        self.assertGreater(r1["requests"], 0)
        net2 = Net({})
        r2 = self.run_ensure(["ムクゲ試験"], net2)
        self.assertEqual((r2["results"], r2["requests"], net2.n), ({"ムクゲ試験": "cached"}, 0, 0))     # 2 回目は通信 0 件

    def test_a_name_without_photo_is_remembered_and_not_searched_again(self):
        net = Net({"/taxa?": (200, search())})                                    # 候補が 0 件
        r1 = self.run_ensure(["写真なし試験花"], net)
        self.assertEqual(r1["results"], {"写真なし試験花": "none"})
        net2 = Net({})
        r2 = self.run_ensure(["写真なし試験花"], net2)
        self.assertEqual((r2["results"], net2.n), ({"写真なし試験花": "none"}, 0))

    def test_generic_words_are_skipped_without_a_request(self):
        net = Net({})
        r = self.run_ensure(["カモ類"], net)
        self.assertEqual((r["results"], net.n), ({"カモ類": "skipped"}, 0))

    def test_the_run_limit_stops_and_the_rest_is_pending(self):
        net = Net({"/taxa?": (200, search())})
        r = self.run_ensure(["上限試験一", "上限試験二", "上限試験三"], net, max_requests=2)
        self.assertEqual(r["requests"], 2)
        self.assertEqual(sorted(k for k, v in r["results"].items() if v == "pending"), ["上限試験三"])

    def test_429_stops_and_marks_the_rest_pending_not_none(self):
        net = Net({"/taxa?": (429, "")})
        r = self.run_ensure(["制限試験一", "制限試験二"], net)
        self.assertEqual(r["status"], "HTTP 429")
        self.assertNotIn("none", r["results"].values())

    def test_ensure_does_nothing_in_tests_when_not_allowed(self):
        res = guide_photos.ensure_for_page(["カワセミ"], "野鳥", POLICY)           # テスト中は許可されない → キャッシュだけで続ける（None）
        self.assertIsNone(res)

    def test_prefetch_lists_are_in_the_policy_and_marked_provisional(self):
        self.assertGreaterEqual(len(PH["prefetch"]["野鳥"]), 100)
        self.assertGreater(len(PH["prefetch"]["花"]), 40)
        self.assertTrue(PH["negative_cache_days"]["provisional"])
        self.assertIn("承認B", PH["auto_fetch_source"])
        self.assertEqual(PH["max_requests_per_run"]["value"], 80)                 # 上限・間隔は承認のまま
        self.assertEqual(PH["min_interval_s"]["value"], 1)


class GenericCheck(unittest.TestCase):
    OK = "11月3日におすすめの名所は、城峯公園です。\n\n## おすすめ\n1. **城峯公園**(埼玉県神川町) — 冬桜\n2. **桜山公園**(群馬県) — 冬桜\n3. **三ツ池公園**(横浜市) — 桜\n"

    def check(self, text):
        return V.generic_check(text)

    def test_a_normal_answer_passes(self):
        self.assertTrue(self.check(self.OK)["ok"])

    def test_work_notes_and_process_sentences_are_rejected(self):
        for bad in ("作業メモ(答えとは別)", "コマンド `guide find` の出力", "record-candidate はしていません", "テーマの表に追加します", "検査器に通りませんでした",
                    "答えの検査(ask verify)を実行していません", "コードは変更していないので、テストは実行していません", "final.txt の内容です"):
            r = self.check(self.OK + bad + "\n")
            self.assertFalse(r["ok"], bad)

    def test_ask_back_only_is_rejected_but_unanswerable_is_allowed(self):
        r = self.check("野草の見頃と場所は、いつ・どこで見たいか教えてください。\n")
        self.assertFalse(r["ok"])
        self.assertEqual(r["errors"][0]["code"], "ask_back_only")
        self.assertTrue(self.check("検索しても出どころが見つからず、お答えできません。探した言葉: 野草。\n")["ok"])

    def test_the_typo_in_the_item_name_is_detected(self):
        self.assertFalse(self.check(self.OK + "- 熱海 — 出どろの区分: 報道\n")["ok"])

    def test_strip_removes_only_the_bad_lines(self):
        text = self.OK + "作業メモ: 内部\n"
        r = self.check(text)
        out = V.generic_strip(text, r)
        self.assertNotIn("作業メモ", out)
        self.assertIn("城峯公園", out)


def entry(name, **kw):
    e = {"id": name, "scope": "place", "theme": "花", "name": name, "prefecture": "神奈川県", "municipality": "試験市", "kinds": [{"kind": "梅", "independent_sources": 3, "shown": True}],
         "season": {"text": "2月中旬〜3月上旬", "window": {"start": "02-11", "end": "03-10"}, "independent_sources": 3, "shown": True}, "tier": "curated",
         "independent_sources": 3, "classes": ["B"], "exists_confirmed": True, "range": {"status": "in_range"}, "approval": {"state": "provisional"}, "sources": []}
    e.update(kw)
    return e


class AnswerText(unittest.TestCase):
    def render(self, found, on=date(2026, 2, 20)):
        return guide.render_answer(found, POLICY, origin_line="出発地: 横浜", on=on, themes={"花"})

    def found(self, **kw):
        base = {k: [] for k in ("recommend", "upcoming", "other_season", "no_season", "reference", "out_of_range", "kind_notes")}
        base.update(kw)
        return base

    def test_the_conclusion_comes_first(self):
        text = self.render(self.found(recommend=[entry("甲梅林"), entry("乙梅林")]))
        lines = [l for l in text.splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("出発地"))
        self.assertEqual(lines[1], "2月20日におすすめの名所は、甲梅林・乙梅林です。")
        self.assertTrue(lines[2].startswith("今年の咲き具合"))                        # 今の状態の記録がないときの 1 文
        self.assertTrue(lines[3].startswith("## おすすめ"))

    def test_conclusion_when_nothing_is_recommended(self):
        text = self.render(self.found(upcoming=[entry("丙梅林")]))
        self.assertIn("2月20日はまだ早い時期です。これから見ごろに入る名所は、丙梅林です。", text)
        self.assertIn("見つかりませんでした", self.render(self.found()))

    def test_reference_is_limited_and_the_rest_is_counted(self):
        n = POLICY["answer"]["reference_max"]["value"]
        refs = [entry(f"参考{i}号園", tier="reference") for i in range(n + 3)]
        text = self.render(self.found(reference=refs))
        self.assertIn("- ほか3件", text)
        self.assertEqual(sum(1 for i in range(n + 3) if f"参考{i}号園" in text), n)

    def test_timeline_lists_kinds_in_order_of_start(self):
        a = entry("早咲き園", kinds=[{"kind": "冬桜", "independent_sources": 3, "shown": True}],
                  season={"text": "例年10月下旬〜12月上旬", "window": {"start": "10-21", "end": "12-10"}, "independent_sources": 3, "shown": True})
        b = entry("河津園", kinds=[{"kind": "河津桜", "independent_sources": 3, "shown": True}],
                  season={"text": "2月上旬〜3月上旬", "window": {"start": "02-01", "end": "03-10"}, "independent_sources": 3, "shown": True})
        text = self.render(self.found(recommend=[a], other_season=[b]), on=date(2026, 11, 3))
        i1, i2 = text.index("- 冬桜: 例年の時期は10月下旬〜12月上旬(早咲き園)"), text.index("- 河津桜: 例年の時期は2月上旬〜3月上旬(河津園)")
        self.assertLess(i1, i2)
        self.assertNotIn("例年の時期は例年", text)

    def test_no_typo_in_the_template_words(self):
        text = self.render(self.found(recommend=[entry("甲梅林")], reference=[entry("丁園", tier="reference")]))
        self.assertNotIn("出どろ", text)
        self.assertIn("出どころの区分", text)

    def test_state_note_avoid_sources_and_next_question(self):
        rec = [entry("甲梅林", sources=[{"url": "https://example.org/a"}])]
        out = [entry("丙梅林", tier="reference")]
        text = self.render(self.found(recommend=rec, other_season=out))
        self.assertIn("今年の咲き具合・色づきの日付つきの記録は読めていません", text)        # 今の状態の日付つきの記録がないとき、言い切らない
        self.assertIn("## 避けたほうがよい場所", text)
        self.assertIn("丙梅林などは、今日は例年の時期の外で、咲いていない見込みです。代わりに、甲梅林がよいです。", text)
        self.assertIn("今日おすすめにできる名所は1件でした。", text)
        self.assertIn("https://example.org/a", text.split("## 出典")[1])
        self.assertNotIn("好みを1つ", text)                                               # 段階57 第13部: 末尾に質問が出ない

    def test_the_next_question_is_only_one_and_last(self):
        text = self.render(self.found(recommend=[entry("甲梅林")]))
        self.assertEqual(text.count("好みを1つ教えてください"), 0)                        # 段階57 第13部: 末尾に質問が出ない

    def test_nothing_recommended_has_no_question_line(self):
        self.assertNotIn("好みを1つ", self.render(self.found()))

    def test_generic_check_passes_the_real_find_output_shape(self):
        text = self.render(self.found(recommend=[entry("甲梅林"), entry("乙梅林"), entry("丙梅林")]))
        r = V.generic_check(text)
        self.assertTrue(r["ok"], r["errors"])


class UserVisited(unittest.TestCase):
    def build(self, extra):
        recs = [{"schema": "x", "theme": "花", "name": "試験梅林", "prefecture": "神奈川県", "municipality": "小田原市", "kinds": ["梅"],
                 "season": {"text": "2月中旬〜3月上旬", "from": "2月中旬", "to": "3月上旬"}, "url": "https://rurubu.jp/andmore/article/13230", "origin": "user",
                 "read_at": "2026-11-03T07:00:00+09:00", "read_by": "agent", "host": "rurubu.jp", "publisher": "るるぶ", "class": "B"}] + extra
        return guide.build_entries(recs, {}, POLICY, guide.catalog_mod.load_policy(), reviews={}, retired={"names": {}, "urls": {}})

    def test_a_place_the_user_visited_is_recommended_in_season_with_one_source(self):
        es = [e for e in self.build([]) if e["name"] == "試験梅林"]
        e = es[0]
        self.assertTrue(e["user_visited"])
        self.assertEqual(e["approval"]["state"], "provisional")                   # 代表点がなくても、出どころ 1 件でも止めない
        found = guide.find(es, themes={"花"}, kinds=["梅"], on=date(2026, 2, 20), policy=POLICY, origin="横浜")
        self.assertEqual([x["name"] for x in found["recommend"]], ["試験梅林"])
        text = guide.render_answer(found, POLICY, origin_line=None, on=date(2026, 2, 20), themes={"花"})
        self.assertIn("あなたが行った場所", text)

    def test_out_of_season_goes_to_the_other_section(self):
        found = guide.find(self.build([]), themes={"花"}, kinds=["梅"], on=date(2026, 11, 3), policy=POLICY, origin="横浜")
        self.assertEqual(found["recommend"], [])


class Themes(unittest.TestCase):
    def test_new_flower_kinds_are_in_the_words_table(self):
        for w, kind in (("ひまわり", "ヒマワリ"), ("コスモス", "コスモス"), ("彼岸花", "ヒガンバナ"), ("スズラン", "スズラン"), ("アジサイ", "アジサイ"), ("ラベンダー", "ラベンダー")):
            themes, kinds = guide.themes_for_words([w], POLICY)
            self.assertEqual((themes, kinds), ({"花"}, [kind]), w)

    def test_a_pending_theme_can_be_recorded_but_an_unknown_word_without_records_is_not_guessed(self):
        item = {"theme": "pending:野草", "name": "試験の山", "prefecture": "神奈川県", "url": "https://example.org/yama"}
        self.assertEqual(guide.validate_item(item, POLICY), [])
        self.assertTrue(guide.validate_item({**item, "theme": "野草"}, POLICY))       # 接頭辞がなければ従来どおり表の外
        self.assertEqual(guide.themes_for_words(["野草"], POLICY)[0], None)


class PagesAreLight(unittest.TestCase):
    def test_no_cardboard_drawings_in_pages(self):
        from ikimonobiyori import guide_page, park_page
        for mod in (guide_page, park_page):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            self.assertNotIn("<img", src, mod.__name__)                           # 画像は PhotoPool の背景として 1 回だけ埋め込む
            self.assertNotIn("<svg", src, mod.__name__)                           # 手描きのイラストを出さない


class PagesAndRecords(unittest.TestCase):
    def test_subspecies_names_are_rounded_to_the_species_and_deduplicated(self):
        from ikimonobiyori import ask, park_page
        pol = ask.load_policy()["park_page"]
        facts = {"subjects": {"birds": {"candidates": [{"name": "試験の森", "park_birds": [
            {"name": "リュウキュウサンショウクイ", "taxon_id": 9, "scientific_name": "X y"}, {"name": "サンショウクイ"}, {"name": "ジョウビタキ"}]}]}}}
        c = park_page.parks(facts, pol)[0]
        self.assertEqual([b["name"] for b in c["park_birds"]], ["サンショウクイ", "ジョウビタキ"])
        self.assertIsNone(c["park_birds"][0]["taxon_id"])

    def test_policy_has_the_page_values_and_they_are_marked(self):
        from ikimonobiyori import ask, observations as O
        pol = ask.load_policy()["park_page"]
        self.assertEqual(pol["old_record_years"]["value"], 10)
        self.assertTrue(pol["rare_max_count"]["provisional"])
        opb = O.load_policy()["park_birds"]
        self.assertEqual(opb["recent_strict_days"]["value"], 7)
        self.assertLess(opb["recent_strict_days"]["value"], opb["recent_days"]["value"])
        self.assertIn("recent_season", opb["kind_labels"])

    def test_add_to_table_is_read_back_and_written_only_under_the_data_dir(self):
        guide_photos.add_to_table([{"name": "表試験花", "scientific": "Floris testus", "taxon_id": 9101, "checked_on": "2026-11-03", "image": "x"}], "花")
        row = guide_photos.load_table()["表試験花"]
        self.assertEqual((row["scientific"], row["taxon_id"]), ("Floris testus", 9101))
        self.assertNotIn("image", row)                                             # 事実だけ（画像・撮影者名は含まない）
        self.assertTrue(str(guide_photos.export_dir()).startswith(str(H.ROOT) ) is False)


class FlowerPage(unittest.TestCase):
    def test_flower_page_has_flower_words_and_no_bird_words(self):
        import test_stage29_page as TP
        from ikimonobiyori import guide_page
        es = TP.entries(("試験の苑", [TP.U1, TP.U2], TP.KINDS))
        found, parts = TP.parts_for(es)
        over = PH["html"]["by_theme"]["花"]
        page = guide_page.build_page(parts, policy=POLICY, now=TP.NOW, kind_notes=found.get("kind_notes") or [], photo_for=lambda n: (TP.META, TP.JPEG), h_over=over)
        self.assertIn("<title>花の案内</title>", page)
        self.assertNotIn(PH["html"]["headings"]["birds"], page)                    # 鳥向けの見出しは出ない
        self.assertNotIn("<title>野鳥の案内</title>", page)
        self.assertTrue(any(over["headings"][k] in page for k in ("birds", "birds_out", "birds_unknown")))     # 花向けの見出し
        self.assertIn('class="lead"', page)                                       # 結論と次の質問
        self.assertNotIn("<img", page)


if __name__ == "__main__":
    unittest.main()


class PageFollowsAnswer(unittest.TestCase):
    """利用者の指摘(2026-11-03): ページは答えの結論・順位をそのまま使う / 『今季の記録』の鳥を『記録が少ない鳥』にしない / 返事に作業の事情を書かない。"""
    ANSWER = ("野鳥のおすすめです。今日は水辺の公園が向いています。\n\nおすすめ\n① 森の池公園(試験市)\n・今の状態: x\n\n② 谷の沼(試験市)\n・今の状態: y\n\n"
              "避けたほうがよい場所\n谷戸山公園の記録は古いため外しました。\n\n確かさの補足\n今日確かめられたのは森の池公園だけです。\n\n好みを教えてください。\n")

    def facts(self):
        rec = {"name": "カルガモ", "kind": "recent", "kind_label": "今季の記録", "count": None, "lift": None, "date": "2026-10-21", "period": None, "why": "w", "publisher": "p"}
        rare = {"name": "カルガモ", "kind": "season", "kind_label": "この時期の記録", "count": 1, "lift": 1.0, "date": "2026-11-01", "period": "10・11月の記録", "why": "w", "publisher": "p"}
        mk = lambda n, birds: {"name": n, "city": "試験市", "park_birds": birds}  # noqa: E731
        return {"dates": ["2026-11-03"], "subjects": {"birds": {"candidates": [
            mk("谷戸山公園", [dict(rare, name="モズ", count=5)]), mk("谷の沼", [dict(rare, name="モズ", count=5)]), mk("森の池公園", [rec]), mk("池の端", [rare])]}}}

    def build(self, answer):
        from ikimonobiyori import ask, park_page
        pol = ask.load_policy()["park_page"]
        return park_page.build(self.facts(), policy=pol, photo_for=lambda b: None, author_re=".*", commons_source_id="c", now=None, answer=answer)

    def test_page_uses_the_answers_conclusion_ranking_and_leaves_out_avoided_parks(self):
        page, _lines, shown = self.build(self.ANSWER)
        self.assertEqual(list(shown), ["森の池公園", "谷の沼"])
        self.assertLess(page.index("今日は水辺の公園が向いています"), page.index("森の池公園"))
        self.assertIn("谷戸山公園の記録は古いため外しました", page)
        self.assertIn("今日確かめられたのは森の池公園だけです", page)
        self.assertNotIn("<h2>① 谷戸山公園", page)

    def test_without_an_answer_the_page_is_as_before(self):
        _page, _lines, shown = self.build(None)
        self.assertEqual(len(shown), 4)

    def test_a_bird_with_a_recent_record_is_not_listed_as_rare_elsewhere(self):
        page, _lines, _shown = self.build(None)
        self.assertNotIn("この時期の記録が少ない鳥: カルガモ", page)

    def test_working_notes_are_not_allowed_in_the_reply(self):
        for s in ("検査に合格しました。", "テストは実行していません。", "新しい記録が1件増えました。"):
            self.assertFalse(V.generic_check("① a\n② b\n③ c\n" + s + "\n")["ok"], s)
            facts = {"subjects": {}, "dates": [], "lines": {}}
            r = V.reply_check(s + "\n", facts)
            self.assertFalse(r["ok"], s)

    def test_prefetch_list_has_the_pictureless_birds(self):
        for n in ("カワセミ", "オナガガモ", "ヒドリガモ", "アオサギ", "コゲラ", "ハッカチョウ", "ハシブトガラス"):
            self.assertIn(n, POLICY["photos"]["prefetch"]["野鳥"])
