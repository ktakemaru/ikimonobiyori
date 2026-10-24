"""手順の抜けの修正(段階17 フェーズ2)。通信なし。合成のデータだけ。
①コードで読む前に 1 回だけ聞く・聞けなければ「簡易な読み取り」 ④読んだ事実の記録(read_by) ⑤新しさの日付の基準(freshness_basis)
⑥一覧から今月の記事をたどる(瓢湖)。"""
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
from helpers import ROOT

from ikimonobiyori import answer, sources

import test_answer as TA

JST = timezone(timedelta(hours=9))
POLICY = sources.load_policy()
READ_AT = "2026-10-24T13:54:00+09:00"
ON = date(2026, 10, 24)


def rec(source_id="test-koyo", **kw):
    kw.setdefault("site", "kouyou-0001")
    kw.setdefault("label", "渓谷")
    kw.setdefault("state", "◎")
    return sources.make_record(registry=TA.REG, policy=POLICY, read_at=READ_AT, source_id=source_id, **kw)


def fresh(r, src_id="test-koyo"):
    return sources.record_freshness(r, sources.sources_by_id(TA.REG)[src_id], ON, POLICY)


class FreshnessBasis(unittest.TestCase):
    def test_the_observed_date_comes_first(self):
        r = rec(observed="2026-10-22", updated="2026-10-15")
        self.assertEqual(r["freshness_basis"], "observed_date")
        d, no_year, f = fresh(r)
        self.assertEqual((d, no_year, f["class"], f["age_days"]), ("2026-10-22", False, "fresh", 2))
        self.assertEqual(sources.validate_record(r, registry=TA.REG, policy=POLICY), [])

    def test_otherwise_the_updated_date(self):
        for up, cls in (("2026-10-21", "fresh"), ("2026-10-19", "somewhat_old"), ("2026-10-17", "somewhat_old"), ("2026-10-16", "old")):
            r = rec(updated=up)
            self.assertEqual(r["freshness_basis"], "updated_date")
            self.assertEqual(fresh(r)[2]["class"], cls, up)                     # 3 日以内・7 日以内・それより古い

    def test_an_observed_date_without_a_year_is_unknown(self):
        r = rec(observed="2026-10-20", observed_year_inferred=True, updated="2026-10-22")
        self.assertEqual(fresh(r)[2]["class"], "year_unknown")                  # 年がなければ「新しさ不明」(更新日に年があっても使わない)

    def test_a_single_date_takes_its_kind_from_the_registry(self):
        r = rec(source_id="test-yearless", site="kouyou-0006", label="美術館", state="また来年", updated="2026-10-06", year_inferred=True)
        self.assertEqual(r["freshness_basis"], "updated_date")
        reg = json.loads(json.dumps(TA.REG))
        reg["sources"][1]["notation"]["date_basis"] = "observed_date"            # 箱根の「M/D現在」のように、1 つだけの日付が現地の日付
        r2 = sources.make_record(registry=reg, policy=POLICY, read_at=READ_AT, source_id="test-yearless", site="kouyou-0006", label="美術館",
                                 state="また来年", updated="2026-10-06", year_inferred=True)
        self.assertEqual(r2["freshness_basis"], "observed_date")
        hakone = sources.sources_by_id(sources.load_registry("autumn_leaves"))["hakone-kankou-koyo"]
        self.assertEqual(hakone["notation"]["date_basis"], "observed_date")

    def test_bad_basis_and_dates_are_rejected(self):
        errs = lambda r: sources.validate_record(r, registry=TA.REG, policy=POLICY)
        self.assertTrue(any("freshness_basis" in e for e in errs({**rec(updated="2026-10-21"), "freshness_basis": "observed_date"})))
        self.assertTrue(any("読んだ日" in e for e in errs(rec(observed="2026-10-25"))))
        self.assertTrue(any("真偽値" in e for e in errs(rec(observed="2026-10-20", observed_year_inferred="yes"))))
        self.assertEqual(rec(state="✕").get("freshness_basis"), None)          # 日付がなければ基準もない


class ReadBy(unittest.TestCase):
    def test_read_by_follows_the_method(self):
        self.assertEqual(rec(updated="2026-10-21")["read_by"], "summary")
        self.assertEqual(rec(updated="2026-10-21", method="code")["read_by"], "code")
        self.assertEqual(rec(updated="2026-10-21", method="user_verified")["read_by"], "user")
        bad = {**rec(updated="2026-10-21"), "read_by": "code"}
        self.assertTrue(any("read_by" in e for e in sources.validate_record(bad, registry=TA.REG, policy=POLICY)))

    def test_records_are_written_once(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": d}):
            r = rec(observed="2026-10-22")
            self.assertEqual(sources.append_records([r], registry=TA.REG, policy=POLICY), (1, 0))
            self.assertEqual(sources.append_records([rec(observed="2026-10-22")], registry=TA.REG, policy=POLICY), (0, 1))
            self.assertEqual(sources.append_records([rec(observed="2026-10-23")], registry=TA.REG, policy=POLICY), (1, 0))
            got = sources.read_records("autumn_leaves")
        self.assertEqual([(x["official_observed"], x["read_by"], x["freshness_basis"]) for x in got],
                         [("2026-10-22", "summary", "observed_date"), ("2026-10-23", "summary", "observed_date")])


class SimpleReadNote(unittest.TestCase):
    def compose(self, recs, **kw):
        return answer.compose(TA.parts(recs), now=TA.NOW, dates=TA.DATES, policy=POLICY, **kw)

    def test_summary_reads_say_so(self):
        note = POLICY["answer"]["simple_read_note"]
        self.assertEqual(note, "今回は簡易な読み取りです。表記のぶれがありえます")
        t = self.compose([rec(observed="2026-10-22")])
        self.assertIn(note, t.splitlines()[2])                                  # 冒頭(見出しの次)
        self.assertNotIn(note, self.compose([rec(observed="2026-10-22", method="code")]))
        self.assertIn("10/22時点", t)

    def test_record_failed_is_said_at_the_end(self):
        t = self.compose([rec(observed="2026-10-22", method="code")], record_failed=True)
        self.assertEqual(t.rstrip().splitlines()[-1], POLICY["answer"]["record_failed_note"])
        self.assertEqual(answer.forbidden_found(t, POLICY), [])


class MonthlyArticle(unittest.TestCase):
    def test_link_texts(self):
        src = {"follow": {"kind": "monthly_article", "link_text": "令和{era_year}年{month}月の白鳥の渡来状況"}}
        self.assertEqual([t["link_text"] for t in sources.monthly_targets(src, date(2026, 10, 24), POLICY)],
                         ["令和8年10月の白鳥の渡来状況", "令和8年9月の白鳥の渡来状況"])
        self.assertEqual([t["link_text"] for t in sources.monthly_targets(src, date(2027, 1, 5), POLICY)],
                         ["令和9年1月の白鳥の渡来状況", "令和8年12月の白鳥の渡来状況"])
        self.assertEqual(sources.monthly_targets({}, date(2026, 10, 24), POLICY), [])

    def test_the_hyoko_source_follows_the_monthly_article(self):
        reg = sources.load_registry("wintering_birds")
        hy = sources.sources_by_id(reg)["agano-hyoko-monthly"]
        self.assertEqual(hy["follow"]["kind"], "monthly_article")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["--subject", "wintering_birds", "follow", "--source", "agano-hyoko-monthly",
                                           "--now", "2026-10-24T14:00:00+09:00"]), 0)
        got = json.loads(out.getvalue())
        self.assertEqual(got["look_for"][0]["link_text"], "令和8年10月の白鳥の渡来状況")
        self.assertEqual(got["if_missing"]["human_url"], hy["url"])
        # 今月の記事の URL を記録に残せる(同じホスト)。羽数は原文のまま、段階は推測しない
        r = sources.make_record(registry=reg, policy=POLICY, source_id="agano-hyoko-monthly", site="hakucho-0001", label="白鳥の渡来状況",
                                read_at=READ_AT, state="3,386羽", observed="2026-10-23",
                                url="https://www.city.agano.niigata.jp/soshiki/koenkanrijimusho/2/2/16592.html")
        self.assertEqual((r["stage"], sources.validate_record(r, registry=reg, policy=POLICY)), (None, []))
        bad = {**r, "url": "https://other.example.org/16592.html"}
        self.assertTrue(any("ホスト" in e for e in sources.validate_record(bad, registry=reg, policy=POLICY)))


class Steps(unittest.TestCase):
    def test_the_steps_ask_once_and_record_before_answering(self):
        s = (ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("1 回だけ「公式ページをコードで読みます(通信が発生します)。よいですか」", "今回は簡易な読み取りです。表記のぶれがありえます",
                       "記録を残す(必ず。答えの前に)", "読んだ結果を記録できませんでした", "現地の状態の日付", "freshness_basis",
                       "follow --source", "if_missing.human_url"):
            self.assertIn(needle, s)
        d = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")
        self.assertIn(".claude/settings.local.json", d)
        self.assertIn("エージェント(Claude Code・Codex)はこのファイルを書き換えない", d)


if __name__ == "__main__":
    unittest.main()


class YearFromTheSameItem(unittest.TestCase):
    """段階17 の見直し(2026-10-24、ユーザーの判断): 年のない「M/D現在」は、同じ地点の年つきの最終更新日から年を補う。"""
    MARK = POLICY["freshness"]["observed_year_from_update_mark"]

    def test_the_year_comes_from_the_update_date_of_the_same_item(self):
        r = rec(observed_md="10-20", updated="2026-10-22")
        self.assertEqual((r["official_observed"], r["observed_year_inferred"]), ("2026-10-20", "from_same_item_update_date"))
        self.assertEqual(self.MARK, "from_same_item_update_date")
        self.assertEqual(sources.validate_record(r, registry=TA.REG, policy=POLICY), [])
        self.assertEqual(fresh(r)[2]["class"], "somewhat_old")                 # 年が分かるので日数で分ける(4 日)
        r = rec(observed_md="12-28", updated="2026-01-05")                      # 更新日の前の年(更新日以前で 60 日以内)
        self.assertEqual((r["official_observed"], r["observed_year_inferred"]), ("2025-12-28", self.MARK))

    def test_otherwise_the_year_stays_unknown(self):
        for kw in ({"observed_md": "10-20"},                                     # 年つきの日付がない(箱根など)
                   {"observed_md": "07-01", "updated": "2026-10-22"},            # 更新日から 60 日より前
                   {"observed_md": "10-23", "updated": "2026-10-22"},            # 更新日より後
                   {"observed_md": "10-20", "updated": "2026-10-22", "year_inferred": True}):   # 更新日の年も補ったもの
            r = rec(**kw)
            self.assertIs(r["observed_year_inferred"], True, kw)
            self.assertEqual(fresh(r)[2]["class"], "year_unknown", kw)

    def test_the_mark_is_checked(self):
        bad = {**rec(observed="2026-10-20"), "observed_year_inferred": self.MARK}  # 更新日がないのに印だけ
        self.assertTrue(any(self.MARK in e for e in sources.validate_record(bad, registry=TA.REG, policy=POLICY)))


class DedupWithYearFlags(unittest.TestCase):
    def test_a_record_with_a_better_year_is_not_a_duplicate(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": d}):
            self.assertEqual(sources.append_records([rec(updated="2026-10-22", year_inferred=True)], registry=TA.REG, policy=POLICY), (1, 0))
            self.assertEqual(sources.append_records([rec(updated="2026-10-22")], registry=TA.REG, policy=POLICY), (1, 0))   # 年が分かる記録は別の事実
            self.assertEqual(sources.append_records([rec(updated="2026-10-22")], registry=TA.REG, policy=POLICY), (0, 1))


class Superseded(unittest.TestCase):
    """段階17b(2026-10-24、ユーザーの指示): 読み直して置き換えた記録は erroneous ではなく superseded の印。読み違いと集計で混ざらない。"""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.d})
        self.env.start()
        self.addCleanup(self.env.stop)
        sources.append_records([rec(observed="2026-10-22"), rec(site="kouyou-0002", label="湖畔", state="◯", observed="2026-10-22")],
                               registry=TA.REG, policy=POLICY)

    def test_superseded_records_are_kept_but_not_used(self):
        self.assertEqual(sources.supersede_records("autumn_leaves", {"site": "kouyou-0002"}, reason="site で記録し直した", on="2026-10-24"), 1)
        self.assertEqual([r["site"] for r in sources.read_records("autumn_leaves")], ["kouyou-0001"])
        allr = sources.read_records("autumn_leaves", include_superseded=True)
        sup = next(r for r in allr if r["site"] == "kouyou-0002")
        self.assertEqual((sup["superseded"], sup["superseded_on"], "erroneous" in sup), (True, "2026-10-24", False))   # 誤りの印ではない
        self.assertEqual(sources.validate_record(sup, registry=TA.REG, policy=POLICY), [])
        self.assertEqual([r["site"] for r in sources.records_on("autumn_leaves", ON)], ["kouyou-0001"])
        self.assertEqual(len(sources.read_records("autumn_leaves", include_erroneous=True)), 1)   # 誤りの集計(include_erroneous)には入らない
        with self.assertRaises(ValueError):
            sources.append_records([sup], registry=TA.REG, policy=POLICY)

    def test_an_erroneous_mark_used_for_a_replacement_can_be_moved(self):
        sources.mark_erroneous("autumn_leaves", {"site": "kouyou-0002"}, reason="(読み違いではない置き換え)", corrected_on="2026-10-24")
        self.assertEqual(sources.erroneous_to_superseded("autumn_leaves", {"site": "kouyou-0002"}, reason="読み違いではない", on="2026-10-24"), 1)
        r = next(x for x in sources.read_records("autumn_leaves", include_erroneous=True, include_superseded=True) if x["site"] == "kouyou-0002")
        self.assertEqual((r.get("erroneous"), r.get("erroneous_reason"), r["superseded"]), (None, None, True))
        with self.assertRaises(ValueError):                                       # 誤りの印のない記録には当たらない
            sources.erroneous_to_superseded("autumn_leaves", {"site": "kouyou-0001"}, reason="x", on="2026-10-24")

    def test_both_marks_together_are_rejected(self):
        bad = {**rec(observed="2026-10-22"), "superseded": True, "superseded_on": "2026-10-24", "superseded_reason": "x",
               "erroneous": True, "erroneous_reason": "y", "corrected_on": "2026-10-24"}
        self.assertTrue(any("同時に" in e for e in sources.validate_record(bad, registry=TA.REG, policy=POLICY)))
        half = {**rec(observed="2026-10-22"), "superseded": True}
        self.assertTrue(any("そろえて" in e for e in sources.validate_record(half, registry=TA.REG, policy=POLICY)))
