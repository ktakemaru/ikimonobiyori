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


def _fest(**kw):
    f = {"id": "t-fest", "name": "試験町紅葉まつり2026", "spots": ["k-1"], "targets": ["autumn_leaves"], "organizer": "試験町観光協会",
         "organizer_class": "official", "start": "2026-11-01", "end": "2026-11-30", "url": "https://kanko.example.jp/f", "raw": []}
    f.update(kw)
    return f


class Part2NagatoroAndKitamoto(unittest.TestCase):
    TODAY = __import__("datetime").date(2026, 11, 9)

    def test_area_festival_links_to_spots_of_the_same_town_only(self):
        from ikimonobiyori import festivals as F
        doc = {"festivals": [_fest(area={"city": "試験町"})]}
        self.assertEqual([r["name"] for r in F.for_spot("k-2", self.TODAY, doc, subject="autumn_leaves", tags={"city": "試験町"})], ["試験町紅葉まつり2026"])
        self.assertEqual(F.for_spot("k-3", self.TODAY, doc, subject="autumn_leaves", tags={"city": "別の町"}), [])
        doc2 = {"festivals": [_fest()]}                                       # area のない(会場が特定の場所だけの)まつりは結ばない
        self.assertEqual(F.for_spot("k-2", self.TODAY, doc2, subject="autumn_leaves", tags={"city": "試験町"}), [])

    def test_the_real_nagatoro_festival_reaches_the_town_spots(self):
        from ikimonobiyori import festivals as F
        for sid in ("kouyou-0013", "kouyou-0063", "kouyou-0064", "kouyou-0065"):
            self.assertIn("長瀞紅葉まつり2026", [r["name"] for r in F.for_spot(sid, self.TODAY, subject="autumn_leaves", tags={"city": "長瀞町"})], sid)

    def test_nagatoro_spots_have_the_official_typical_window(self):
        from ikimonobiyori import catalog as CM
        ents = {e["id"]: e for e in CM.load_catalog("autumn_leaves")["entries"]}
        for sid in ("kouyou-0013", "kouyou-0063", "kouyou-0064", "kouyou-0065"):
            tw = ents[sid]["typical_window"]
            self.assertEqual((tw["start"], tw["end"]), ("11-11", "11-30"), sid)
            self.assertIn("nagatoro.gr.jp", tw["source_url"])
            self.assertNotIn("まつり", tw["note"])                          # 行事の期間ではない

    def test_kitamoto_facility_report_fills_the_bird_candidate_row_once(self):
        from ikimonobiyori import ask, skeleton as SK
        vc = [{"center": "kitamoto-shizen-gakushu", "name": "埼玉県自然学習センター・北本自然観察公園", "date": "2026-11-06", "state": "八ツ橋の池のコガモの群れにハシビロガモ",
               "species": ["コガモ", "ハシビロガモ"], "url": "http://www.saitama-shizen.info/today/index.html"}]
        doc = {"subjects": {"birds": {"candidates": [{"name": "北本自然観察公園", "current": None, "park_birds": []}]}}}
        ask.attach_vc_to_bird_candidates(doc, vc)
        c = doc["subjects"]["birds"]["candidates"][0]
        self.assertEqual(c["vc_report"]["line"], "北本自然観察公園は、11/6時点の発信で、コガモ・ハシビロガモ（鳥）の名があります")
        t = SK.cfg()
        self.assertEqual(SK.current_line(c, t, {}, None, "birds"), c["vc_report"]["line"])
        facts = {"visitor_centers": vc}
        self.assertEqual(SK.vc_lines(facts, [{"name": "北本自然観察公園", "city": "北本市"}], t), [])      # 施設の欄で二重に出さない

    def test_report_without_state_or_species_is_not_a_candidate_line(self):
        from ikimonobiyori import visitor_centers as V
        self.assertIsNone(V.candidate_report("試験の公園", [{"center": "x", "name": "試験の公園センター", "date": "2026-11-06", "state": None, "species": [], "url": "u"}]))


class Part3FestivalTargetsAndNames(unittest.TestCase):
    TODAY = __import__("datetime").date(2026, 11, 9)

    def test_a_chrysanthemum_show_is_not_attached_to_autumn_leaves(self):
        from ikimonobiyori import festivals as F
        doc = {"festivals": [_fest(name="試験園 菊花展2026", targets=["flowers"])]}
        self.assertEqual(F.for_spot("k-1", self.TODAY, doc, subject="autumn_leaves"), [])
        self.assertEqual(len(F.for_spot("k-1", self.TODAY, doc, subject="flowers")), 1)
        real = [r["name"] for r in F.for_spot("obs-kouyou-0002", self.TODAY, subject="autumn_leaves")]
        self.assertNotIn("三溪園 菊花展2026", real)

    def test_festival_line_starts_with_its_name_and_nameless_ones_are_dropped(self):
        from ikimonobiyori import festivals as F
        r = F.for_spot("k-1", self.TODAY, {"festivals": [_fest()]}, subject="autumn_leaves")[0]
        self.assertTrue(r["named_line"].startswith("試験町紅葉まつり2026(主催者が設定した期間): "), r["named_line"])
        one = F.for_spot("k-1", self.TODAY, {"festivals": [_fest(name="試験の学会", start="2026-11-29", end="2026-11-29")]}, subject="autumn_leaves")[0]
        self.assertEqual(one["named_line"], "試験の学会: 11/29（日）に開催（あと20日）")
        self.assertEqual(F.for_spot("k-1", self.TODAY, {"festivals": [_fest(name="")]}, subject="autumn_leaves"), [])

    def test_events_unrelated_to_the_target_days_are_not_shown(self):
        from datetime import date
        from ikimonobiyori import observations as O
        days = [date(2026, 11, 21), date(2026, 11, 22)]
        self.assertFalse(O.festival_on_dates({"start": "2026-11-29", "end": "2026-11-29"}, days))      # 対象の日にない1日だけの行事
        self.assertFalse(O.festival_on_dates({"start": "2026-11-01", "end": "2026-11-14"}, days))      # 対象の日より前に終わる
        self.assertTrue(O.festival_on_dates({"start": "2026-11-21", "end": "2026-11-23"}, days))
        self.assertTrue(O.festival_on_dates({"start": "2026-11-22", "end": "2026-11-22"}, days))

    def test_omiya_answer_lines_of_2026_11_09_are_not_repeated(self):
        """今日の動作確認の答え(2026-11-09、大宮)の実際の行。名前のない行事の行・紅葉の節の菊花展は出さない。"""
        from ikimonobiyori import skeleton as SK
        c = {"name": "試験の森", "festivals": [{"named_line": None, "period_line": "11/29（日）に開催（あと20日）"}], "current": None}
        lines = SK.pick_block({"name": "試験の森"}, 0, c, "birds", SK.cfg(), 40)
        self.assertNotIn("・11/29（日）に開催（あと20日）", lines)
        self.assertNotIn("・主催者が設定した期間: あと12日で開始(11/21〜11/23)", lines)


class Part3WordsNotSymbolsOrOriginalText(unittest.TestCase):
    """段階65 の動作確認で出た実際の行(2026-11-09 の茨城・栃木・大宮の答え)。凡例の語 1 つと短い状態の語(30字以内)だけにする。"""

    def setUp(self):
        from ikimonobiyori import observations as O
        self.O, self.pol = O, O.load_policy()

    def d(self, raw):
        return self.O.state_display(raw, "日光市観光協会", self.pol)[0]

    def test_actual_lines_of_the_answers(self):
        self.assertEqual(self.d("◯ 山内地区全体見ごろ"), "山内地区全体見ごろ")
        self.assertEqual(self.d("◎ ５割程度の色付き"), "真っ盛り（５割程度の色付き）")
        self.assertEqual(self.d("▼ 色褪せ・落葉始め 終わりです。"), "色褪せ・落葉始め（終わり）")
        out = self.d("◎ 真っ盛り ５割程度の色付きです。緑色が残っていてコントラストが綺麗です")
        self.assertNotIn("コントラスト", out)
        self.assertNotIn("緑色が残って", out)

    def test_no_symbol_no_date_and_at_most_30_chars(self):
        for raw in ("◎ 11/3現在 黄色やオレンジに染まる山肌が美しいです。落葉も始まっているのでお早目に。", "△ 11/3現在 色づきはじめました。護摩堂横見ごろ始まりました。",
                    "▼ 11/3現在 終わりです。", "園内見ごろの花: ススキ・ノギク・ツワブキ・チャノキ・イソギク・サザンカ・ほかにもたくさん"):
            out = self.O.state_display(raw, "日光市観光協会", self.pol)[0]
            self.assertTrue(out, raw)
            self.assertLessEqual(len(out), 30, out)
            self.assertFalse(any(ch in out for ch in "◎◯○〇△▼✕×"), out)
            self.assertNotIn("11/3現在", out)
            self.assertNotIn("お早目に", out)
        self.assertEqual(self.d("◎ 11/3現在 黄色やオレンジに染まる山肌が美しいです。"), "真っ盛り")      # 状態の語でない原文は写さない

    def test_avoid_lines_use_the_same_words(self):
        from ikimonobiyori import skeleton as SK
        facts = {"subjects": {"autumn_leaves": {"avoid": [{"name": "試験の沢", "current": {"state_raw": "▼ 色褪せ・落葉始め 終わりです。", "state_date": "2026-11-03",
                                                                                     "publisher": "日光市観光協会", "source_class": "official", "url": "https://x.example.jp/"}}]}}}
        self.assertEqual(SK.avoid_lines(facts, SK.cfg())[0][0], "・試験の沢: 色褪せ・落葉始め（終わり）(11/3時点、日光市観光協会)")


class Part3NoWorkMemos(unittest.TestCase):
    def test_catalog_window_note_memo_is_not_the_answer_text(self):
        from ikimonobiyori import observations as O
        tw = {"start": "11-01", "end": "11-20", "note": "茨城県(観光いばらき): 11月上旬〜中旬。大子町観光協会のページには例年の時期の記載がない"}
        self.assertEqual(O.window_note_text(tw), "茨城県(観光いばらき): 11月上旬〜中旬")
        self.assertEqual(O.window_note_text({"start": "11-01", "end": "11-20", "note": "公式ページに例年の記載なし(試験)"}), "11/1〜11/20")
        self.assertEqual(O.window_note_text({"start": "11-01", "end": "03-15", "note": "公式: 11月初旬ごろから3月中旬ごろまで観察できる(初旬は上旬として 01 にした)"}),
                         "公式: 11月初旬ごろから3月中旬ごろまで観察できる")

    def test_verifier_rejects_the_memo_sentence(self):
        import re
        from ikimonobiyori import ask_verify as V
        words = V.load_rules()["stage51"]["internal_words"] if "internal_words" in V.load_rules().get("stage51", {}) else None
        if words is None:
            from ikimonobiyori.yamlcache import load
            from pathlib import Path
            words = load(Path(V.__file__).parent / "data" / "ask" / "policy.yaml")
            words = next(v["internal_words"] for v in words.values() if isinstance(v, dict) and "internal_words" in v)
        bad = "・例年の見頃: 茨城県(観光いばらき): 11月上旬〜中旬。大子町観光協会のページにはの時期の記載がない"
        self.assertTrue(any(re.search(w, bad) for w in words))
        self.assertFalse(any(re.search(w, "・例年の見頃: 11月上旬〜中旬(茨城県)") for w in words))


class Part3NoEmptyLines(unittest.TestCase):
    def test_a_report_without_state_is_the_facility_name_only(self):
        from datetime import date
        from ikimonobiyori import visitor_centers as V
        c = {"name": "日光自然博物館"}
        self.assertEqual(V.report_sentences(c, {"date": "2026-11-06", "state": None, "species": []}), ["日光自然博物館"])

    def test_no_picks_heading_without_picks(self):
        from ikimonobiyori import skeleton as SK
        out = SK._subject_part({"candidates": []}, {"picks": []}, "flowers", SK.cfg(), 40, set(), [])
        self.assertNotIn(SK.cfg()["picks_heading"], out)

    def test_autumn_candidate_with_only_an_event_is_not_a_pick(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        it = {"subject": "autumn_leaves", "has_current": False, "has_state": False, "has_window": False, "distance_km": 6, "aim": "near"}
        self.assertFalse(AP._fillable(it, pol))
        self.assertTrue(AP._fillable(dict(it, has_window=True), pol))
        self.assertTrue(AP._fillable(dict(it, subject="flowers"), pol))

    def test_far_bird_park_without_a_record_does_not_fill_the_picks(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        self.assertFalse(AP._fillable({"subject": "birds", "has_current": False, "distance_km": 67, "aim": "trek"}, pol))
        self.assertTrue(AP._fillable({"subject": "birds", "has_current": False, "distance_km": 16, "aim": "near"}, pol))


class Part3UmeFamousSpots(unittest.TestCase):
    def test_unknown_window_spots_come_after_known_ones_up_to_five(self):
        from ikimonobiyori import season_place as SP
        rows = [{"name": f"既知{i}", "km": 10 + i, "start": "02-01", "end": "02-28", "season": "2月", "prefecture": "東京都", "from": "catalog"} for i in range(3)]
        rows += [{"name": f"不明{i}", "km": 5 + i, "start": None, "end": None, "season": None, "prefecture": "東京都", "from": "guide"} for i in range(6)]
        rows += [{"name": "梅林", "km": 120, "start": None, "end": None, "season": None, "prefecture": "茨城県", "from": "catalog",
                  "annual_events": [{"name": "梅まつり", "text": "毎年2月中旬〜3月下旬", "publisher": "試験園", "source_url": "https://x.example.jp/"}]}]
        got, _ = SP.select(rows, "横浜")
        names = [r["name"] for r in got]
        self.assertEqual(names[:3], ["既知0", "既知1", "既知2"])
        self.assertEqual(names[3], "梅林")                                # 名所カタログ・毎年の行事のある名所を先に
        self.assertEqual(len(names), 3 + 5)

    def test_kairakuen_ogose_soga_are_in_the_ume_answer(self):
        from ikimonobiyori import answer_run as AR
        import tempfile
        from datetime import datetime, timezone, timedelta
        with tempfile.TemporaryDirectory() as d:
            res = AR.run("梅の名所と時期を教えて", now=datetime(2026, 11, 9, 7, 0, tzinfo=timezone(timedelta(hours=9))), workdir=__import__("pathlib").Path(d) / "w")
        text = res["text"] if isinstance(res, dict) else str(res)
        for n in ("偕楽園", "越生梅林", "曽我梅林"):
            self.assertIn(n, text)
        self.assertIn("梅まつりは毎年2月中旬〜3月中旬(越生町観光協会)", text)
        self.assertNotIn("2027年", text)


def _kcard(title, place, cat, facts, year=None, sites=("m052",), months=()):
    return {"title": title, "category": cat, "place": place, "place_aliases": [], "facts": facts, "sites": list(sites),
            "condition": {"months": list(months), "year_dependent": bool(year), **({"year": year} if year else {})},
            "source": {"name": "試験県", "url": f"https://example.org/{title}", "checked_on": "2026-11-09"},
            "confidence": "公的資料", "rights": "確認済み。事実のみ", "usage": "ガイドの目として1行"}


class Part4MountainCards(unittest.TestCase):
    NONE = {"autumn_leaves": [], "flowers": [], "birds": []}

    def compose(self, q, cards):
        from datetime import date
        from ikimonobiyori import highlights as HL
        return HL.compose(q, today=date(2026, 11, 9), cards=cards, centers=[], reports=[], cands=self.NONE, records=self.NONE)["text"]

    def test_season_lines_come_from_the_months_in_the_cards(self):
        cs = [_kcard("試験の森", "赤城山", "季節の仕組み", ["ミズナラの林が広がる"]),
              _kcard("試験の花", "赤城山", "見頃の流れ", ["荒山は5月中旬のツツジ", "7〜8月はクロユリ・チングルマ"], months=[5, 7])]
        t = self.compose("赤城山の見どころを教えて", cs)
        self.assertIn("### 春\n・荒山: ツツジ(例年5月中旬、試験県)", t)
        self.assertIn("### 夏\n・クロユリ・チングルマ(例年7〜8月、試験県)", t)
        self.assertNotIn("荒山は5月中旬のツツジ。", t)                     # 季節の行にした事実はガイドの目に重ねない

    def test_facility_and_walk_cards_go_to_their_sections(self):
        cs = [_kcard("試験の森", "赤城山", "季節の仕組み", ["ミズナラの林が広がる"]),
              _kcard("試験VC", "赤城山", "施設", ["試験ビジターセンターは2026年9月19日にオープンした"], year=2026),
              _kcard("試験の散策路", "赤城山", "行き方・歩き方", ["大沼一周は約60分"])]
        t = self.compose("赤城山の見どころを教えて", cs)
        self.assertIn("## 施設\n・試験ビジターセンターは2026年9月19日にオープンした(試験県)", t)
        self.assertIn("## 行く前に・歩き方\n大沼一周は約60分(試験県)", t)
        self.assertNotIn("ガイドの目: ", t)

    def test_lead_is_the_whole_area_card(self):
        cs = [_kcard("滝の話", "竜頭ノ滝", "季節の仕組み", ["竜頭ノ滝は滝上の紅葉がいちばん早い"], sites=()),
              _kcard("森の話", "日光", "見頃の流れ", ["4月下旬に花が咲き始める"], sites=())]
        cs[0]["place_aliases"] = ["奥日光"]
        t = self.compose("日光の見どころを教えて", cs)
        self.assertTrue(t.splitlines()[1].startswith("日光の自然: 4月下旬に花が咲き始める"), t)

    def test_no_year_prefix_when_the_fact_has_a_year(self):
        from ikimonobiyori import knowledge as K
        c1 = _kcard("試験", "赤城山", "保全・マナー", ["新しい木道は2024年秋に完成した"], year=2026)
        self.assertNotIn("2026年の記録では", K.line_for(c1))
        c2 = _kcard("試験2", "赤城山", "保全・マナー", ["シカの食害が深刻"], year=2026)
        self.assertIn("2026年の記録では", K.line_for(c2))

    def test_site_name_is_not_matched_by_a_shorter_alias(self):
        cs = [_kcard("木曽の花", "木曽駒ヶ岳", "季節の仕組み", ["カールがお花畑になる"], sites=("m008",)),
              _kcard("箱根の鳥", "箱根", "種の解説", ["箱根だけの固有の鳥はいない"], sites=())]
        cs[1]["place_aliases"] = ["駒ヶ岳"]
        t = self.compose("木曽駒ヶ岳の見どころを教えて", cs)
        self.assertNotIn("箱根だけの固有の鳥", t)


if __name__ == "__main__":
    unittest.main()
