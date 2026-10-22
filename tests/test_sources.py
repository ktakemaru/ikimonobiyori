"""現況の情報源の台帳と、読んだ結果の記録(段階15。ikimonobiyori/sources.py)。通信なし。
台帳の検査(承認の条件・名所カタログとの対応)、状態の書き方の対応、新しさ、候補の絞り込み、記録の読み書き(事実だけ・重複なし)。"""
import contextlib
import copy
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yaml

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import catalog, paths, sources

JST = timezone(timedelta(hours=9))
POLICY = sources.load_policy()


def src(**kw):
    s = {"id": "test-kankou-koyo", "publisher": "試験市観光協会", "publisher_kind": "tourism_association",
         "url": "https://kankou.example.org/koyo", "kind": "status_page",
         "covers": [{"site": "kouyou-0001", "label": "渓谷"}, {"name": "滝", "label": "【北】滝"}],
         "notation": {"style": "symbol", "map": {"✕": "not_yet", "△": "starting", "〇": "good", "◎": "peak", "▼": "fading"},
                      "no_info": ["情報なし"], "updated": "per_item", "year_shown": True},
         "readable": {"status": "ok", "checked_on": "2026-10-23", "robots": "allows"},
         "terms": {"status": "no_prohibition_found"},
         "approval": {"status": "approved", "approved_by": "claude_code_provisional", "approved_on": "2026-10-23"}}
    s.update(kw)
    return s


def reg(*ss):
    return {"schema": "ikimono-status-sources/1", "subject": "autumn_leaves", "sources": list(ss)}


def site(sid, tw=None, status_sources=None, **kw):
    e = {"id": sid, "name": f"名所 {sid}", "subjects": ["autumn_leaves"], "timing_type": "temperature", "kind": "point",
         "point": {"lat": 35.5, "lon": 139.5, "elevation_m": 100}, "location_precision": "exact", "status": "approved",
         "approved_at": "2026-10-22", "sources": [{"url": "https://example.org/a"}]}
    if tw:
        e["typical_window"] = {"start": tw[0], "end": tw[1], "source_url": "https://example.org/tw"}
    if status_sources is not None:
        e["status_sources"] = status_sources
    e.update(kw)
    return e


def cat(*entries):
    return {"schema": "ikimono-site-catalog/1", "subject": "autumn_leaves", "entries": list(entries)}


CATALOG = cat(site("kouyou-0001", ("10-21", "11-10"), ["test-kankou-koyo"]))


# 段階15 でユーザーが承認した情報源(2026-10-23 の見直し。docs/stage15-decisions.md D-38)。段階16 で仮承認に戻さない
STAGE15_USER_APPROVED = {"nikko-kankou-autumn-leaves", "hakone-kankou-koyo", "daigo-kanko-koyo", "ibaraki-guide-autumn-leaves", "yamanashi-kankou-koyo",
                         "tokyo-park-rikugien-news", "fng-shinjuku-seasonal", "tokyo-park-rikugien-lightup", "hasedera-lightup", "ttca-autumn-tsukuba",
                         "nikko-kankou-congestion", "okuooi-traffic-sumata", "numata-kankou-news"}


class Registry(unittest.TestCase):
    def errs(self, r, c=CATALOG, name="autumn_leaves"):
        return sources.check_registry(r, name=name, catalog_doc=c, policy=POLICY)

    def assertRejected(self, r, needle, c=CATALOG):
        errs = self.errs(r, c)
        self.assertTrue(any(needle in e for e in errs), errs)

    def test_the_repository_registry_passes(self):
        res = sources.check_all()
        self.assertEqual([(p.name, e) for p, e in res if e], [])
        self.assertIn("autumn_leaves.yaml", [p.name for p, _ in res])
        self.assertNotIn("policy.yaml", [p.name for p, _ in res])           # 方針のファイルは台帳として検査しない

    def test_the_repository_registry_keeps_the_rules(self):
        r = sources.load_registry("autumn_leaves")
        for s in r["sources"]:
            with self.subTest(s["id"]):
                if s["approval"]["status"] == "approved":
                    self.assertEqual(s["readable"]["status"], "ok")
                    self.assertNotIn(s["readable"].get("robots"), sources.ROBOTS_BLOCKING)
                    # 段階15 の仮承認はユーザーの見直し(2026-10-23)ですべてユーザーの承認に切り替えた。段階16 で足した情報源だけは仮承認でよい(指示書 フェーズ6)
                    self.assertEqual(s["approval"].get("approved_by"), "user" if s["id"] in STAGE15_USER_APPROVED else "claude_code_provisional")
                self.assertNotIn(s["publisher_kind"], ("aggregator", "travel_agency", "weather_company", "personal"))

    def test_the_review_of_2026_10_23_is_kept(self):
        """ユーザーの見直し(2026-10-23)の反映。"""
        by = sources.sources_by_id(sources.load_registry("autumn_leaves"))
        self.assertIs(by["hakone-kankou-koyo"]["notation"]["year_shown"], False)
        self.assertEqual(by["hakone-kankou-koyo"]["approval"]["status"], "approved")
        ise = by["isehara-oyama-koyo"]
        self.assertNotEqual(ise["kind"], "status_page")                              # 現況の情報源にしない
        self.assertEqual(ise["approval"]["status"], "pending")
        self.assertTrue(ise["approval"].get("reason"))
        for sid in ("ibaraki-guide-autumn-leaves", "fng-shinjuku-seasonal", "tokyo-park-rikugien-news", "tokyo-park-rikugien-lightup"):
            self.assertIn("複製には当たらないとユーザーが判断(2026-10-23)", by[sid]["approval"]["reason"], sid)
        self.assertEqual(by["chichibu-kanko-kouyou"]["approval"]["status"], "pending")
        self.assertIn("ユーザー側でも同じ内容を確認済み", by["nikko-kankou-autumn-leaves"]["readable"]["note"])
        c = sources.candidates(catalog.load_catalog("autumn_leaves"), sources.load_registry("autumn_leaves"), [date(2026, 11, 21)], POLICY)
        self.assertNotIn("isehara-oyama-koyo", [p["id"] for p in c["read_plan"]])
        self.assertIn("isehara-oyama-koyo", [h["id"] for h in c["human_urls"]])

    def test_a_good_registry_passes(self):
        self.assertEqual(self.errs(reg(src())), [])

    def test_cli_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["check"]), 0)
        self.assertIn("OK  sources/autumn_leaves.yaml", out.getvalue())
        d = Path(tempfile.mkdtemp(prefix="ikimono-src-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "autumn_leaves.yaml").write_text(yaml.safe_dump(reg(src(kind="blog")), allow_unicode=True), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sources.main(["check", "--sources-dir", str(d)]), 1)

    def test_schema_rejects_bad_shapes(self):
        self.assertRejected(reg(src(kind="blog")), "kind")
        self.assertRejected(reg(src(publisher_kind="personal")), "publisher_kind")
        self.assertRejected(reg(src(covers=[{"site": "kouyou-0001", "name": "x"}])), "covers")
        self.assertRejected(reg(src(body="本文の写し")), "Additional properties")       # 本文を入れる欄はない

    def test_rules_beyond_the_schema(self):
        self.assertRejected(reg(src(notation={"style": "word", "map": {"見頃": "mikoro"}})), "共通の段階にない")
        self.assertRejected(reg(src(covers=[{"site": "kouyou-9999"}])), "名所カタログの承認済みの件にない")
        self.assertRejected(reg(src(), src()), "id が重複")
        self.assertRejected(reg(src(approval={"status": "approved"})), "approved_by と approved_on")
        self.assertRejected(reg(src(readable={"status": "refused", "checked_on": "2026-10-23"})), "読めていない")
        self.assertRejected(reg(src(readable={"status": "partial", "checked_on": "2026-10-23"})), "読めていない")
        self.assertRejected(reg(src(readable={"status": "ok", "checked_on": "2026-10-23", "robots": "ai_agents_blocked"})), "robots.txt")
        self.assertRejected(reg(src(terms={"status": "not_checked"})), "利用条件")
        self.assertRejected(reg(src(terms={"status": "prohibits_summary"})), "利用条件")
        self.assertRejected(reg(src(readable={"status": "unconfirmed", "checked_on": "2026-10-23"}, approval={"status": "pending"})), "reason")
        self.assertRejected(reg(src(readable={"status": "ok", "checked_on": "2026-13-01"})), "日付でない")
        ok_pending = src(readable={"status": "unconfirmed", "checked_on": "2026-10-23"}, approval={"status": "pending", "reason": "HTTP 503"})
        self.assertEqual(self.errs(reg(ok_pending)), [])

    def test_catalog_and_registry_must_agree(self):
        self.assertRejected(reg(src()), "が違う", c=cat(site("kouyou-0001", ("10-21", "11-10"), [])))
        self.assertRejected(reg(src()), "台帳にない", c=cat(site("kouyou-0001", ("10-21", "11-10"), ["test-kankou-koyo", "missing-source"])))
        self.assertRejected(reg(src(covers=[{"name": "滝"}])), "が違う")             # カタログは指しているが台帳の covers にない


class Notation(unittest.TestCase):
    def test_symbols_map_to_the_common_stages(self):
        s = src()
        self.assertEqual(sources.normalize_state(s, "◎"), ("peak", "mapped"))
        self.assertEqual(sources.normalize_state(s, " 〇 "), ("good", "mapped"))
        self.assertEqual(sources.normalize_state(s, "▼"), ("fading", "mapped"))
        self.assertEqual(sources.normalize_state(s, "情報なし"), (None, "no_info"))
        self.assertEqual(sources.normalize_state(s, None), (None, "no_info"))
        self.assertEqual(sources.normalize_state(s, "見頃"), (None, "unknown"))       # 台帳にない書き方は推測しない

    def test_the_nikko_notation_in_the_repository(self):
        nikko = sources.sources_by_id(sources.load_registry("autumn_leaves"))["nikko-kankou-autumn-leaves"]
        got = {k: sources.normalize_state(nikko, k)[0] for k in "✕△〇◎▼"}
        self.assertEqual(got, {"✕": "not_yet", "△": "starting", "〇": "good", "◎": "peak", "▼": "fading"})

    def test_stage_labels(self):
        self.assertEqual(sources.stage_label(POLICY, "autumn_leaves", "peak"), "真っ盛り")
        self.assertIsNone(sources.stage_label(POLICY, "autumn_leaves", None))


class Freshness(unittest.TestCase):
    def test_classes(self):
        on = date(2026, 10, 23)
        cls = {n: sources.freshness(on - timedelta(days=n), on, POLICY)["class"] for n in (0, 3, 4, 7, 8, 30)}
        self.assertEqual(cls, {0: "fresh", 3: "fresh", 4: "somewhat_old", 7: "somewhat_old", 8: "old", 30: "old"})
        self.assertEqual(sources.freshness(None, on, POLICY)["class"], "unknown")
        self.assertEqual(sources.freshness(date(2026, 10, 20), on, POLICY)["label"], "新しい")
        with self.assertRaises(ValueError):
            sources.freshness(date(2026, 10, 24), on, POLICY)                      # 未来の更新日は推測で直さない

    def test_a_date_without_a_year_is_not_judged(self):
        on = date(2026, 10, 23)
        got = sources.freshness(date(2026, 10, 22), on, POLICY, year_inferred=True)
        self.assertEqual(got, {"age_days": None, "class": "year_unknown", "label": "新しさ不明"})   # 1 日前でも「新しい」としない
        self.assertEqual(sources.freshness(None, on, POLICY, year_inferred=True)["class"], "unknown")
        yearless = src(notation={"style": "word", "map": {"まだまだ": "not_yet"}, "year_shown": False})
        self.assertTrue(sources.year_unknown(yearless))
        self.assertTrue(sources.year_unknown(src(), {"updated_year_inferred": True}))
        self.assertFalse(sources.year_unknown(src(), {}))

    def test_policy_values_have_a_source(self):
        for k in ("fresh_max_days", "somewhat_old_max_days"):
            self.assertIn("source", POLICY["freshness"][k])
            self.assertIn("provisional", POLICY["freshness"][k])
        self.assertIn("source", POLICY["candidates"]["window_margin_days"])


class Weekend(unittest.TestCase):
    def test_next_weekend(self):
        f = lambda s: [d.isoformat() for d in sources.next_weekend(datetime.fromisoformat(s))]
        self.assertEqual(f("2026-10-23T22:00:00+09:00"), ["2026-10-24", "2026-10-25"])   # 金曜
        self.assertEqual(f("2026-10-19T08:00:00+09:00"), ["2026-10-24", "2026-10-25"])   # 月曜
        self.assertEqual(f("2026-10-24T08:00:00+09:00"), ["2026-10-24", "2026-10-25"])   # 土曜は当日から
        self.assertEqual(f("2026-10-25T08:00:00+09:00"), ["2026-10-25"])                 # 日曜は当日だけ

    def test_now_needs_an_offset(self):
        with self.assertRaises(ValueError):
            sources.parse_now("2026-10-23T22:00:00")

    def test_days_from_window(self):
        tw = {"start": "10-21", "end": "11-10"}
        self.assertEqual(sources.days_from_window(date(2026, 10, 24), tw), 0)
        self.assertEqual(sources.days_from_window(date(2026, 10, 14), tw), 7)
        self.assertEqual(sources.days_from_window(date(2026, 11, 17), tw), 7)
        wrap = {"start": "12-20", "end": "01-10"}
        self.assertEqual(sources.days_from_window(date(2027, 1, 5), wrap), 0)
        self.assertEqual(sources.days_from_window(date(2026, 12, 25), wrap), 0)
        self.assertEqual(sources.days_from_window(date(2027, 1, 12), wrap), 2)

    def test_candidates_and_the_read_plan(self):
        r = reg(src(covers=[{"site": "kouyou-0001"}, {"site": "kouyou-0002"}]),
                src(id="test-park-news", covers=[{"site": "kouyou-0003"}], readable={"status": "unconfirmed", "checked_on": "2026-10-23"},
                    approval={"status": "pending", "reason": "HTTP 503"}),
                src(id="test-traffic", kind="access_page", covers=[{"site": "kouyou-0002"}]))
        c = cat(site("kouyou-0001", ("10-21", "11-10"), ["test-kankou-koyo"]),
                site("kouyou-0002", ("10-31", "11-20"), ["test-kankou-koyo", "test-traffic"]),
                site("kouyou-0003", None, ["test-park-news"]),
                site("kouyou-0004", ("12-01", "12-20"), []),
                site("kouyou-0005", ("09-21", "10-10"), [], status="candidate"))
        got = sources.candidates(c, r, [date(2026, 10, 24), date(2026, 10, 25)], POLICY)
        self.assertEqual([(s["site"], s["season"], s["days_from_window"]) for s in got["sites"]],
                         [("kouyou-0001", "in_window", 0), ("kouyou-0002", "near", 6), ("kouyou-0003", "no_window", None)])
        self.assertEqual([o["site"] for o in got["out_of_season"]], ["kouyou-0004"])        # candidate(未承認)は入れない
        self.assertEqual([(p["id"], p["sites"]) for p in got["read_plan"]],
                         [("test-kankou-koyo", ["kouyou-0001", "kouyou-0002"]), ("test-traffic", ["kouyou-0002"])])   # 1 回だけ読む。現況が先
        self.assertEqual([h["id"] for h in got["human_urls"]], ["test-park-news"])
        self.assertEqual(got["no_status_source"], ["kouyou-0003"])

    def test_out_of_season_sites_covered_by_a_page_that_is_read_anyway(self):
        r = reg(src(covers=[{"site": "kouyou-0001"}, {"site": "kouyou-0002"}]))
        c = cat(site("kouyou-0001", ("10-21", "11-10"), ["test-kankou-koyo"]), site("kouyou-0002", ("09-21", "10-10"), ["test-kankou-koyo"]))
        got = sources.candidates(c, r, [date(2026, 10, 24)], POLICY)
        self.assertEqual(got["out_of_season"], [{"site": "kouyou-0002", "name": "名所 kouyou-0002", "days_from_window": 14,
                                                 "covered_by_read_plan": ["test-kankou-koyo"]}])

    def test_weekend_cli_on_the_repository(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["weekend", "--now", "2026-10-23T22:00:00+09:00"]), 0)
        got = json.loads(out.getvalue())
        self.assertEqual(got["dates"], ["2026-10-24", "2026-10-25"])
        self.assertIn("kouyou-0001", [s["site"] for s in got["sites"]])


class Records(unittest.TestCase):
    R = reg(src(), src(id="test-pending", approval={"status": "pending"}))
    AT = "2026-10-23T21:30:00+09:00"

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-log-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {paths.ENV_DATA_DIR: str(self.d)}

    def rec(self, **kw):
        a = {"registry": self.R, "policy": POLICY, "source_id": "test-kankou-koyo", "read_at": self.AT, "state": "◎",
             "updated": "2026-10-21", "site": "kouyou-0001", "label": "渓谷"}
        a.update(kw)
        return sources.make_record(**a)

    def errs(self, r):
        return sources.validate_record(r, registry=self.R, policy=POLICY)

    def test_a_good_record(self):
        r = self.rec()
        self.assertEqual(self.errs(r), [])
        self.assertEqual((r["stage"], r["url"], r["schema"]), ("peak", "https://kankou.example.org/koyo", "ikimono-status-record/1"))
        self.assertEqual(self.errs(self.rec(site=None, name="滝", label=None, state="情報なし", updated=None)), [])

    def test_bad_records_are_rejected(self):
        def bad(r, needle):
            errs = self.errs(r)
            self.assertTrue(any(needle in e for e in errs), errs)
        bad({**self.rec(), "text": "公式ページの本文"}, "入れられない項目")
        bad({**self.rec(), "photo": "x.jpg"}, "入れられない項目")
        bad(self.rec(source_id="test-pending"), "承認されていない")
        bad({**self.rec(source_id="nope"), "url": "https://kankou.example.org/koyo"}, "台帳にない")
        bad(self.rec(site="kouyou-0099"), "covers にない")
        bad(self.rec(name="滝"), "どちらか一方")
        bad(self.rec(state="◎" * 21), "本文を写さない")
        bad(self.rec(label="長" * 41), "label")
        bad({**self.rec(), "stage": "good"}, "台帳の対応")
        bad(self.rec(read_at="2026-10-23T21:30:00"), "オフセット")
        bad(self.rec(updated="2026-10-24"), "読んだ日")
        bad(self.rec(updated="2026-02-30"), "日付でない")
        bad({**self.rec(), "url": "https://other.example.com/koyo"}, "ホスト")
        bad(self.rec(year_inferred="yes"), "真偽値")

    def test_append_dedup_and_all_or_nothing(self):
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(sources.append_records([self.rec(), self.rec(site=None, name="滝", label="【北】滝", state="△")],
                                                    registry=self.R, policy=POLICY), (2, 0))
            self.assertEqual(sources.append_records([self.rec(read_at="2026-10-23T23:00:00+09:00")], registry=self.R, policy=POLICY), (0, 1))
            with self.assertRaises(ValueError):
                sources.append_records([self.rec(state="▼", updated="2026-10-23"), self.rec(source_id="test-pending")], registry=self.R, policy=POLICY)
            got = sources.read_records("autumn_leaves")
        self.assertEqual([(r.get("site") or r.get("name"), r["stage"]) for r in got], [("kouyou-0001", "peak"), ("滝", "starting")])
        p = self.d / "status_log" / "autumn_leaves.jsonl"
        self.assertTrue(p.is_file())                                                # IKIMONOBIYORI_DATA_DIR の下だけに書く
        self.assertNotIn(b"\r\n", p.read_bytes())

    def test_record_cli(self):
        batch = self.d / "reads.json"
        batch.write_text(json.dumps([{"source": "nikko-kankou-autumn-leaves", "site": "kouyou-0001", "label": "【奥日光】湯ノ湖、湯滝",
                                      "state": "◎", "updated": "2026-10-20"}], ensure_ascii=False), encoding="utf-8")
        reg_real = sources.load_registry("autumn_leaves")
        approved = copy.deepcopy(reg_real)
        for s in approved["sources"]:
            if s["id"] == "nikko-kankou-autumn-leaves":
                s["approval"] = {"status": "approved", "approved_by": "claude_code_provisional", "approved_on": "2026-10-23"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(sources, "load_registry", return_value=approved), contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["record", "--read-at", "2026-10-23T21:30:00+09:00", "--batch", str(batch)]), 0)
        got = json.loads(out.getvalue())
        self.assertEqual(got["written"], 1)
        self.assertEqual((got["rows"][0]["stage_label"], got["rows"][0]["freshness"]["class"]), ("真っ盛り", "fresh"))
        self.assertTrue(Path(got["path"]).is_relative_to(self.d))

    def test_a_source_without_years_needs_the_inferred_flag(self):
        r = reg(src(id="test-yearless", notation={"style": "word", "map": {"まだまだ": "not_yet"}, "updated": "per_item", "year_shown": False}))
        a = {"registry": r, "policy": POLICY, "source_id": "test-yearless", "read_at": self.AT, "state": "まだまだ",
             "updated": "2026-10-22", "site": "kouyou-0001", "label": "渓谷"}
        errs = sources.validate_record(sources.make_record(**a), registry=r, policy=POLICY)
        self.assertTrue(any("updated_year_inferred" in e for e in errs), errs)
        self.assertEqual(sources.validate_record(sources.make_record(**a, year_inferred=True), registry=r, policy=POLICY), [])
        self.assertEqual(sources.validate_record(sources.make_record(**{**a, "updated": None}), registry=r, policy=POLICY), [])

    def test_record_cli_says_freshness_unknown_for_hakone(self):
        batch = self.d / "reads.json"
        batch.write_text(json.dumps([{"source": "hakone-kankou-koyo", "site": "kouyou-0018", "label": "強羅(箱根美術館)",
                                      "state": "色づきはじめ", "updated": "2026-10-22", "year_inferred": True}], ensure_ascii=False), encoding="utf-8")
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["record", "--read-at", "2026-10-23T21:30:00+09:00", "--batch", str(batch)]), 0)
        row = json.loads(out.getvalue())["rows"][0]
        self.assertEqual((row["stage"], row["freshness"]["class"], row["freshness"]["label"]), ("starting", "year_unknown", "新しさ不明"))

    def test_the_log_location_is_under_the_data_dir(self):
        self.assertEqual(sources.log_path("autumn_leaves", self.env), self.d / "status_log" / "autumn_leaves.jsonl")

    def test_erroneous_records_are_kept_but_not_used(self):
        """段階16 A-1: 誤った記録は消さずに印を付け、読む処理は使わない。正しい事実は user_verified の新しい記録。"""
        wrong = self.rec(site=None, name="滝", label="【北】滝", state="△", updated="2026-10-22")
        with mock.patch.dict(os.environ, self.env):
            sources.append_records([self.rec(), wrong], registry=self.R, policy=POLICY)
            with self.assertRaises(ValueError):                                      # 一致しなければ何もしない
                sources.mark_erroneous("autumn_leaves", {"name": "滝", "official_state": "◎"}, reason="x", corrected_on="2026-10-23")
            with self.assertRaises(ValueError):
                sources.mark_erroneous("autumn_leaves", {"name": "滝"}, reason="", corrected_on="2026-10-23")
            n = sources.mark_erroneous("autumn_leaves", {"name": "滝", "official_state": "△"}, reason="紹介文を状態と取り違えた", corrected_on="2026-10-23")
            self.assertEqual(n, 1)
            self.assertEqual(sources.mark_erroneous("autumn_leaves", {"name": "滝", "official_state": "△"}, reason="x", corrected_on="2026-10-23"), 0)
            fixed = self.rec(site=None, name="滝", label="【北】滝", state="✕", updated="2026-10-15", method="user_verified",
                             read_at="2026-10-23T22:00:00+09:00")
            self.assertEqual(self.errs(fixed), [])
            sources.append_records([fixed], registry=self.R, policy=POLICY)
            used = sources.read_records("autumn_leaves")
            every = sources.read_records("autumn_leaves", include_erroneous=True)
            same_day = sources.records_on("autumn_leaves", date(2026, 10, 23))
            with self.assertRaises(ValueError):                                      # 印の付いた記録を足し直さない
                sources.append_records([{**wrong, "erroneous": True, "erroneous_reason": "x", "corrected_on": "2026-10-23"}], registry=self.R, policy=POLICY)
        self.assertEqual(len(every), 3)
        self.assertEqual([(r.get("name"), r["official_state"], r["method"]) for r in used if r.get("name")], [("滝", "✕", "user_verified")])
        self.assertNotIn("△", [r["official_state"] for r in same_day])
        marked = [r for r in every if r.get("erroneous")]
        self.assertEqual((marked[0]["official_state"], marked[0]["corrected_on"]), ("△", "2026-10-23"))
        self.assertNotIn(b"\r\n", (self.d / "status_log" / "autumn_leaves.jsonl").read_bytes())

    def test_new_fields_are_checked(self):
        def bad(r, needle):
            errs = self.errs(r)
            self.assertTrue(any(needle in e for e in errs), errs)
        bad(self.rec(method="guess"), "method")
        bad(self.rec(forecast="長" * 61), "official_forecast")
        bad(self.rec(event_start="2026-11-25"), "event_start")
        bad(self.rec(event_start="2026-12-06", event_end="2026-11-25"), "より後")
        bad({**self.rec(), "erroneous": True}, "誤りの印")
        self.assertEqual(self.errs(self.rec(forecast="10月下旬～11月上旬", event_start="2026-11-25", event_end="2026-12-06")), [])
        self.assertEqual(self.rec()["method"], "agent_summary")                      # 既定は要約で読んだもの

    def test_records_are_reused_only_on_the_same_day(self):
        with mock.patch.dict(os.environ, self.env):
            sources.append_records([self.rec(read_at="2026-10-22T23:50:00+09:00", updated="2026-10-20"), self.rec(read_at="2026-10-23T00:10:00+09:00")],
                                   registry=self.R, policy=POLICY)
            self.assertEqual([r["read_at"] for r in sources.records_on("autumn_leaves", date(2026, 10, 23))], ["2026-10-23T00:10:00+09:00"])
            self.assertEqual(sources.records_on("autumn_leaves", date(2026, 10, 24)), [])


class Forecasts(unittest.TestCase):
    """段階16 A-8: 公式の見頃予測。A-3: 表示が古い可能性。"""
    def test_forecast_windows(self):
        f = lambda t: (lambda w: w and (w[0].isoformat(), w[1].isoformat()))(sources.forecast_window(t, 2026, POLICY))
        self.assertEqual(f("10月下旬～11月上旬"), ("2026-10-21", "2026-11-10"))
        self.assertEqual(f("9月下旬"), ("2026-09-21", "2026-09-30"))
        self.assertEqual(f("10月下旬～11月中旬（木の種類により異なります）"), ("2026-10-21", "2026-11-20"))   # 括弧の注記は読み飛ばす
        self.assertEqual(f("10月上旬～中旬"), ("2026-10-01", "2026-10-20"))
        self.assertEqual(f("11月上旬～11月下旬"), ("2026-11-01", "2026-11-30"))
        self.assertEqual(f("12月下旬～1月上旬"), ("2026-12-21", "2027-01-10"))                         # 年をまたぐ(冬鳥など)
        self.assertEqual(f("2月下旬"), ("2026-02-21", "2026-02-28"))
        for t in ("10月下旬～", "見頃", "", None, "13月上旬"):
            self.assertIsNone(sources.forecast_window(t, 2026, POLICY), t)                              # 読めないものは推測しない

    def test_month_thirds_come_from_the_policy(self):
        self.assertIn("source", POLICY["month_thirds"])
        self.assertEqual(set(POLICY["month_thirds"]["items"]), {"上旬", "中旬", "下旬"})

    def test_icons_map_to_words(self):
        hakone = sources.sources_by_id(sources.load_registry("autumn_leaves"))["hakone-kankou-koyo"]
        self.assertEqual({k: sources.normalize_state(hakone, k)[0] for k in ("icon_lev1", "icon_lev2", "icon_lev4", "icon_lev3")},
                         {"icon_lev1": "not_yet", "icon_lev2": "starting", "icon_lev4": "fading", "icon_lev3": None})   # lev3 は確かめていない

    def test_stale_display_and_the_summary(self):
        r = reg(src(), src(id="test-yearless", notation={"style": "word", "map": {"まだまだ": "not_yet", "また来年": "fading"}, "year_shown": False},
                           covers=[{"site": "kouyou-0001", "label": "美術館"}, {"name": "湖", "label": "湖"}]),
                src(id="test-event", kind="event_page", covers=[{"site": "kouyou-0001", "label": "ライトアップ"}], notation={"style": "none", "map": {}}))
        c = cat(site("kouyou-0001", ("11-11", "11-30"), ["test-kankou-koyo", "test-yearless", "test-event"]))
        at = "2026-10-23T07:00:00+09:00"
        mk = lambda **kw: sources.make_record(registry=r, policy=POLICY, read_at=at, **kw)
        recs = [mk(source_id="test-yearless", site="kouyou-0001", label="美術館", state="また来年", updated="2026-10-06", year_inferred=True),
                mk(source_id="test-yearless", name="湖", label="湖", state="まだまだ", updated="2026-10-15", year_inferred=True),
                mk(source_id="test-kankou-koyo", name="滝", label="【北】滝", state="✕", updated="2026-10-15", forecast="10月下旬～11月上旬"),
                mk(source_id="test-kankou-koyo", site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-21", forecast="10月中旬"),
                mk(source_id="test-event", site="kouyou-0001", label="ライトアップ", state=None, event_start="2026-10-31", event_end="2026-11-30")]
        self.assertEqual([e for x in recs for e in sources.validate_record(x, registry=r, policy=POLICY)], [])
        got = sources.summarize(recs, registry=r, catalog_doc=c, policy=POLICY, on=date(2026, 10, 23), dates=[date(2026, 10, 31), date(2026, 11, 1)])
        by = {(x["site"] or x["name"], x["label"]): x for x in got["rows"]}
        self.assertTrue(by[("kouyou-0001", "美術館")]["stale_display_suspect"])          # 終わりの表示が例年の時期より前 → 古い表示の可能性
        self.assertFalse(by[("湖", "湖")]["stale_display_suspect"])
        self.assertEqual(by[("湖", "湖")]["freshness"]["class"], "year_unknown")
        self.assertEqual([(x["name"], x["official_state"]) for x in got["forecast_hits"]], [("滝", "✕")])   # 今は「まだ」でも予測が対象日にかかる
        self.assertEqual([x["label"] for x in got["events"]], ["ライトアップ"])
        self.assertEqual(got["unparsed_forecasts"], [])
        self.assertFalse(sources.stale_display_suspect(recs[0], None, POLICY, r["sources"][1]))   # カタログの件がなければ判定しない


class Generic(unittest.TestCase):
    """段階16 B: 対象によらない形(段階の並びはプロファイル、地域・条件・範囲の外・対象の一覧)。"""
    def test_stages_come_from_the_profiles(self):
        from ikimonobiyori.profiles import load_profiles
        self.assertEqual(POLICY["stages"]["autumn_leaves"], load_profiles()["autumn_leaves"]["stages"])
        self.assertNotIn("stages", yaml.safe_load(paths.SOURCES_POLICY_PATH.read_text(encoding="utf-8")))   # 方針には書かない(正本はプロファイル)
        self.assertEqual(sources.stage_errors(POLICY), [])
        self.assertEqual([sources.stage_order(POLICY, "autumn_leaves", s) for s in ("not_yet", "starting", "good", "peak", "fading")], [0, 1, 2, 3, 4])

    def test_stage_errors(self):
        bad = copy.deepcopy(POLICY)
        bad["stages"]["autumn_leaves"]["items"][1]["order"] = 9
        self.assertTrue(any("共通の順番" in e for e in sources.stage_errors(bad)))
        bad = copy.deepcopy(POLICY)
        bad["stages"]["autumn_leaves"]["items"].reverse()
        self.assertTrue(any("並んでいない" in e for e in sources.stage_errors(bad)))

    def test_scope(self):
        self.assertEqual(sources.scope_orders(POLICY), [2, 3])                              # 既定は見ごろ・最盛
        self.assertEqual(sources.scope_orders(POLICY, early=True), [1, 2, 3])
        self.assertEqual(sources.scope_orders(POLICY, early=True, late=True), [1, 2, 3, 4])

    def test_horizon(self):
        now = datetime(2026, 10, 23, 8, tzinfo=JST)
        self.assertEqual(sources.horizon(now, [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 8)], POLICY),
                         {"days": 14, "beyond": ["2026-11-07", "2026-11-08"]})

    def test_tags_filter_sites(self):
        e = site("kouyou-0001", tags={"prefecture": "東京都", "area": "都心", "terrain": ["garden", "urban"], "access": ["walk_from_station"]})
        region = {"name": "都内", "match": {"prefectures": ["東京都"]}}
        self.assertTrue(sources.site_filter(e, region=region, terrain=["garden"], access=["walk_from_station"]))
        self.assertFalse(sources.site_filter(e, terrain=["mountain"]))
        self.assertFalse(sources.site_filter(site("kouyou-0002"), terrain=["mountain"]))   # tags がなければ外す(分からない)
        self.assertEqual(catalog.schema_errors(cat(e)), [])
        self.assertTrue(catalog.schema_errors(cat(site("kouyou-0003", tags={"terrain": ["volcano"]}))))

    def test_regions(self):
        regions = sources.load_regions()
        self.assertEqual(sources.resolve_region("奥日光", regions)["name"], "日光")
        self.assertIsNone(sources.resolve_region("日光の近く", regions))                    # 推測で近いものを選ばない
        names = [r["name"] for r in regions["regions"]]
        self.assertEqual(len(names), len(set(names)))
        aliases = [a for r in regions["regions"] for a in [r["name"]] + (r.get("aliases") or [])]
        self.assertEqual(len(aliases), len(set(aliases)), "地域の呼び名が重複")
        cp = catalog.load_policy()
        tohoku = sources.region_report(sources.resolve_region("東北", regions), catalogs={"autumn_leaves": catalog.load_catalog("autumn_leaves")},
                                       catalog_policy=cp)
        self.assertEqual(tohoku["status"], "partial")                                      # 一部(福島県の代表点)が 250 km 以内
        self.assertIn("福島県", tohoku["within_points_by_prefecture"])
        self.assertNotIn("宮城県", tohoku["within_points_by_prefecture"])
        self.assertEqual(tohoku["catalog_sites"], {"autumn_leaves": []})
        tokyo = sources.region_report(sources.resolve_region("都内", regions), catalogs={"autumn_leaves": catalog.load_catalog("autumn_leaves")},
                                      catalog_policy=cp)
        self.assertEqual(tokyo["status"], "in_range")
        self.assertTrue({"kouyou-0022", "kouyou-0023", "kouyou-0024"} <= set(tokyo["catalog_sites"]["autumn_leaves"]))

    def test_every_catalog_area_is_reachable_by_a_region(self):
        regions = sources.load_regions()
        for subject in [s["subject"] for s in sources.subjects_status() if s["implemented"]]:
            for e in catalog.approved_entries(catalog.load_catalog(subject)):
                with self.subTest(e["id"]):
                    self.assertIn("tags", e)
                    self.assertTrue(any(sources.in_region(e, r) for r in regions["regions"]))

    def test_subjects(self):
        got = {s["subject"]: s for s in sources.subjects_status()}
        self.assertTrue(got["autumn_leaves"]["implemented"])
        self.assertFalse(got["cherry_blossom"]["implemented"])
        self.assertIn("台帳", got["cherry_blossom"]["missing"])


class WinteringBirds(unittest.TestCase):
    """段階16 C: 2 つ目の対象(冬鳥の飛来地)。手順・コードは紅葉と同じものを使う。"""
    def test_the_second_subject_uses_the_same_machinery(self):
        got = {s["subject"]: s["implemented"] for s in sources.subjects_status()}
        self.assertTrue(got["wintering_birds"] and got["autumn_leaves"])
        self.assertEqual([s["label"] for s in POLICY["stages"]["wintering_birds"]["items"]], ["飛来前", "飛来開始", "増加中", "最多", "北帰行"])
        self.assertEqual(sources.stage_errors(POLICY), [])
        res = dict((p.name, e) for p, e in sources.check_all())
        self.assertEqual(res["wintering_birds.yaml"], [])

    def test_no_count_thresholds(self):
        """羽数から段階を決める閾値は持たない(出典がない)。羽数は原文のまま、段階は null。"""
        reg_w = sources.load_registry("wintering_birds")
        for s in reg_w["sources"]:
            self.assertFalse(any(k.endswith("羽") for k in ((s.get("notation") or {}).get("map") or {})), s["id"])
        rec = sources.make_record(registry=reg_w, policy=POLICY, source_id="azumino-hakucho-hirai", site="hakucho-0002", label="御宝田遊水地",
                                  read_at="2026-10-23T08:00:00+09:00", state="6羽", updated="2026-10-20")
        self.assertEqual((rec["stage"], sources.validate_record(rec, registry=reg_w, policy=POLICY)), (None, []))

    def test_before_the_season_the_typical_start_is_given(self):
        c = catalog.load_catalog("wintering_birds")
        got = sources.candidates(c, sources.load_registry("wintering_birds"), [date(2026, 10, 24), date(2026, 10, 25)], POLICY)
        up = {u["site"]: u["next_start"] for u in got["upcoming_windows"]}
        self.assertEqual(up["hakucho-0003"], "2026-11-11")                                 # 多々良沼: 例年 11月中旬から
        self.assertIn("hakucho-0001", [s["site"] for s in got["sites"]])                   # 瓢湖: 例年 10月上旬から(季節の中)
        self.assertEqual(sources.next_window_start(date(2026, 12, 1), {"start": "11-11", "end": "03-10"}), date(2027, 11, 11))

    def test_locations_are_coarse(self):
        for e in catalog.approved_entries(catalog.load_catalog("wintering_birds")):
            self.assertIn(e["location_precision"], ("area_1km", "area_10km"), e["id"])


class V0Estimates(unittest.TestCase):
    DOC = {"schema": "biyori-proposal/1", "generated_at": "2026-10-23T09:30:00+09:00", "proposals": [
        {"id": "ikimonobiyori:autumn_leaves:2026-10-24:kouyou-0002", "phenology_stage": "before_bud", "suitability": {"band": "no"}},
        {"id": "ikimonobiyori:autumn_leaves:2026-10-24:kouyou-0001", "phenology_stage": "early_bloom", "suitability": {"band": "maybe"}},
        {"id": "ikimonobiyori:autumn_leaves:2026-10-25:kouyou-0001", "phenology_stage": "early_bloom", "suitability": {"band": "maybe"}},
        {"id": "ikimonobiyori:autumn_leaves:2026-10-24:m001", "phenology_stage": "peak", "suitability": {"band": "maybe"}},
        {"id": "ikimonobiyori:birds:2026-10-24:area-1", "suitability": {"band": "maybe"}}]}
    LABELS = {"before_bud": "色づき前", "early_bloom": "色づき始め"}

    def test_reads_only_the_subject_and_always_labels_it_as_an_estimate(self):
        got = sources.v0_estimates(self.DOC, subject="autumn_leaves", labels=self.LABELS, policy=POLICY, dates=[date(2026, 10, 24)])
        self.assertEqual([(r["site"], r["stage_label"], r["band"]) for r in got],
                         [("kouyou-0001", "色づき始め", "maybe"), ("kouyou-0002", "色づき前", "no"), ("m001", None, "maybe")])
        self.assertTrue(all(r["label"] == "推定(未検証・段階14で不合格)" and r["generated_at"] == "2026-10-23T09:30:00+09:00" for r in got))
        self.assertEqual(len(sources.v0_estimates(self.DOC, subject="autumn_leaves", labels=self.LABELS, policy=POLICY)), 4)

    def test_rejects_other_shapes(self):
        with self.assertRaises(ValueError):
            sources.v0_estimates({"schema": "x"}, subject="autumn_leaves", labels={}, policy=POLICY)


class Procedure(unittest.TestCase):
    """「今週末のおすすめ」の手順は、Claude Code のスキルと AGENTS.md・CLAUDE.md で同じ(段階15)。"""
    def block(self, path):
        s = path.read_text(encoding="utf-8")
        b, e = "<!-- ikimono-weekend:begin -->", "<!-- ikimono-weekend:end -->"
        self.assertEqual((s.count(b), s.count(e)), (1, 1), path.name)
        return s[s.index(b):s.index(e)]

    def test_skill_and_agents_md_have_the_same_steps(self):
        skill = self.block(ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md")
        self.assertEqual(self.block(ROOT / "AGENTS.md"), skill)
        self.assertEqual(self.block(ROOT / "CLAUDE.md"), skill)
        for needle in ("approved", "robots.txt", "3 日以内", "7 日以内", "推定(未検証・段階14で不合格)", "上位 3〜5 か所", "出典 URL",
                       "IKIMONOBIYORI_DATA_DIR", "--live"):
            self.assertIn(needle, skill)

    def test_the_numbers_in_the_steps_match_the_policy(self):
        skill = self.block(ROOT / "AGENTS.md")
        f = POLICY["freshness"]
        self.assertIn(f"{sources.val(f['fresh_max_days'])} 日以内は「{f['labels']['fresh']}」", skill)
        self.assertIn(f"{sources.val(f['somewhat_old_max_days'])} 日以内は「{f['labels']['somewhat_old']}」", skill)
        self.assertIn(f"前後 {sources.val(POLICY['candidates']['window_margin_days'])} 日以内", skill)
        r = POLICY["recommend"]
        self.assertIn(f"上位 {sources.val(r['top_min'])}〜{sources.val(r['top_max'])} か所", skill)
        self.assertIn(POLICY["aux_estimate"]["label"], skill)
        self.assertIn(f"「{f['labels']['year_unknown']}」", skill)                      # 年のない更新日(ユーザーの見直し 2026-10-23)
        self.assertIn(f"{sources.val(POLICY['horizon_days'])} 日より先", skill)            # 段階16 B-4 ①
        common = "・".join(f"{s['order']} {s['label']}" for s in POLICY["common_stages"]["items"])
        self.assertIn(common, skill)                                                       # 共通の順番(0 前・1 始まり・…)

    def test_the_steps_cover_the_five_question_types(self):
        skill = self.block(ROOT / "AGENTS.md")
        for needle in ("1. **いつ**", "2. **どこで**", "3. **どの段階まで**", "4. **どんな場所で**", "5. **範囲の外**",
                       "sources subjects", "sources region", "--early", "--late", "--terrain", "--access", "conflicts", "stale_display_suspect",
                       "reader: code", "コードで読めなかった", "ヤマビヨリ"):
            self.assertIn(needle, skill)
        self.assertNotIn("日光市観光協会 ✕ まだ", skill)                                   # 紅葉専用の書き方は台帳とプロファイルへ


if __name__ == "__main__":
    unittest.main()
