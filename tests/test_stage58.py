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


if __name__ == "__main__":
    unittest.main()
