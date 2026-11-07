"""段階58(指示書 docs/stage58-area-and-official-fetch-instructions.md): エリア・場所の質問の堅牢化。通信しない。合成データだけ。"""
import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP, ask, areas as AR, skeleton as SK
from ikimonobiyori import ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
RULES = V.load_rules()
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def spot(name, km=20, state="見頃", date_="2026-11-05", window=("11-01", "11-30"), city="試験町", source_class="official", **kw):
    cur = {"state": state, "state_raw": state, "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{city}", "source_class": source_class,
           "freshness": "fresh", "age_days": 2, "read_at": "2026-11-07T09:00:00+09:00"} if state else None
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": "埼玉県", "current": cur, "current_unknown": cur is None, "distance_km": km,
            "typical": [{"text": "例年11月", "start": window[0], "end": window[1], "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak", **kw}


def facts_doc(subjects, dates=("2026-11-08",), now="2026-11-07T12:00:00+09:00", origin="横浜", **lines):
    return {"schema": "ikimono-ask-facts/1", "now": now, "dates": list(dates), "origin": origin, "region": "全範囲", "subjects": subjects,
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": f"{origin}からの距離で選びました。", **lines}, "summary_pages": [], "this_round": {}}


def subject(*cands):
    return {"subject": "autumn_leaves", "candidates": list(cands), "avoid": [], "nearby_out_of_region": [], "alternatives": []}


class Part1Area(unittest.TestCase):
    def test_question_forms(self):
        self.assertEqual(AR.from_question("秩父・長瀞のエリアで紅葉のおすすめを教えて"), ["秩父", "長瀞"])
        self.assertEqual(AR.from_question("飯能あたりの紅葉はどう?"), ["飯能"])
        self.assertEqual(AR.from_question("箱根周辺の紅葉"), ["箱根"])
        self.assertEqual(AR.from_question("明日 紅葉を見に行きたい"), [])

    def test_resolve_does_not_mistake_names(self):
        self.assertEqual(AR.resolve("奥秩父")["name"], "秩父")
        self.assertEqual(AR.resolve("富士山")["name"], "富士五湖")
        self.assertIsNone(AR.resolve("高尾山口駅前"))
        self.assertIsNone(AR.resolve("軽井"))                                   # 一部だけでは決めない
        d = AR.describe(["秩父市の山奥", "ありえない郷"])
        self.assertEqual(d["found"], [])
        self.assertEqual(d["unknown"][1], "ありえない郷のエリアの範囲を特定できませんでした。")
        self.assertIn("秩父", d["unknown"][0])                                  # 確実に近い名前だけ示す

    def test_members_by_city_or_radius(self):
        a = AR.resolve("秩父")
        cands = [{"name": "中津峡", "city": "秩父市中津川"}, {"name": "横浜の庭", "city": "横浜市"}, {"name": "座標の渓谷", "city": "どこか", "point": {"lat": 35.96, "lon": 138.95}},
                 {"name": "遠い山", "city": "どこか", "point": {"lat": 36.7, "lon": 139.7}}]
        self.assertEqual([c["name"] for c in AR.members(a, cands)], ["中津峡", "座標の渓谷"])

    def test_area_plan_contains_area_spots_and_passes(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"), spot("三峰山", 95, city="秩父市", elevation_m=1000), spot("宝登山", 80, city="長瀞町"),
                                                  spot("横浜の庭", 5, city="横浜市"))})
        plan = AP.build_areas(f, [AR.resolve("秩父"), AR.resolve("長瀞")], "autumn_leaves")
        self.assertEqual([s["heading"] for s in plan["segments"]], ["秩父", "長瀞"])
        names = [p["name"] for s in plan["segments"] for p in s["plan"]["picks"]]
        self.assertTrue({"中津峡", "三峰山"} & set(names))
        self.assertIn("宝登山", names)
        self.assertNotIn("横浜の庭", names)
        text = SK.compose(f, plan)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))

    def test_area_without_spot_still_gets_a_line_and_missing_area_fails(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"))})
        plan = AP.build_areas(f, [AR.resolve("秩父"), AR.resolve("飯能")], "autumn_leaves")
        text = SK.compose(f, plan)
        self.assertIn("飯能は、今年の情報が確認できていません。", text)
        self.assertTrue(V.check(text, f, RULES, plan=plan)["ok"])
        codes = [e["code"] for e in V.check("① 中津峡: 例年の見頃です。\n", f, RULES, plan=plan)["answer_errors"]]
        self.assertIn("area_missing", codes)


class Part2Official(unittest.TestCase):
    def test_official_url_is_read_and_one_level_followed(self):
        from ikimonobiyori import official_pages as OP
        calls = []

        def reader(u):
            calls.append(u)
            if u.endswith("/top"):
                return {"status": 200, "html": "x", "links": [{"url": "https://www.city.hanno.lg.jp/news", "text": "お知らせ"}, {"url": "https://www.city.hanno.lg.jp/a", "text": "市長の部屋"},
                                                              {"url": "https://other.example/x", "text": "紅葉情報"}]}
            return {"status": 200, "html": "y", "links": [{"url": "https://www.city.hanno.lg.jp/deep", "text": "お知らせ"}]}
        rows = [{"url": "https://www.city.hanno.lg.jp/top"}, {"url": "https://koyo.walkerplus.com/x"}, {"url": "https://tenki.jp/x"}]
        res = OP.read_all(rows, reader)
        self.assertEqual(calls, ["https://www.city.hanno.lg.jp/top", "https://www.city.hanno.lg.jp/news"])     # 1 階層だけ
        self.assertEqual(res["failed"], [])

    def test_cap_and_failure_is_not_retried(self):
        from ikimonobiyori import official_pages as OP
        calls = []

        def reader(u):
            calls.append(u)
            return {"status": 404}
        rows = [{"url": f"https://www.city.x{i}.lg.jp/"} for i in range(9)]
        res = OP.read_all(rows, reader)
        self.assertEqual(len(calls), AP.load_policy()["official_pages"]["max_pages"])
        self.assertEqual(res["read"], [])
        self.assertEqual(res["failed"][0]["reason"], "HTTP 404")

    def test_not_tried_wording_needs_a_real_failure(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡"))})
        self.assertEqual([e["code"] for e in V.not_tried_errors("お知らせの中身は読めていません。", f)], ["official_not_tried"])
        f["fetch"] = {"failed": [{"url": "https://www.city.x.lg.jp/", "reason": "HTTP 403"}]}
        self.assertEqual(V.not_tried_errors("公式ページを確認できていません。", f), [])

    def test_notice_appears_before_you_go(self):
        c = spot("あけぼの公園", 50, city="飯能市", notices=[{"text": "開園日等の変更(試行)", "date": "2026-11-01", "url": "https://www.city.hanno.lg.jp/news"}])
        f = facts_doc({"autumn_leaves": subject(c)})
        plan = AP.build(f, "autumn_leaves")
        text = SK.compose(f, plan)
        self.assertIn("行く前に確認すること", text)
        self.assertIn("あけぼの公園: 開園日等の変更(試行)(11/1時点の公式のお知らせ)", text)
        self.assertIn("https://www.city.hanno.lg.jp/news", text)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))

    def test_notice_is_recorded_only_from_official_pages(self):
        from ikimonobiyori import observations as O
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            O.record([{"subject": "autumn_leaves", "name": "試験の森", "state": "状態の記載なし", "notice": "一部区域の閉鎖", "state_date": "2026-11-01", "url": "https://www.city.x.lg.jp/n", "publisher": "試験市", "source_class": "official"}], env=env, now=NOW)
            self.assertEqual(O.read_records("autumn_leaves", env)[0]["notice"], "一部区域の閉鎖")


class Part3ThisYear(unittest.TestCase):
    def facts(self):
        return facts_doc({"autumn_leaves": subject(spot("今年の園", 20, city="園町"), spot("奥秩父の渓谷", 90, state=None, city="秩父市"),
                                                   spot("まつりの山", 60, state=None, city="山町", festivals=[{"name": "もみじまつり", "start": "2026-11-01", "end": "2026-11-30", "period_line": "主催者が設定した期間: まつり期間中(11/1〜11/30)"}]))})

    def test_no_info_is_out_of_picks_and_in_the_other_list(self):
        plan = AP.build(self.facts(), "autumn_leaves")
        names = [p["name"] for p in plan["picks"]]
        self.assertNotIn("奥秩父の渓谷", names)
        self.assertIn("まつりの山", names)                                      # 今年の行事は今年の情報
        self.assertEqual(plan["no_this_year"][0]["name"], "奥秩父の渓谷")
        r = next(x for x in plan["ranking"] if x["name"] == "奥秩父の渓谷")
        self.assertEqual(r["reason"], "no_this_year")
        self.assertLess(r["breakdown"]["no_this_year"], 0)

    def test_skeleton_lists_it_separately_and_passes(self):
        f = self.facts()
        plan = AP.build(f, "autumn_leaves")
        text = SK.compose(f, plan)
        self.assertIn("今年の情報が確認できていない候補", text)
        self.assertIn("・奥秩父の渓谷: 例年の見頃: 11月(今年の情報は確認できていません)", text)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))

    def test_old_year_only_basis_fails(self):
        plan = AP.build(self.facts(), "autumn_leaves")
        plan["picks"] = plan["picks"][:1]
        errs = AP.plan_errors("", plan, None, [f"① {plan['picks'][0]['name']}: 2024年の記事では見頃でした。"], V.short_names)
        self.assertIn("old_year_basis", [e["code"] for e in errs])
        errs = AP.plan_errors("", plan, None, [f"① {plan['picks'][0]['name']}: 見頃(11/5時点)。2024年の記事では遅めでした。"], V.short_names)
        self.assertNotIn("old_year_basis", [e["code"] for e in errs])

    def test_last_year_record_is_not_this_year(self):
        c = spot("古い記録の園", date_="2025-11-05")
        self.assertFalse(AP.has_this_year(c, 2026))
        self.assertTrue(AP.has_this_year(spot("新しい園"), 2026))


class Part4SnsAndExcuses(unittest.TestCase):
    def test_sns_sources_fail(self):
        for u in ("https://x.com/park/status/1", "https://www.instagram.com/p/1", "https://www.facebook.com/x", "https://www.youtube.com/watch?v=1", "https://twitter.com/a"):
            self.assertIn("sns_source", [e["code"] for e in V.source_rule_errors("出典\n" + u, RULES, "")], u)
        self.assertEqual(V.source_rule_errors("出典\nhttps://www.city.hanno.lg.jp/x", RULES, ""), [])

    def test_sns_records_are_rejected(self):
        from ikimonobiyori import observations as O
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            out = O.record([{"subject": "autumn_leaves", "name": "試験の森", "state": "見頃", "url": "https://x.com/park/status/1", "publisher": "公式X", "source_class": "official"}], env=env, now=NOW)
            self.assertEqual(out["written"], 0)
            self.assertTrue(out["rejected"])

    def test_process_excuses_fail(self):
        for s in ("このプロジェクトの方針で使っていません。", "ウェザーニュースを外して検索しました。", "検索結果だけで答えます。", "ファイルは変更せず答えます。", "そのページには触れていません。"):
            self.assertIn("process_excuse", [e["code"] for e in V.process_excuse_errors(s, RULES)], s)


class Part5Compare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def plan(self, *names):
        f = facts_doc({"autumn_leaves": subject(*[spot(n, 20 + i * 40, city=f"町{i}") for i, n in enumerate(names)])})
        return f, AP.build(f, "autumn_leaves")

    def test_needs_two_plans_and_uses_latest_values(self):
        from ikimonobiyori import compare as CP
        f, plan = self.plan("河口湖", "長瀞")
        CP.remember(plan, NOW, self.env)
        self.assertEqual(CP.table(NOW, self.env), (None, []))
        self.assertFalse(CP.can_compare(NOW, self.env))
        CP.remember(self.plan("飯能")[1], NOW + timedelta(hours=1), self.env)
        self.assertTrue(CP.can_compare(NOW + timedelta(hours=1), self.env))
        latest = {"candidates": [spot("河口湖", 80, state="色づき始め", date_="2026-11-07", city="町0"), spot("長瀞", 90, city="町1"), spot("飯能", 50, state=None, city="町2")], "avoid": []}
        text, urls = CP.table(NOW + timedelta(hours=1), self.env, facts_fn=lambda sj, ds: latest)
        self.assertIn("| 河口湖 | 色づき始め(11/7時点) |", text)                     # 計画の時点の値ではなく最新の値
        self.assertIn("| 飯能 | 確認できていません |", text)
        self.assertTrue(urls)

    def test_history_is_capped_and_expires(self):
        from ikimonobiyori import compare as CP
        for i in range(7):
            CP.remember(self.plan(f"場所{i}")[1], NOW + timedelta(minutes=i), self.env)
        self.assertEqual(len(CP.load_history(NOW + timedelta(minutes=7), self.env)), 5)
        self.assertEqual(CP.load_history(NOW + timedelta(hours=30), self.env), [])

    def test_offer_only_with_history(self):
        from ikimonobiyori import offers as OF
        self.assertEqual([o["id"] for o in OF.available({"compare_history": False})], [])
        self.assertEqual([o["id"] for o in OF.available({"compare_history": True})], ["compare_table"])
        f = ask.Flow(Path(self.tmp.name) / "w", now=NOW, env=self.env)
        f._save("facts.json", self.plan("河口湖", "長瀞")[0])
        self.assertNotIn("compare_table", [o["id"] for o in f.plan()["offers"]])     # 1 件目はまだ履歴がない
        self.assertIn("compare_table", [o["id"] for o in f.plan()["offers"]])         # 2 件目で履歴が 2 件


class Part6Names(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import place_answer as PA
        self.PA = PA
        self.c = spot("トーベ・ヤンソンあけぼの子どもの森公園", 50, city="飯能市")

    def test_variants_resolve_and_official_name_is_shown_once(self):
        f = facts_doc({"autumn_leaves": subject(self.c)})
        for q in ("トーベヤンソンあけぼの子ども森林公園", "トーベ・ヤンソンあけぼの子ども森林公園"):
            res = self.PA.plan_for([q], "autumn_leaves", f)
            self.assertEqual(res["found"][0]["candidate"]["name"], self.c["name"], q)
            self.assertEqual(res["found"][0]["section"][0], f"{self.c['name']}(正式名称は{self.c['name']}です)")
        res = self.PA.plan_for([self.c["name"]], "autumn_leaves", f)
        self.assertEqual(res["found"][0]["section"][0], self.c["name"])         # 同じならそのまま

    def test_unknown_is_not_guessed(self):
        f = facts_doc({"autumn_leaves": subject(self.c, spot("あけぼの山農業公園", 60, city="柏市"))})
        self.assertEqual(self.PA.plan_for(["ありえない森"], "autumn_leaves", f)["found"], [])
        self.assertEqual(self.PA.match("あけぼの", f["subjects"]["autumn_leaves"]["candidates"]), None)   # 2 件に当たる語は決めない

    def test_learned_alias_is_used_next_time(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            self.PA.add_alias("森の公園", "試験の森公園", env)
            self.assertEqual(self.PA.official_name("森の公園", env), "試験の森公園")
            self.assertTrue(Path(d, "ask", "place_aliases.json").is_file())


class Part7TargetWeek(unittest.TestCase):
    def test_weekend_of_the_middle_of_the_window(self):
        w = AP.target_weekend({"start": "11-11", "end": "11-30"}, date(2026, 11, 7))
        self.assertEqual(w, (date(2026, 11, 21), date(2026, 11, 22)))
        self.assertIsNone(AP.target_weekend({"start": "10-01", "end": "10-20"}, date(2026, 11, 7)))
        self.assertIsNone(AP.target_weekend(None, date(2026, 11, 7)))

    def test_line_has_label_and_uncertainty_and_only_when_no_recent_status(self):
        c = spot("試験の山", state=None, window=("11-11", "11-30"))
        line = AP.target_week_line(c, date(2026, 11, 7))
        self.assertIn("11/21〜11/22", line)
        self.assertIn("例年の見頃(試験市、公式)から", line)
        self.assertIn("今年の現況は分かりません", line)
        fresh = spot("試験の園", window=("11-11", "11-30"))
        fresh["current"]["age_days"] = 2
        self.assertIsNone(AP.target_week_line(fresh, date(2026, 11, 7)))
        old = spot("古い園", window=("11-11", "11-30"))
        old["current"]["age_days"] = 30
        self.assertIsNotNone(AP.target_week_line(old, date(2026, 11, 7)))

    def test_no_typical_no_line(self):
        c = spot("試験の山", state=None)
        c["typical"] = []
        self.assertIsNone(AP.target_week_line(c, date(2026, 11, 7)))


class Part9Skeleton(unittest.TestCase):
    def test_multi_area_split(self):
        names = AR.from_question("大菩薩嶺・西沢渓谷、秩父～長瀞～飯能、富士山周辺などで紅葉のおすすめを探しています。")
        self.assertEqual(names, ["大菩薩嶺", "西沢渓谷", "秩父", "長瀞", "飯能", "富士山"])

    def test_every_area_must_appear(self):
        plan = {"area_names": ["秩父", "飯能"]}
        self.assertEqual(AP.area_errors("秩父は見頃です。", plan), [{"code": "area_missing", "detail": "飯能"}])

    def test_default_dates(self):
        sat = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        wed = datetime(2026, 11, 4, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        g = AP.default_periods("箱根の紅葉のおすすめは", sat)
        self.assertTrue(g["defaulted"])
        self.assertEqual(g["periods"], [[date(2026, 11, 7), date(2026, 11, 8)]])          # 土日なら今日と明日
        self.assertEqual(AP.default_periods("箱根の紅葉のおすすめは", wed)["periods"], [[date(2026, 11, 7), date(2026, 11, 8)]])
        two = AP.default_periods("紅葉のおすすめを探しています", wed)
        self.assertEqual(two["periods"][1], [date(2026, 11, 14), date(2026, 11, 15)])
        self.assertFalse(AP.default_periods("明日の紅葉", wed)["defaulted"])

    def test_date_sentence_in_the_lead(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"))})
        text = SK.compose(f, AP.build(f, "autumn_leaves"), defaulted_date=True)
        self.assertIn("日付の指定がなかったので、11/8で探しました。", text)
        self.assertIn("横浜からの距離で選びました。", text)

    def test_lead_matches_the_weakest_pick(self):
        t = AP.load_policy()["skeleton"]
        self.assertEqual(SK.lead_for([{"has_current": True, "outlook": "in_peak"}, {"has_current": False, "outlook": "in_peak"}], t), t["lead_mixed"])
        self.assertEqual(SK.lead_for([{"has_current": False, "outlook": "in_peak"}], t), t["lead_no_current"])
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"), spot("三峰", 120, state=None, city="小鹿野町"))})
        plan = AP.build(f, "autumn_leaves")
        r = V.check("今週末は真っ盛りです。\n今回のおすすめ\n① 中津峡: 見頃が続いている可能性があります。例年の見頃は11月です。\n", f, RULES, plan=plan)
        self.assertIn("lead_too_assertive", [e["code"] for e in r["answer_errors"]])

    def test_third_party_status_is_not_a_reason(self):
        c = spot("紹介の渓谷", 60, city="渓町", source_class="secondary")
        self.assertFalse(AP.has_current(c))
        self.assertTrue(AP.has_this_year(c, 2026))
        off = spot("公式の園", 90, city="園町")
        off["current"]["age_days"] = 2
        f = facts_doc({"autumn_leaves": subject(c, off)})
        plan = AP.build(f, "autumn_leaves")
        self.assertEqual(plan["picks"][0]["name"], "公式の園")
        text = SK.compose(f, plan)
        self.assertIn("紹介サイトでは見頃とされています", text)
        self.assertIn("公式ではありません", text)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))

    def test_ten_failure_types_do_not_appear_in_the_skeleton(self):
        c1 = spot("甲の渓谷", 40, city="甲町", practical=[{"text": "開園 9:00〜17:00", "url": "https://www.city.a.lg.jp/p"}])
        c2 = spot("乙の山", 70, state=None, city="乙町", elevation_m=900, festivals=[{"name": "まつり", "start": "2026-11-01", "end": "2026-11-30", "period_line": "主催者が設定した期間: まつり期間中(11/1〜11/30)", "url": "https://www.city.b.lg.jp/f"}])
        c3 = spot("丙の湖", 130, city="丙町", source_class="secondary")
        c3["typical"] = []
        c3["typical_line"] = None
        c3["typical_unknown"] = True
        f = facts_doc({"autumn_leaves": subject(c1, c2, c3)})
        plan = AP.build(f, "autumn_leaves")
        text = SK.compose(f, plan)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))
        self.assertIn("例年の時期は分かりません", text)

    def test_few_candidates_line_passes(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"), spot("横瀬の滝", 92, city="横瀬町"))})
        plan = AP.build(f, "autumn_leaves")
        text = SK.compose(f, plan)
        self.assertIn(f"今年の情報が確認できた候補は{len(plan['picks'])}件です。", text)
        self.assertTrue(V.check(text, f, RULES, plan=plan)["ok"], text)

    def test_failed_answer_becomes_minimal_not_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            fl = ask.Flow(Path(d) / "w", now=NOW, env=env)
            fl._save("facts.json", facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"), spot("横瀬の滝", 92, city="横瀬町"))}))
            fl.plan()
            r, final = fl.verify("中津峡は12/31に見頃です。根拠のない文です。\n")
            self.assertFalse(r["ok"])
            self.assertNotIn("根拠のない文", final)
            self.assertIn("今回のおすすめ", final)
            self.assertTrue(Path(d, "ask", "first_check.jsonl").is_file())
            rows = Path(d, "ask", "first_check.jsonl").read_text(encoding="utf-8").splitlines()
            fl.verify("もう一度書いた文です。\n")
            self.assertEqual(len(Path(d, "ask", "first_check.jsonl").read_text(encoding="utf-8").splitlines()), len(rows))   # 初回だけ記録

    def test_cannot_answer_line(self):
        f = facts_doc({"autumn_leaves": subject(spot("中津峡", 90, city="秩父市"))})
        plan = {"subject": "unknown-shape", "picks": []}
        r = {"sentences": [], "answer_errors": []}
        self.assertEqual(ask.minimal_answer("x", f, plan, r), "今は答えを用意できません。\n")


class Part10Subjects(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import guide
        self.g = guide
        self.P = guide.load_policy()

    def test_state_note_by_subject(self):
        found = {"recommend": [{"name": "x"}]}
        self.assertIn("飛来", self.g.state_note(found, self.P, {"冬鳥"}))
        self.assertNotIn("咲き具合", self.g.state_note(found, self.P, {"冬鳥"}))
        self.assertIn("咲き具合", self.g.state_note(found, self.P, {"花"}, strict=True))
        self.assertNotIn("色づき", self.g.state_note(found, self.P, {"花"}, strict=True))
        self.assertIn("色づき", self.g.state_note(found, self.P, {"紅葉"}))
        self.assertIn("開花", self.g.state_note(found, self.P, {"野草"}))

    def test_birds_answer_with_flower_words_fails(self):
        f = facts_doc({"birds": {"candidates": []}})
        self.assertEqual([e["code"] for e in V.subject_word_errors("今年の咲き具合は分かりません。", f, RULES)], ["subject_wrong_word"])
        f = facts_doc({"flowers": {"candidates": []}})
        self.assertEqual([e["code"] for e in V.subject_word_errors("今年の飛来は分かりません。", f, RULES)], ["subject_wrong_word"])
        self.assertEqual(V.subject_word_errors("今年の咲き具合は分かりません。", f, RULES), [])

    def test_brief_answer_has_at_most_five(self):
        from datetime import date as D
        words = {"themes": ["冬鳥", "野鳥"]}
        entries = self.g.build()[0]
        found = self.g.find(entries, themes={"野鳥", "冬鳥"}, kinds=[], on=D(2026, 11, 8), policy=self.P)
        text = self.g.render_brief(found, self.P, on=D(2026, 11, 8), themes={"野鳥", "冬鳥"})
        rows = [l for l in text.splitlines() if l.startswith(("①", "②", "③", "- ")) and "の観察では" not in l]
        self.assertLessEqual(len(rows), 5)
        self.assertNotIn("参照数", text)
        self.assertNotIn("出どころの区分", text)
        self.assertNotIn("咲き具合", text)
        self.assertEqual(V.question_errors(text, RULES), [])

    def test_process_phrases(self):
        for s in ("今回は簡易な読み取りです。", "コードの文面なので、変えていません。", "コマンドの出力を一字一句そのまま出す決まりなのに、まとめていました。", "リポジトリには手を入れていません。", "出し直します。"):
            self.assertIn("process_excuse", [e["code"] for e in V.process_excuse_errors(s, RULES)], s)

    def test_bird_status_up_to_ten_and_no_excuse_in_answer_line(self):
        names = [f"種{i}" for i in range(15)]
        got = self.g.bird_status_line("2026年11月6日の野鳥公園", date(2026, 11, 7), count="38種", species=names, for_answer=True)
        self.assertIn("種9", got["line"])
        self.assertNotIn("種10", got["line"])
        self.assertNotIn("簡易な読み取り", got["line"])
        got = self.g.bird_status_line("2026年11月6日の野鳥公園", date(2026, 11, 7), count="38種", for_answer=True)
        self.assertIn("（38種）", got["line"])
        self.assertNotIn("種名", got["line"])

    def test_arrival_line(self):
        self.assertEqual(self.g.arrival_line([], self.P), "今年の飛来の記録は読めていません。")
        line = self.g.arrival_line([{"name": "本埜", "kind": "first", "date": "2026-10-25"}, {"name": "千波湖", "kind": "count", "date": "2026-11-03", "text": "12羽"}], self.P)
        self.assertIn("本埜 初飛来(10/25)", line)
        self.assertIn("千波湖 飛来数 12羽(11/3)", line)


class Part10Combo(unittest.TestCase):
    A = [{"name": "昭和記念公園", "point": {"lat": 35.71, "lon": 139.40}}, {"name": "菅生沼", "point": {"lat": 36.0, "lon": 139.95}}]
    B = [{"name": "昭和記念公園(花)", "point": {"lat": 35.71, "lon": 139.40}}, {"name": "近くの花畑", "point": {"lat": 36.05, "lon": 139.95}}, {"name": "城峯公園", "point": {"lat": 36.15, "lon": 139.05}}]

    def test_same_and_near_only(self):
        from ikimonobiyori import combo
        got = combo.find("x", "y", self.A, self.B)
        self.assertEqual(got["same"], ["昭和記念公園"])
        self.assertEqual([p["b"] for p in got["near"]], ["近くの花畑"])
        self.assertTrue(all(p["km"] <= 20 for p in got["near"]))
        self.assertNotIn("城峯公園", str(got))                                   # 70km 以上離れた組み合わせは出さない
        self.assertIn("近くの花畑", " ".join(combo.lines(got)))

    def test_none_line(self):
        from ikimonobiyori import combo
        got = combo.find("x", "y", [self.A[1]], [self.B[2]])
        self.assertEqual(combo.lines(got), ["同じ場所、または近く(約20km以内)では確認できていません。"])


class Part10Quote(unittest.TestCase):
    def test_two_long_quotes_fail(self):
        t = "「紅葉の名所として知られている公園です」と「秋には美しい景色が広がっています」。"
        self.assertEqual([e["code"] for e in V.quote_errors(t, RULES)], ["quote_repeated"])
        self.assertEqual(V.quote_errors("「◎ 真っ盛り」と「見ごろ」です。", RULES), [])


class Part8Flow(unittest.TestCase):
    def test_facts_keep_the_point_for_area_membership(self):
        from ikimonobiyori import observations as O
        s = {"id": "x", "subject": "autumn_leaves", "name": "長瀞の試験", "point": {"lat": 36.09, "lon": 139.11}, "typical": []}
        pol = O.load_policy()
        f = O.facts("autumn_leaves", region="全範囲", dates=[date(2026, 11, 8)], now=NOW, env={"IKIMONOBIYORI_DATA_DIR": tempfile.mkdtemp()}, spots_doc={"spots": [s]}, catalogs={"autumn_leaves": {"entries": []}, "flowers": {"entries": []}}, with_alternatives=False)
        c = next(x for x in f["candidates"] + f["avoid"] if x["name"] == "長瀞の試験")
        self.assertEqual(AR.members(AR.resolve("長瀞"), [c])[0]["name"], "長瀞の試験")
        self.assertEqual(O.normalize("autumn_leaves", "月の石もみじ公園 色づき進む", pol), "色づき始め")

    def test_periods_by_area_compose_and_pass(self):
        s = lambda: subject(spot("中津峡", 90, city="秩父市"), spot("宝登山", 80, city="長瀞町"))
        f = facts_doc({"autumn_leaves": s()}, dates=("2026-11-07", "2026-11-08", "2026-11-14", "2026-11-15"))
        f["periods"] = [{"dates": ["2026-11-07", "2026-11-08"], "subjects": {"autumn_leaves": s()}}, {"dates": ["2026-11-14", "2026-11-15"], "subjects": {"autumn_leaves": s()}}]
        areas = [AR.resolve("秩父"), AR.resolve("長瀞"), AR.resolve("飯能")]
        plan = AP.build_periods(f, area_rows=areas)
        text = SK.compose(f, plan, defaulted_date=True)
        for w in ("11/7・11/8のおすすめ", "11/14・11/15のおすすめ", "秩父", "長瀞", "飯能は、今年の情報が確認できていません。"):
            self.assertIn(w, text)
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], (text, V.report_lines(r)))


if __name__ == "__main__":
    unittest.main()
