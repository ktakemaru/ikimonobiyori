"""段階37(指示書 docs/stage37-H11-instructions.md 第1部): イキモノビヨリを単体で完結させる。通信しない。合成のデータだけ。
1. 手順(ikimonobiyori.ask の prepare → record → facts → verify)と文章の検査器(ikimonobiyori.ask_verify)が、
   biyori-hub の段階H8〜H10 のテスト(生き物の部分)と同じ挙動をする(ハブのテストを写した)。
2. 書き込み先の既定(環境変数・Windows・それ以外)。
3. 移行: 2 か所の記録が合わさり、重複がまとまり、元の 2 か所は変わらない。
4. 前回からの残り: 月のない日付・重複の数え方・時期を表す語の中の「見頃」・Open-Meteo の取得時刻。
5. 開発の言葉・作業の経過の文が、検査器で落ちる。"""
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import ask
from ikimonobiyori import ask_verify as V
from ikimonobiyori import migrate_data as M
from ikimonobiyori import observations as O
from ikimonobiyori import paths

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 1, 10, 0, tzinfo=JST)
D = [date(2026, 11, 2)]
RULES = V.load_rules()
SKILL = ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md"
URL = "https://kouyou.example.com/list"
AREAS = [a["id"] for a in O.load_obs_bird_areas()]

SPOTS = {"spots": [
    {"id": "t-k-1", "subject": "autumn_leaves", "name": "試験の湖", "prefecture": "神奈川県", "city": "試験町", "pages": [],
     "typical": [{"text": "11月上旬～11月下旬", "url": "https://kouyou.example.com/t", "publisher": "試験サイト"}]},
    {"id": "t-k-2", "subject": "autumn_leaves", "name": "試験の峠", "prefecture": "神奈川県", "city": "試験町", "pages": []},
    {"id": "t-k-3", "subject": "autumn_leaves", "name": "試験の温泉", "prefecture": "神奈川県", "city": "試験町", "pages": []},
] + [{"id": f"t-b-{i}", "subject": "birds", "name": f"試験の探鳥地{i}", "prefecture": "神奈川県", "city": "試験市", "bird_area": a, "pages": []}
     for i, a in enumerate(AREAS[:2])]}
CATALOGS = {"autumn_leaves": {"entries": []}, "flowers": {"entries": []}, "birds": {"entries": []}}
OBS_KW = {"spots_doc": SPOTS, "catalogs": CATALOGS}


def codes(r):
    return sorted({e["code"] for s in r["sentences"] for e in s["errors"]} | {e["code"] for e in r["answer_errors"]})


def read(name, d):
    p = Path(d) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.wd = Path(self.tmp.name) / "ask" / "q1"

    def flow(self, **kw):
        return ask.Flow(self.wd, now=NOW, env=self.env, clock=lambda: NOW, obs_kw=OBS_KW, **kw)

    def run_flow(self, subjects=("autumn_leaves",), fetcher=None):
        return ask.run({"subjects": list(subjects), "region": "神奈川", "dates": D}, workdir=self.wd, fetcher=fetcher, now=NOW,
                       env=self.env, clock=lambda: NOW, obs_kw=OBS_KW)

    def fresh_records(self):
        O.record([{"subject": "autumn_leaves", "spot": s, "state": "色づき始め", "state_date": "2026-11-01", "url": URL, "publisher": "試験サイト",
                   "source_class": "secondary"} for s in ("t-k-1", "t-k-2", "t-k-3")], env=self.env, now=NOW)


def reader(state="色づき始め", sdate="2026-10-31", url=URL, spot="t-k-1"):
    seen = []

    def fetcher(plan_doc):
        seen.append(plan_doc)
        return [{"subject": "autumn_leaves", "spot": spot, "state": state, "state_date": sdate, "url": url, "publisher": "試験サイト",
                 "source_class": "secondary"}], {"read": [{"url": url, "publisher": "試験サイト"}], "failed": []}
    return fetcher, seen


# ---- 1. 手順(ハブの test_stageH8 / H9 / H10 の生き物の部分を写した) ----

class FlowOrder(Base):
    def test_order_when_records_are_old(self):
        fetcher, seen = reader()
        f, doc = self.run_flow(fetcher=fetcher)
        self.assertEqual([c["step"] for c in f.calls], ["prepare", "record", "facts"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(doc["lines"]["fetch"], ["11/1 に 試験サイト の 1ページを読み直し、新しい記録が 1件増えました。"])
        calls = read("calls.json", self.wd)
        self.assertTrue(all(c["module"] == "ikimonobiyori.ask" and "biyori-hub" not in json.dumps(c) for c in calls))
        self.assertTrue(all(Path(c["data_dir"]) == Path(self.tmp.name) for c in calls))

    def test_fresh_records_do_not_fetch(self):
        self.fresh_records()
        fetcher, seen = reader()
        f, doc = self.run_flow(fetcher=fetcher)
        self.assertEqual([c["step"] for c in f.calls], ["prepare", "facts"])
        self.assertEqual(seen, [])
        self.assertEqual(doc["lines"]["fetch"], ["記録が新しいため、今回は読み直していません。"])

    def test_outputs_have_no_requests_to_the_user(self):
        f, doc = self.run_flow(fetcher=None)
        texts = (self.wd / "plan.json").read_text(encoding="utf-8") + (self.wd / "facts.json").read_text(encoding="utf-8")
        for w in RULES["forbidden_phrases"]:
            self.assertNotIn(w, texts)

    def test_dates(self):
        self.assertEqual(ask.parse_dates("明日", NOW), [date(2026, 11, 2)])
        self.assertEqual(ask.parse_dates("今週末", datetime(2026, 10, 29, tzinfo=JST)), [date(2026, 10, 31), date(2026, 11, 1)])
        self.assertEqual(ask.parse_dates("今週末", NOW), [date(2026, 11, 1)])
        self.assertEqual(ask.parse_dates("2026-11-03", NOW), [date(2026, 11, 3)])

    def test_scope_line_names_the_subjects(self):
        f, doc = self.run_flow(subjects=("autumn_leaves", "flowers", "birds"))
        self.assertEqual(doc["lines"]["scope"], "紅葉・花・野鳥のおすすめです(横浜などの出発地から行ける範囲)。")
        self.assertEqual(set(doc["subjects"]), {"autumn_leaves", "flowers", "birds"})


class Reread(Base):
    """ハブ H9 穴1: この回に新しい記録が 0 件なら「読み直しました」が出ない。"""

    def test_no_new_records_no_reread_line(self):
        fetcher, _ = reader()
        self.run_flow(fetcher=fetcher)
        self.wd = Path(self.tmp.name) / "ask" / "q2"
        f, doc = self.run_flow(fetcher=fetcher)                 # 同じ事実をもう一度 → 新しい記録 0
        self.assertEqual(read("records.json", self.wd)[0]["written"], 0)
        self.assertEqual(doc["lines"]["fetch"], ["11/1 に 試験サイト を読みに行きましたが、新しい情報は取れませんでした。"])

    def test_fetch_log_alone_is_not_evidence(self):
        rnd = ask.this_round([], {"read": [{"url": "https://a.example/", "publisher": "A"}]}, {"needs_fetch": True})
        self.assertEqual(ask.fetch_line(rnd, NOW), ["11/1 に A を読みに行きましたが、新しい情報は取れませんでした。"])

    def test_same_publisher_list_page_is_not_listed_as_nothing_new(self):
        rec = [{"by_url": [{"url": "https://pref.example.jp/r810.html", "publisher": "試験県(センター)", "written": 10, "duplicates": 0}]}]
        log = {"read": [{"url": "https://pref.example.jp/top.html", "publisher": "試験県"}, {"url": "https://walker.example.jp/", "publisher": "試験ウォーカー"}]}
        self.assertEqual(ask.fetch_line(ask.this_round(rec, log), NOW),
                         ["11/1 に 試験県(センター) の 1ページを読み直し、新しい記録が 10件増えました。", "試験ウォーカー も読みに行きましたが、新しい情報は取れませんでした。"])

    def test_failed_pages_are_listed(self):
        rnd = ask.this_round([], {"failed": [{"url": "https://b.example/", "reason": "403"}]}, {"needs_fetch": True})
        self.assertEqual(ask.fetch_line(rnd, NOW)[-1], "読めなかったページ(ご自身で開いてください): https://b.example/")

    def facts(self, new):
        return {"now": NOW.isoformat(), "subjects": {}, "this_round": {"new_records": new, "attempted": True, "needs_fetch": True},
                "lines": {"fetch": [f"11/1 に tenki.jp の 1ページを読み直し、新しい記録が {new}件増えました。"] if new else []}}

    def test_checker_drops_reread_claim_without_new_records(self):
        self.assertIn("reread_without_new_records", codes(V.check("11/1 に tenki.jp のページを読み直しました。\n", self.facts(0), RULES)))
        r = V.check("11/1 に tenki.jp の 1ページを読み直し、新しい記録が 3件増えました。\n", self.facts(3), RULES)
        self.assertNotIn("reread_without_new_records", codes(r))
        self.assertNotIn("reread_not_from_record", codes(r))
        self.assertIn("reread_not_from_record", codes(V.check("11/1 に tenki.jp ほか3ページを読み直しました。\n", self.facts(3), RULES)))

    def test_checker_drops_answer_without_fetch_when_records_are_old(self):
        f, doc = self.run_flow(fetcher=None)
        self.assertFalse(doc["this_round"]["attempted"])
        r = V.check("今回は新しく調べ直さず、今朝までの記録で答えています。\n", doc, RULES)
        self.assertIn("fetch_skipped", codes(r))
        self.assertIn("forbidden_phrase", codes(r))


class InatPlan(Base):
    """ハブ H10: 野鳥の iNaturalist の集計の取り直し。新しければ呼ばない。上限を超えない。計測フックの下だけ。"""

    def test_stale_areas_are_planned_within_the_limit(self):
        f, doc = self.run_flow(subjects=("birds",))
        plan = read("plan.json", self.wd)
        ir = plan["inat_refresh"]
        self.assertTrue(ir["needed"])
        self.assertEqual(sorted(ir["areas"]), sorted(AREAS[:2]))
        self.assertLessEqual(ir["max_requests"], O.load_policy()["inat_refresh"]["max_requests_per_question"]["value"])
        self.assertEqual(ir["max_requests"], 4)
        c = [c for c in read("calls.json", self.wd) if c["step"] == "inat_refresh"]
        self.assertEqual(c[-1]["skipped"], "no_measure_hook")                       # 単体では取り直さない(計測フックがない)
        self.assertEqual(doc["inat_refresh"]["reason"], "no_measure_hook")

    def test_not_for_other_subjects(self):
        self.run_flow(subjects=("autumn_leaves",))
        self.assertNotIn("inat_refresh", [c["step"] for c in read("calls.json", self.wd)])

    def test_under_test_the_real_refresh_never_launches(self):
        f = self.flow()
        f.prepare(["birds"], "神奈川", D)
        with mock.patch.object(O, "inat_refresh", side_effect=AssertionError("起動してはいけない")):
            out = f.inat_refresh()
        self.assertEqual(out, {"ran": False, "reason": "under_test"})

    def test_refresh_with_an_injected_http_runs_and_is_recorded(self):
        body = {"total_results": 1, "page": 1, "per_page": 200, "results": [{"count": 20, "taxon": {"id": 1, "name": "Anas crecca",
                                                                                                "preferred_common_name": "コガモ"}}]}
        calls = []

        def http(url):
            calls.append(url)
            return 200, json.dumps(body, ensure_ascii=False), {}
        f = self.flow()
        f.prepare(["birds"], "神奈川", D)
        out = f.inat_refresh(http_get=http, sleep=lambda s: None, clock=lambda: NOW)
        f.save_calls()
        self.assertTrue(out["ran"])
        self.assertEqual(out["rc"], 0)
        self.assertLessEqual(len(calls), 4)
        c = [c for c in read("calls.json", self.wd) if c["step"] == "inat_refresh"][-1]
        self.assertEqual((c["max_requests"], sorted(c["areas"])), (4, sorted(AREAS[:2])))
        self.assertEqual(read("inat_refresh.json", self.wd)["ran"], True)
        self.wd2 = self.wd
        doc = f.facts(["birds"], "神奈川", D)
        self.assertTrue(doc["inat_refresh"]["ran"])

    def test_failure_does_not_stop(self):
        def http(url):
            return 503, "x", {}
        f = self.flow()
        f.prepare(["birds"], "神奈川", D)
        out = f.inat_refresh(http_get=http, sleep=lambda s: None, clock=lambda: NOW)
        self.assertEqual(out["rc"], 5)
        doc = f.facts(["birds"], "神奈川", D)
        self.assertEqual(doc["schema"], "ikimono-ask-facts/1")
        self.assertTrue(any("取り直しは失敗" in n for n in doc["notes"]))

    def test_fresh_areas_are_not_refreshed(self):
        with mock.patch.object(O, "inat_refresh_plan", return_value={"needed": False, "areas": [], "fresh": [{"area": AREAS[0], "state": "fresh"}]}):
            f, doc = self.run_flow(subjects=("birds",))
        c = next(c for c in read("calls.json", self.wd) if c["step"] == "inat_refresh")
        self.assertEqual((c["skipped"], c["fresh"]), ("fresh", [AREAS[0]]))
        self.assertEqual(read("plan.json", self.wd)["inat_refresh"], {"ran": False, "reason": "fresh"})


class Cli(Base):
    def test_prepare_record_facts_verify_from_the_command_line(self):
        with mock.patch.dict("os.environ", self.env):
            for argv in (["prepare", "--out-dir", str(self.wd), "--subject", "autumn_leaves", "--region", "神奈川", "--when", "2026-11-02",
                          "--now", NOW.isoformat()],):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(ask.main(argv), 0)
            batch = self.wd / "reads.json"
            batch.write_text(json.dumps([{"subject": "autumn_leaves", "name": "試験の滝", "city": "試験町", "state": "01日現在 色づき始め",
                                          "url": URL, "publisher": "試験サイト", "source_class": "secondary"}], ensure_ascii=False), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ask.main(["record", "--out-dir", str(self.wd), "--batch", str(batch)]), 0)
            self.assertEqual(json.loads(out.getvalue())["written"], 1)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ask.main(["facts", "--out-dir", str(self.wd)]), 0)
            doc = json.loads(out.getvalue())
            self.assertEqual(doc["dates"], ["2026-11-02"])                              # prepare の値を使う
            ans = self.wd / "answer.txt"
            ans.write_text("テストの結果、コードは変更していません。\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(ask.main(["verify", "--out-dir", str(self.wd), "--text", str(ans)]), 1)
            self.assertIn("dev_term", codes(read("check.json", self.wd)))
        steps = [c["step"] for c in read("calls.json", self.wd)]
        self.assertEqual(steps, ["prepare", "record", "facts", "verify"])


# ---- 検査器(ハブの test_stageH8 Checker・H9 Hole2・H10 R4Reading を写した) ----

def spot(name, state=None, sdate=None, typ="11月上旬～11月下旬", cls="secondary", fresh="fresh", url="https://kouyou.example.com/k", **kw):
    cur = None if state is None else {"state": state, "state_raw": state, "state_date": sdate, "publisher": "試験サイト", "url": url,
                                      "source_class": cls, "freshness": fresh}
    return {"id": "t-" + name, "name": name, "city": "試験町", "current": cur, "typical": [{"text": typ, "url": "https://kouyou.example.com/t", "publisher": "試験サイト"}],
            "events": [], "reason_labels": [], "history": [], **kw}


def facts_doc(cands, avoid=(), alts=()):
    return {"now": NOW.isoformat(), "dates": ["2026-11-02"], "region": "神奈川",
            "subjects": {"autumn_leaves": {"subject": "autumn_leaves", "candidates": list(cands), "avoid": list(avoid), "alternatives": list(alts),
                                           "nearby_out_of_region": []}},
            "lines": {"fetch": ["11/1 に 試験サイト ほか2ページを読み直しました。"]}, "summary_pages": []}


FACTS = facts_doc([spot("試験の湖", "色づき始め", "2026-10-31"), spot("試験の峠", "色づき始め", "2026-10-31", typ="10月中旬～11月下旬"),
                   spot("試験の温泉", "色づき始め", "2026-10-31", typ="11月中旬～12月上旬")],
                  avoid=[spot("試験の寺", "青葉", "2026-10-31", typ="11月下旬～12月中旬")],
                  alts=[{"name": "試験の庭園", "events": [{"name": "試験の菊花展", "start": "2026-10-31", "end": "2026-11-23", "url": "https://hana.example.org/"}]}])

GOOD = """明日(11/2)の試験県の紅葉は、まだ早めです。
試験サイトの10/31時点の情報では、多くの名所が「色づき始め」でした。
① 試験の峠: 色づき始め(10/31時点、試験サイト)。例年の見頃は10月中旬～11月下旬で、今がいちばん近い場所です。
② 試験の湖: 色づき始め(10/31時点)。例年の見頃は11月上旬～11月下旬で、これから進みます。
③ 試験の温泉: 色づき始め。例年の見頃は11月中旬～12月上旬です。
避けたほうがよい場所: 試験の寺は青葉でした。試験の庭園の試験の菊花展(10/31～11/23)なら楽しめます。
どちらを重視しますか?
https://kouyou.example.com/k
"""


class Checker(unittest.TestCase):
    def errs(self, text, facts=FACTS, gaz=("試験の谷", "架空市")):
        return V.check(text, facts, RULES, gazetteer=gaz)

    def test_good_answer_passes(self):
        r = self.errs(GOOD)
        self.assertTrue(r["ok"], V.report_lines(r))
        self.assertEqual(len(r["candidates_mentioned"]), 3)

    def test_unknown_date_state_place_url_number_period_fail(self):
        for bad, code in (("試験の湖は11/9に見頃です。", "unknown_date"), ("試験の湖は落葉でした。", "unknown_state"),
                          ("試験の谷も色づき始めです。", "unknown_place"), ("詳しくは https://evil.example.net/x を見てください。", "unknown_url"),
                          ("試験の湖は標高1234mです。", "unknown_number"), ("例年の見頃は1月上旬です。", "unknown_period")):
            self.assertIn(code, codes(self.errs(GOOD + bad + "\n")), bad)

    def test_peak_claim_needs_a_peak_record_and_a_fresh_one_for_now(self):
        self.assertIn("unsupported_peak_claim", codes(self.errs(GOOD + "試験の湖はいま見頃です。\n")))
        f = facts_doc([spot("試験の湖", "見頃", "2026-09-01", fresh="very_stale"), spot("試験の峠", "色づき始め", "2026-10-31"),
                       spot("試験の温泉", "色づき始め", "2026-10-31")])
        self.assertIn("old_record_as_now", codes(self.errs("試験の湖はいま見頃です。試験の峠、試験の温泉も。\n", facts=f)))

    def test_r10_phrases_and_internal_terms_fail(self):
        for bad in ("紅葉のデータが古く、おすすめを出せません。", "地域に合う材料もありません。", "更新は私からは始めません。",
                    "実行するなら ! を付けてください。", "スナップショットが古いです。", "status_log を読みました。", "承認してください。"):
            r = self.errs(GOOD + bad + "\n")
            self.assertFalse(r["ok"], bad)
            self.assertTrue({"forbidden_phrase", "internal_term"} & set(codes(r)), bad)

    def test_each_candidate_block_needs_a_typical_period(self):
        bad = GOOD.replace("③ 試験の温泉: 色づき始め。例年の見頃は11月中旬～12月上旬です。", "③ 試験の温泉: 色づき始め。")
        self.assertIn("no_typical_in_candidate", codes(self.errs(bad)))

    def test_too_few_candidates_and_too_long(self):
        self.assertIn("too_few_candidates", codes(self.errs("① 試験の湖: 色づき始め(10/31時点)。\n")))
        self.assertIn("too_long", codes(self.errs(GOOD + "あ" * RULES["max_chars"])))

    def test_strip_removes_only_bad_sentences_and_keeps_the_answer(self):
        text = GOOD + "試験の湖は落葉でした。おすすめを出せません。\n"
        out = V.strip(text, self.errs(text))
        self.assertNotIn("落葉", out)
        self.assertNotIn("出せません", out)
        self.assertIn("① 試験の峠", out)
        self.assertTrue(V.check(out, FACTS, RULES, gazetteer=("試験の谷",))["ok"])


class DevWords(unittest.TestCase):
    """5: 開発の言葉・作業の経過の文が落ちる(単体の試用 2026-11-01 で出た言い方)。"""

    def test_dev_terms_and_progress_sentences_fail(self):
        for bad in ("コードは変更していないので、テストは実行していません。", "作業メモ: 記録を足しました。", "記録済みの名所です。",
                    "スキルの手順で調べました。", "コマンドで確かめました。", "検査が通ったので、その答えを出します。",
                    "あとは答えを書くだけです。", "花・野鳥は、今回は取りに行っていません。"):
            r = V.check(GOOD + bad + "\n", FACTS, RULES)
            self.assertFalse(r["ok"], bad)
            self.assertTrue({"forbidden_phrase", "dev_term"} & set(codes(r)), bad)

    def test_words_that_only_contain_the_letters_pass(self):
        f = json.loads(json.dumps(FACTS))
        f["subjects"]["autumn_leaves"]["candidates"][0]["events"] = [{"name": "試験のフォトコンテスト"}]
        r = V.check(GOOD + "試験の湖では試験のフォトコンテストがあります。\n", f, RULES)
        self.assertNotIn("dev_term", codes(r))

    def test_skill_states_the_rule(self):
        t = SKILL.read_text(encoding="utf-8")
        for w in ("ikimonobiyori.ask prepare", "ikimonobiyori.ask record", "ikimonobiyori.ask facts", "ikimonobiyori.ask verify",
                  "web-fetch", "開発の言葉", "docs/ask-rubric.md"):
            self.assertIn(w, t)


def bird(name, closed=None, season="この時期に見られる鳥: iNaturalist の過去5年の記録では、コガモ・オナガガモが多く記録されています"):
    return {"id": "t-" + name, "name": name, "city": "試験市", "current": {"state": "状態不明", "state_raw": "冬鳥のコガモが増えて来ました",
            "state_date": "2026-10-21", "publisher": "試験の遊水地", "url": "https://birds.example.org/", "source_class": "official", "freshness": "stale"},
            "typical": [], "events": [], "reason_labels": [], "history": [], "season_line": season, "season_birds": [],
            "relation_label": None, "closed_on": closed or []}


BFACTS = {"now": NOW.isoformat(), "dates": ["2026-11-02"], "region": "神奈川", "this_round": {"new_records": 1, "attempted": True, "needs_fetch": True},
          "lines": {"fetch": ["11/1 に 試験の遊水地 の 1ページを読み直し、新しい記録が 1件増えました。"]},
          "subjects": {"birds": {"subject": "birds", "avoid": [], "alternatives": [], "nearby_out_of_region": [], "candidates": [
              bird("試験の遊水地"), bird("試験の森"),
              bird("試験の公園", closed=[{"date": "2026-11-02", "closed": True, "facility": "試験の里", "line": "11/2(月)は試験の里が休みです(公園には入れます)。"}])]}}}

GOOD_BIRDS = """明日(11/2)は、冬鳥のカモ類が見られ始める時期です。
① 試験の遊水地: この時期に見られる鳥は、iNaturalist の過去5年の記録ではコガモ・オナガガモが多く記録されています。10/21時点で「冬鳥のコガモが増えて来ました」(試験の遊水地)。
② 試験の森: この時期に見られる鳥は、コガモ・オナガガモです(iNaturalist の過去5年の記録)。
③ 試験の公園: この時期に見られる鳥は、コガモ・オナガガモです。明日(11/2・月)は試験の里が休みです(公園には入れます)。
11/1 に 試験の遊水地 の 1ページを読み直し、新しい記録が 1件増えました。
"""


class Birds(unittest.TestCase):
    def test_good_bird_answer_passes(self):
        r = V.check(GOOD_BIRDS, BFACTS, RULES)
        self.assertTrue(r["ok"], V.report_lines(r))

    def test_typical_phrase_dropped_and_season_required(self):
        bad = GOOD_BIRDS.replace("① 試験の遊水地: この時期に見られる鳥は、", "① 試験の遊水地: 例年の見頃: 分かりません。")
        c = codes(V.check(bad, BFACTS, RULES))
        self.assertIn("birds_typical_phrase", c)
        self.assertIn("no_season_birds_in_candidate", c)

    def test_words_inside_urls_are_not_internal_terms(self):
        facts = json.loads(json.dumps(BFACTS))
        facts["subjects"]["birds"]["candidates"][0]["inat"] = {"url": "https://api.inaturalist.org/v1/observations/species_counts?lat=35.4"}
        r = V.check("出典: https://api.inaturalist.org/v1/observations/species_counts?lat=35.4\n", facts, RULES)
        self.assertNotIn("internal_term", codes(r))
        self.assertIn("internal_term", codes(V.check("observations の記録です。\n", facts, RULES)))

    def test_closed_day_must_be_stated(self):
        bad = GOOD_BIRDS.replace("明日(11/2・月)は試験の里が休みです(公園には入れます)。", "明日11/2は第1月曜にあたります。")
        self.assertIn("closed_not_stated", codes(V.check(bad, BFACTS, RULES)))


def cand(name, events=(), last_year=(), unknown=True):
    return {"id": name, "name": name, "typical_unknown": unknown, "current": None, "history": [],
            "typical_alternatives": {"events": [{"name": e, "start": "2026-10-31", "end": "2026-11-23"} for e in events],
                                     "last_year": [{"state": "見頃", "date": d, "year": int(d[:4])} for d in last_year],
                                     "event_periods_not_typical": []} if unknown else None}


def r4(text, cands):
    mat = V.Material({"now": NOW.isoformat(), "subjects": {"flowers": {"subject": "flowers", "candidates": cands}}}, RULES)
    return [e["code"] for e in V.typical_unknown_errors(text, mat, RULES)]


class R4Reading(unittest.TestCase):
    def test_unknown_without_alternative_fails_when_material_has_one(self):
        self.assertEqual(r4("① 試験の庭園\n・例年の時期は分かりません。\n", [cand("試験の庭園", events=["試験の菊まつり"])]),
                         ["typical_unknown_without_alternative"])

    def test_unknown_with_this_years_event_or_last_year_passes(self):
        c = [cand("試験の庭園", events=["試験の菊まつり"])]
        self.assertEqual(r4("① 試験の庭園\n・例年の時期は分かりません(今年の行事「試験の菊まつり」は10/31〜11/23)。\n", c), [])
        self.assertEqual(r4("試験の花畑は、例年の時期は分かりません。昨年は11/4に見頃でした。", [cand("試験の花畑", last_year=["2025-11-04"])]), [])

    def test_unknown_without_any_material_passes_by_stating_it(self):
        self.assertEqual(r4("試験の山の上は、例年の時期は分かりません。", [cand("試験の山の上")]), [])

    def test_units_are_separate(self):
        c = [cand("試験の庭園", events=["試験の菊まつり"]), cand("試験の花畑", events=["試験のコスモスまつり"])]
        text = "① 試験の庭園\n・例年の時期は分かりません。\n\n② 試験の花畑\n・例年の時期は分かりません(今年の行事「試験のコスモスまつり」は10/31〜11/23)。\n"
        self.assertEqual(r4(text, c), ["typical_unknown_without_alternative"])

    def test_rubric_body_has_the_reading(self):
        t = (ROOT / "docs" / "ask-rubric.md").read_text(encoding="utf-8")
        row = next(line for line in t.splitlines() if line.startswith("| R4 |"))
        for w in ("例年の時期は分かりません", "今年の行事の期間", "昨年", "R4 を満たす", "候補を答えから外さない", "この時期に見られる鳥"):
            self.assertIn(w, row)
        self.assertIn("ここに書いていない読み方を、採点者に添えない", t)
        r10 = next(line for line in t.splitlines() if line.startswith("| R10 |"))
        for w in ("テスト", "コード", "作業メモ", "記録済み", "スキル", "コマンド", "あとは答えを書くだけです"):
            self.assertIn(w, r10)


# ---- 2. 書き込み先の既定 ----

class DataDir(unittest.TestCase):
    def test_env_then_platform_default(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(paths.data_dir({"IKIMONOBIYORI_DATA_DIR": str(d / "x")}), d / "x")
        self.assertEqual(paths.data_dir({"LOCALAPPDATA": str(d)}, os_name="nt"), d / "ikimonobiyori")
        self.assertEqual(paths.data_dir({}, os_name="nt", home=d), d / "AppData" / "Local" / "ikimonobiyori")
        self.assertEqual(paths.data_dir({}, os_name="posix", home=d), d / ".local" / "share" / "ikimonobiyori")
        self.assertEqual(paths.data_dir({"IKIMONOBIYORI_DATA_DIR": "", "LOCALAPPDATA": str(d)}, os_name="nt"), d / "ikimonobiyori")

    def test_default_is_outside_the_repository(self):
        self.assertFalse(str(paths.default_data_dir({})).startswith(str(ROOT)))

    def test_tests_never_write_to_the_user_location(self):
        import os
        self.assertTrue(os.environ.get("IKIMONOBIYORI_DATA_DIR"))
        self.assertNotEqual(paths.data_dir(), paths.default_data_dir())
        self.assertEqual(H.child_env().get("IKIMONOBIYORI_DATA_DIR"), os.environ["IKIMONOBIYORI_DATA_DIR"])


# ---- 3. 移行 ----

def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


class Migrate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.a, self.b, self.t = self.tmp / "standalone", self.tmp / "hub", self.tmp / "new"
        row = {"subject": "flowers", "spot": "t-h-1", "state": "コスモス: 見頃", "state_date": "2026-10-31", "url": "https://a.example/",
               "source_class": "secondary", "read_at": "2026-10-31T09:00:00+09:00"}
        H.write(self.a / "cache" / "k1.json", {"body": "a"})
        H.write(self.b / "cache" / "k2.json", {"body": "b"})
        self.lines(self.a / "observations" / "flowers.jsonl", [row])
        self.lines(self.b / "observations" / "flowers.jsonl", [dict(row, url="https://b.example/", read_at="2026-11-01T08:00:00+09:00"),
                                                                dict(row, state="コスモス: 見頃過ぎ", read_at="2026-11-01T08:00:00+09:00")])
        self.lines(self.a / "status_log" / "autumn_leaves.jsonl", [{"source": "s", "state": "◯", "read_at": "2026-10-30T09:00:00+09:00"}])
        self.lines(self.b / "status_log" / "autumn_leaves.jsonl", [{"source": "s", "state": "◯", "read_at": "2026-10-30T09:00:00+09:00"},
                                                                    {"source": "s", "state": "◎", "read_at": "2026-10-31T09:00:00+09:00"}])
        H.write(self.b / "observations" / "inat_index.json", {"schema": "ikimono-inat-index/1", "areas": {"x": [{"center": "2026-11-02", "fetched_at": "2026-11-01T09:00:00+09:00"}]}})

    def lines(self, p, rows):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def run_m(self, *extra):
        with mock.patch.dict("os.environ", {"IKIMONOBIYORI_DATA_DIR": str(self.t)}), redirect_stdout(io.StringIO()) as out:
            rc = M.main(["--from", str(self.a), "--from", str(self.b), *extra])
        return rc, json.loads(out.getvalue())

    def test_dry_run_writes_nothing(self):
        rc, st = self.run_m("--dry-run")
        self.assertEqual(rc, 0)
        self.assertFalse(self.t.exists())
        self.assertEqual(st["observations_total"], {"lines_in": 3, "written": 2, "merged_duplicates": 1})

    def test_merge_dedupes_and_keeps_the_sources(self):
        before = (tree_hash(self.a), tree_hash(self.b))
        rc, st = self.run_m()
        self.assertEqual(rc, 0)
        self.assertEqual(before, (tree_hash(self.a), tree_hash(self.b)))              # 元の 2 か所は変わらない
        self.assertTrue((self.t / "cache" / "k1.json").is_file() and (self.t / "cache" / "k2.json").is_file())
        env = {"IKIMONOBIYORI_DATA_DIR": str(self.t)}
        rows = O.read_records("flowers", env)
        self.assertEqual([r["state"] for r in rows], ["コスモス: 見頃", "コスモス: 見頃過ぎ"])
        self.assertEqual(rows[0]["last_confirmed_at"], "2026-11-01T08:00:00+09:00")    # 重複は「最後に確かめた日時」に
        sl = (self.t / "status_log" / "autumn_leaves.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(sl), 2)
        self.assertEqual(st["jsonl_total"]["merged_duplicates"], 1)
        self.assertIn("x", json.loads((self.t / "observations" / "inat_index.json").read_text(encoding="utf-8"))["areas"])
        rc, st2 = self.run_m()                                                           # もう一度実行しても増えない
        self.assertEqual(len(O.read_records("flowers", env)), 2)
        self.assertEqual(st2["copied"], 0)

    def test_refuses_overlapping_folders(self):
        with mock.patch.dict("os.environ", {"IKIMONOBIYORI_DATA_DIR": str(self.a)}), redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(M.main(["--from", str(self.a)]), 2)


# ---- 4. 前回からの残り ----

class Leftovers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def test_1_day_only_dates_take_the_nearest_past_month(self):
        self.assertEqual(O.state_date_from_text("01日現在 色づき始め", "2026-11-01T10:00:00+09:00"), "2026-11-01")
        self.assertEqual(O.state_date_from_text("31日現在", "2026-11-01T10:00:00+09:00"), "2026-10-31")
        self.assertEqual(O.state_date_from_text("31日時点", "2026-03-02T10:00:00+09:00"), "2026-01-31")    # 2 月に 31 日はない
        self.assertEqual(O.state_date_from_text("10月8日現在", "2026-11-01T10:00:00+09:00"), "2026-10-08")  # 月つきは従来どおり
        out = O.record([{"subject": "autumn_leaves", "name": "試験の滝", "state": "01日現在 色づき始め", "url": URL, "source_class": "secondary"}],
                       env=self.env, now=NOW)
        r = out["records"][0]
        self.assertEqual((r["state_date"], r["state_date_inferred"]), ("2026-11-01", "month_from_read_date"))
        out = O.record([{"subject": "autumn_leaves", "name": "試験の沢", "state": "色づき始め", "state_date_text": "31日現在", "url": URL,
                         "source_class": "secondary"}], env=self.env, now=NOW)
        self.assertEqual(out["records"][0]["state_date"], "2026-10-31")

    def rec(self, url, sdate="2026-10-31", state="色づき始め"):
        return {"subject": "autumn_leaves", "spot": "t-k-1", "state": state, "state_date": sdate, "url": url, "publisher": "試験サイト",
                "source_class": "secondary"}

    def test_2_same_fact_from_another_page_or_day_is_not_new(self):
        r1 = O.record([self.rec("https://a.example/")], env=self.env, now=NOW)
        r2 = O.record([self.rec("https://b.example/")], env=self.env, now=NOW + timedelta(days=1))
        self.assertEqual((r1["written"], r2["written"], r2["duplicates"]), (1, 0, 1))
        self.assertEqual(r2["by_url"][0]["written"], 0)
        rows = O.read_records("autumn_leaves", self.env)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["last_confirmed_at"], (NOW + timedelta(days=1)).isoformat())
        r3 = O.record([self.rec("https://a.example/", state="見頃")], env=self.env, now=NOW + timedelta(days=1))
        self.assertEqual(r3["written"], 1)                                                    # 状態が変われば新しい記録
        r4_ = O.record([self.rec("https://a.example/", sdate="2026-11-01")], env=self.env, now=NOW + timedelta(days=1))
        self.assertEqual(r4_["written"], 1)                                                   # 状態の日付が変われば新しい記録
        rnd = ask.this_round([{"by_url": r2["by_url"]}], {}, {"needs_fetch": True})
        self.assertEqual(rnd["new_records"], 0)

    def test_2_undated_reconfirmed_fact_counts_as_checked_later(self):
        rec = {"subject": "flowers", "spot": "t-h-1", "state": "開花状況の記載なし", "state_date": None, "url": URL, "source_class": "secondary"}
        O.record([rec], env=self.env, now=NOW - timedelta(days=10))
        O.record([rec], env=self.env, now=NOW)
        rows = O.read_records("flowers", self.env)
        self.assertEqual(len(rows), 1)
        self.assertEqual(O.freshness(rows[0], NOW.date(), "flowers", O.load_policy())["class"], "fresh")

    def test_3_period_words_are_not_the_current_state(self):
        for raw in ("(例年の見頃のみ)", "例年の見頃: 11月中旬～12月上旬", "見頃予想は11月中旬", "見頃の時期は11月下旬", "見ごろ予測: 11月上旬"):
            self.assertEqual(O.normalize("autumn_leaves", raw), O.load_policy()["unknown_state"], raw)
            self.assertEqual(O.normalize("flowers", raw), O.load_policy()["unknown_state"], raw)
        self.assertEqual(O.normalize("autumn_leaves", "見頃"), "見頃")
        self.assertEqual(O.normalize("autumn_leaves", "色づき始め(例年の見頃は11月中旬)"), "色づき始め")
        self.assertEqual(O.normalize("flowers", "満開(見頃の時期は10月)"), "見頃")

    def test_4_open_meteo_fetched_at_is_the_receive_time(self):
        import fakes
        from ikimonobiyori.fetch import live
        from ikimonobiyori.fetch.cache import Cache
        got = datetime(2026, 10, 14, 7, 3, 12, tzinfo=JST)
        later_now = got + timedelta(days=2)
        inputs, rep = live.fetch_temperatures(["m001"], fakes.SITES, fakes.AUT, fakes.DATES, later_now.date(), later_now, cache=Cache(tempfile.mkdtemp()),
                                              cfg=fakes.CFG, http_get=fakes.FakeHttp(), live=True, max_requests=5, unparsed_dir=tempfile.mkdtemp(),
                                              clock=lambda: got)
        self.assertEqual(inputs["temperatures_meta"]["m001"]["fetched_at"], got.isoformat())
        self.assertEqual(inputs["fetched_at"], got.isoformat())
        self.assertEqual(live.received_at(NOW, lambda: got), got.isoformat())
        with self.assertRaises(ValueError):
            live.received_at(NOW, lambda: datetime(2026, 1, 1))

    def test_inat_aggregation_made_before_the_index_is_used_within_its_period(self):
        """段階37: 索引ができる前に取った集計(対象の日そのものの問い合わせ)も、期間(前後 window_weeks 週)が対象の日を含めば使う。"""
        from ikimonobiyori import profiles as PR
        from ikimonobiyori.config import load_config
        from ikimonobiyori.fetch.cache import Cache
        prof, cfg = PR.load_profiles()["birds"], load_config()
        area = O._rounded(O._area_by_id(AREAS[0]), prof)
        cache = Cache(paths.data_path(cfg["cache"]["dir"], self.env))
        for q in O._inat_queries(area, date(2026, 11, 2), prof, cfg):
            cache.put(url=q["url"], params=q["params"], body="{}", source="iNaturalist API", fetched_at=NOW.isoformat())
        st = O.inat_status(AREAS[0], date(2026, 11, 3), NOW, env=self.env)
        self.assertEqual((st["state"], st["center"]), ("fresh", "2026-11-02"))
        far = O.inat_status(AREAS[0], date(2026, 11, 2) + timedelta(days=30), NOW, env=self.env)
        self.assertEqual(far["state"], "none")


if __name__ == "__main__":
    unittest.main()
