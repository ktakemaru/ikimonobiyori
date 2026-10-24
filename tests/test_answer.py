"""答えの形(段階17 フェーズ1。ikimonobiyori/answer.py と、スキルの答えの例)。通信なし。合成のデータだけ。
結論が先・内部用語なし・同じ名所を 2 か所に出さない・日付は地点ごとに 1 つ・扱える範囲の 1 行。"""
import contextlib
import io
import os
import re
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import answer, catalog, sources

JST = timezone(timedelta(hours=9))
POLICY = sources.load_policy()
NOW = datetime(2026, 10, 24, 13, 54, tzinfo=JST)
DATES = [date(2026, 10, 31), date(2026, 11, 1)]
# 指示書(段階17 フェーズ1 の 3)の禁止語。方針の answer.forbidden_terms と同じであること
INSTRUCTED_TERMS = ["reader", "code", "record", "規則", "access_notes", "v0", "台帳", "approved", "pending", "provisional",
                    "status_log", "read_plan", "out_of_season"]


def src(sid, covers, kind="status_page", approved=True, notation=None):
    return {"id": sid, "publisher": "試験市観光協会", "publisher_kind": "tourism_association", "url": f"https://kankou.example.org/{sid}",
            "kind": kind, "covers": covers,
            "notation": notation or {"style": "symbol", "map": {"✕": "not_yet", "△": "starting", "◯": "good", "◎": "peak", "▼": "fading"},
                                     "updated": "per_item", "year_shown": True},
            "readable": {"status": "ok", "checked_on": "2026-10-23", "robots": "allows"}, "terms": {"status": "no_prohibition_found"},
            "approval": ({"status": "approved", "approved_by": "user", "approved_on": "2026-10-23"} if approved
                         else {"status": "pending", "reason": "試験"})}


def site(sid, name, tw=None, status_sources=(), **tags):
    e = {"id": sid, "name": name, "subjects": ["autumn_leaves"], "timing_type": "temperature", "kind": "point",
         "point": {"lat": 35.5, "lon": 139.5, "elevation_m": None}, "location_precision": "exact", "status": "approved",
         "approved_at": "2026-10-22", "sources": [{"url": "https://example.org/a"}], "status_sources": list(status_sources),
         "tags": {"prefecture": "東京都", **tags}}
    if tw:
        e["typical_window"] = {"start": tw[0], "end": tw[1], "source_url": "https://example.org/tw"}
    return e


REG = {"schema": "ikimono-status-sources/1", "subject": "autumn_leaves", "sources": [
    src("test-koyo", [{"site": "kouyou-0001", "label": "渓谷"}, {"site": "kouyou-0002", "label": "湖畔"}, {"site": "kouyou-0003", "label": "滝"}]),
    src("test-yearless", [{"site": "kouyou-0006", "label": "美術館"}],
        notation={"style": "word", "map": {"また来年": "fading"}, "updated": "per_item", "year_shown": False}),
    src("test-garden", [{"site": "kouyou-0004", "label": "庭園"}], approved=False)]}
CAT = {"schema": "ikimono-site-catalog/1", "subject": "autumn_leaves", "entries": [
    site("kouyou-0001", "試験の渓谷", ("10-11", "11-10"), ["test-koyo"], traffic_note="紅葉期は峠道が渋滞しやすい"),
    site("kouyou-0002", "試験の湖畔", ("10-11", "11-10"), ["test-koyo"]),
    site("kouyou-0003", "試験の滝", ("10-21", "11-20"), ["test-koyo"]),
    site("kouyou-0004", "試験の庭園", ("11-01", "11-30"), ["test-garden"]),
    site("kouyou-0005", "試験の高原", ("10-11", "11-10")),
    site("kouyou-0006", "試験の美術館", ("11-11", "11-30"), ["test-yearless"])]}


def records():
    mk = lambda source_id="test-koyo", **kw: sources.make_record(registry=REG, policy=POLICY, read_at=NOW.isoformat(), source_id=source_id, **kw)
    return [mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22", forecast="10月中旬～11月上旬"),
            mk(site="kouyou-0002", label="湖畔", state="◯", updated="2026-10-21"),
            mk(site="kouyou-0003", label="滝", state="△", updated="2026-10-22", forecast="10月下旬～11月上旬"),
            mk(source_id="test-yearless", site="kouyou-0006", label="美術館", state="また来年", updated="2026-10-06", year_inferred=True)]


def parts(recs=None):
    recs = records() if recs is None else recs
    return [{"subject": "autumn_leaves", "name": "紅葉", "catalog": CAT,
             "summary": sources.summarize(recs, registry=REG, catalog_doc=CAT, policy=POLICY, on=NOW.date(), dates=DATES),
             "candidates": sources.candidates(CAT, REG, DATES, POLICY), "care": None}]


def body_lines(text, heading):
    """見出し(## heading)の下の行。"""
    out, on = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            on = ln == f"## {heading}"
            continue
        if on and ln.strip():
            out.append(ln)
    return out


class AnswerForm(unittest.TestCase):
    def setUp(self):
        self.text = answer.compose(parts(), now=NOW, dates=DATES, policy=POLICY)
        self.h = POLICY["answer"]["headings"]

    def test_the_forbidden_terms_are_the_instructed_ones(self):
        self.assertEqual(POLICY["answer"]["forbidden_terms"], INSTRUCTED_TERMS)

    def test_conclusion_comes_first(self):
        heads = [ln[3:] for ln in self.text.splitlines() if ln.startswith("## ")]
        self.assertEqual(heads[0], self.h["recommend"])
        self.assertEqual(heads, [h for h in (self.h["recommend"], self.h["evidence"], self.h["notes"], self.h["unread"]) if h in heads])
        rec = body_lines(self.text, self.h["recommend"])
        self.assertEqual([re.search(r"\*\*(.+?)\*\*", ln).group(1) for ln in rec], ["試験の渓谷", "試験の湖畔", "試験の滝"])
        self.assertIn("見頃予測「10月下旬～11月上旬」が対象の日にかかる", rec[2])

    def test_no_internal_terms(self):
        self.assertEqual(answer.forbidden_found(self.text, POLICY), [])
        self.assertEqual(answer.forbidden_found("公式ページは pending です", POLICY), ["pending"])
        self.assertEqual(answer.forbidden_found("v0 によると", POLICY), ["v0"])
        self.assertEqual(answer.forbidden_found("https://example.org/record/code — 見ごろ", POLICY), [])   # URL の中は数えない
        self.assertEqual(answer.forbidden_found("encoder", POLICY), [])                                  # 語の一部は数えない

    def test_each_place_once(self):
        ev = body_lines(self.text, self.h["evidence"])
        unread = body_lines(self.text, self.h["unread"])
        names = [ln[2:].split(":")[0] for ln in ev + unread]
        self.assertEqual(len(names), len(set(names)), names)
        self.assertEqual([ln[2:].split(":")[0] for ln in unread], ["試験の庭園", "試験の高原"])   # 承認待ちと情報源なしを 1 か所に
        self.assertIn("https://kankou.example.org/test-garden", unread[0])
        self.assertNotIn("試験の美術館", "\n".join(ev))                          # 表示が古い可能性は根拠に出さず、注意に
        self.assertIn("試験の美術館", "\n".join(body_lines(self.text, self.h["notes"])))

    def test_one_date_per_place(self):
        for ln in body_lines(self.text, self.h["evidence"]) + body_lines(self.text, self.h["recommend"]):
            self.assertEqual(len(re.findall(r"\d+/\d+時点", ln)), 1, ln)
        self.assertNotIn("更新」は", self.text)                                 # 読み方の注記を書かない

    def test_scope_note_first_and_traffic_note(self):
        t = answer.compose(parts(), now=NOW, dates=DATES, policy=POLICY, scope_note="野鳥全般はまだ扱えません。冬鳥(白鳥)だけお答えします")
        first = [ln for ln in t.splitlines() if ln.strip()][1]
        self.assertEqual(first, "野鳥全般はまだ扱えません。冬鳥(白鳥)だけお答えします")
        self.assertIn("紅葉期は峠道が渋滞しやすい", "\n".join(body_lines(t, self.h["notes"])))

    def test_times_keep_the_year_and_offset(self):
        self.assertIn("2026年10月31日(土)・2026年11月1日(日)", self.text)
        self.assertIn("2026年10月24日 13:54(+09:00)", self.text)

    def test_nothing_read_says_so(self):
        t = answer.compose(parts([]), now=NOW, dates=DATES, policy=POLICY)
        self.assertIn(POLICY["answer"]["none_found"], t)
        self.assertEqual(answer.forbidden_found(t, POLICY), [])


class SkillExample(unittest.TestCase):
    def test_the_example_in_the_steps_has_no_internal_terms(self):
        s = (ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        ex = s[s.index("### 答えの例"):s.index("<!-- ikimono-weekend:end -->")]
        ex = ex[ex.index("```") + 3:ex.rindex("```")]
        self.assertEqual(answer.forbidden_found(ex, POLICY), [])
        self.assertIn(f"## {POLICY['answer']['headings']['recommend']}", ex.splitlines()[3])   # 結論が先
        self.assertIn("example.org", ex)                                                       # 合成の例(実在の名所ではない)

    def test_traffic_notes_in_the_catalogs_have_no_internal_terms(self):
        for st in sources.subjects_status():
            for e in catalog.approved_entries(catalog.load_catalog(st["subject"]) or {}):
                tn = (e.get("tags") or {}).get("traffic_note")
                if tn:
                    self.assertEqual(answer.forbidden_found(tn, POLICY), [], e["id"])


class AnswerCli(unittest.TestCase):
    def test_cli_on_an_empty_log(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": d}), contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["answer", "--now", NOW.isoformat(), "--subjects", "all"]), 0)
        self.assertEqual(answer.forbidden_found(out.getvalue(), POLICY), [])
        self.assertTrue(out.getvalue().splitlines()[0].startswith("**2026年10月24日(土)・2026年10月25日(日)の"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sources.main(["answer", "--now", NOW.isoformat(), "--subjects", "cherry_blossom"]), 2)


if __name__ == "__main__":
    unittest.main()
