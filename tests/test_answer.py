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
        if on and ln.strip() and not ln.startswith("#") and not re.fullmatch(r"\*\*[^*]+\*\*", ln):   # 小見出し(段階・対象)は数えない
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
            # 段階20: 本文に「現在」の日付があれば「○/○時点」、更新日だけなら「公式の更新日は○/○」(どちらも 1 つ)
            self.assertEqual(len(re.findall(r"\d+/\d+時点|公式の更新日は\d+/\d+", ln)), 1, ln)
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


class AnswerOrdering(unittest.TestCase):
    """段階17 フェーズ2 で実際の記録に当てて見つけた点: 同じ名所の複数の地点・見頃予測を過ぎた地点・複数の対象。"""
    def test_two_labels_of_one_site_are_told_apart(self):
        reg = {**REG, "sources": [src("test-koyo", REG["sources"][0]["covers"] + [{"site": "kouyou-0001", "label": "【北】渓谷の上流"}])] + REG["sources"][1:]}
        mk = lambda **kw: sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", **kw)
        recs = [mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22"), mk(site="kouyou-0001", label="【北】渓谷の上流", state="△", updated="2026-10-22")]
        p = [{**parts()[0], "summary": sources.summarize(recs, registry=reg, catalog_doc=CAT, policy=POLICY, on=NOW.date(), dates=DATES)}]
        ev = body_lines(answer.compose(p, now=NOW, dates=DATES, policy=POLICY), POLICY["answer"]["headings"]["evidence"])
        self.assertEqual([ln[2:].split(":")[0] for ln in ev], ["試験の渓谷・渓谷", "試験の渓谷・渓谷の上流"])   # 【…】は外して添える

    def test_a_place_past_its_forecast_goes_after(self):
        mk = lambda **kw: sources.make_record(registry=REG, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", **kw)
        recs = [mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-18", forecast="10月上旬～10月中旬"),     # 段階21: 状態が 3 日より古い
                mk(site="kouyou-0002", label="湖畔", state="◯", updated="2026-10-22", forecast="10月下旬～11月上旬")]
        rec_lines = body_lines(answer.compose(parts(recs), now=NOW, dates=DATES, policy=POLICY), POLICY["answer"]["headings"]["recommend"])
        # 段階20: 見頃予測が対象の日より前に終わる渓谷は、後ろに回すのではなくおすすめから外し、名前だけ 1 行で書く
        picked = [re.search(r"\*\*(.+?)\*\*", ln).group(1) for ln in rec_lines if re.search(r"\*\*(.+?)\*\*", ln)]
        self.assertEqual(picked, ["試験の湖畔"])
        self.assertIn("予測の時期を過ぎる見込みのため外しました: 試験の渓谷", rec_lines)

    def test_each_subject_gets_its_own_recommendations(self):
        other = {**parts()[0], "subject": "wintering_birds", "name": "冬鳥"}
        t = answer.compose(parts() + [other], now=NOW, dates=DATES, policy=POLICY)
        rec = re.split(r"\n## ", t.split(f"## {POLICY['answer']['headings']['recommend']}")[1])[0]
        self.assertIn("### 紅葉", rec)
        self.assertIn("### 冬鳥", rec)


class AnswerFilters(unittest.TestCase):
    """段階17 フェーズ7 の答え直しで見つけた点: 地域で絞ったときの根拠、情報なしの書き方を見頃予測で選ばない。"""
    def test_a_region_keeps_only_its_places(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        reg = sources.load_registry("autumn_leaves")
        at = NOW.isoformat()
        recs = [sources.make_record(registry=reg, policy=POLICY, read_at=at, source_id="hakone-kankou-koyo", name="宮ノ下", label="宮ノ下",
                                    state="色づきはじめ", updated="2026-10-22", year_inferred=True),
                sources.make_record(registry=reg, policy=POLICY, read_at=at, source_id="hakone-kankou-koyo", site="kouyou-0034",
                                    label="仙石原(長安寺)", state="色づきはじめ", updated="2026-10-23", year_inferred=True),
                sources.make_record(registry=reg, policy=POLICY, read_at=at, source_id="nikko-kankou-autumn-leaves", site="kouyou-0028",
                                    label="【湯西川・川俣・奥鬼怒】瀬戸合峡", state="◎", updated="2026-10-21")]
        with mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": d}):
            sources.append_records(recs, registry=reg, policy=POLICY)
            hakone = sources.resolve_region("箱根", sources.load_regions())
            rows = sources.answer_parts(["autumn_leaves"], policy=POLICY, now=NOW, dates=DATES, region=hakone)[0]["summary"]["rows"]
            self.assertEqual(sorted(r.get("site") or r.get("name") for r in rows), ["kouyou-0034", "宮ノ下"])   # 日光は出さない
            rows = sources.answer_parts(["autumn_leaves"], policy=POLICY, now=NOW, dates=DATES, region=hakone, terrain=["highland"])[0]["summary"]["rows"]
            self.assertEqual([r.get("site") or r.get("name") for r in rows], ["kouyou-0034"])   # カタログ外の地点は地形が分からないので外す

    def test_places_before_their_season_get_the_typical_start(self):
        notes = body_lines(answer.compose(parts(), now=NOW, dates=DATES, policy=POLICY), POLICY["answer"]["headings"]["notes"])
        self.assertIn("- 試験の美術館: 例年の時期はこれから(11月11日ごろから)", notes)

    def test_no_info_is_not_recommended_by_forecast(self):
        reg = {**REG, "sources": [{**REG["sources"][0], "notation": {**REG["sources"][0]["notation"], "no_info": ["現在、情報がありません"]}}] + REG["sources"][1:]}
        r = sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", site="kouyou-0003", label="滝",
                                state="現在、情報がありません", updated="2026-10-23", forecast="10月下旬～11月上旬")
        p = [{**parts()[0], "summary": sources.summarize([r], registry=reg, catalog_doc=CAT, policy=POLICY, on=NOW.date(), dates=DATES)}]
        t = answer.compose(p, now=NOW, dates=DATES, policy=POLICY)
        self.assertEqual(body_lines(t, POLICY["answer"]["headings"]["recommend"]), [POLICY["answer"]["none_found"]])
        self.assertIn("現在、情報がありません", "\n".join(body_lines(t, POLICY["answer"]["headings"]["evidence"])))   # 根拠には出す


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


class ReviewOfStage17(unittest.TestCase):
    """段階17 の見直し(2026-10-24、ユーザー承認): 段階ごとの見出し・先の週末の見頃予測・状態の記載がない発信・参考リンク。"""
    def compose(self, recs, dates=DATES, **kw):
        p = [{**parts()[0], "summary": sources.summarize(recs, registry=REG, catalog_doc=CAT, policy=POLICY, on=NOW.date(), dates=dates,
                                                         early=kw.get("early", False))}]
        return answer.compose(p, now=NOW, dates=dates, policy=POLICY, **kw)

    def mk(self, **kw):
        return sources.make_record(registry=REG, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", **kw)

    def test_early_gives_stage_headings(self):
        recs = [self.mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22"),
                self.mk(site="kouyou-0002", label="湖畔", state="△", updated="2026-10-22")]
        t = self.compose(recs, dates=[date(2026, 10, 25)], early=True)
        sh = POLICY["answer"]["stage_headings"]
        rec = re.split(r"\n## ", t.split(f"## {POLICY['answer']['headings']['recommend']}")[1])[0]
        self.assertLess(rec.index(f"### {sh['default']}"), rec.index("試験の渓谷"))
        self.assertLess(rec.index(f"### {sh['early']}"), rec.index("試験の湖畔"))
        self.assertLess(rec.index("試験の渓谷"), rec.index(f"### {sh['early']}"))

    def test_a_later_weekend_lists_places_whose_forecast_hits(self):
        recs = [self.mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22"),
                self.mk(site="kouyou-0002", label="湖畔", state="◯", updated="2026-10-22"),
                self.mk(site="kouyou-0003", label="滝", state="✕", updated="2026-10-22", forecast="10月下旬～11月上旬")]
        sh = POLICY["answer"]["stage_headings"]
        t = self.compose(recs)                                                   # 対象の日(10/31)が読んだ日(10/24)から 7 日先
        self.assertIn(f"### {sh['ahead']}", t)
        self.assertIn("試験の滝", t.split(f"### {sh['ahead']}")[1].split("\n## ")[0])   # 今は「まだ」でも見頃予測が対象の日にかかる
        near = self.compose(recs, dates=[date(2026, 10, 25)])
        self.assertNotIn(sh["ahead"], near)                                      # 今週末なら見出しを足さない

    def test_a_page_without_a_state_is_a_human_url(self):
        recs = [self.mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22"),
                self.mk(site="kouyou-0002", label="湖畔", state=None)]
        t = self.compose(recs)
        unread = body_lines(t, POLICY["answer"]["headings"]["unread"])
        self.assertIn(f"- 試験の湖畔: {POLICY['answer']['no_state']}、{POLICY['answer']['human_url']}: https://kankou.example.org/test-koyo", unread)
        self.assertNotIn("試験の湖畔", "\n".join(body_lines(t, POLICY["answer"]["headings"]["evidence"])))

    def test_reference_links_are_not_status_sources(self):
        ref = {**src("test-ref", [{"site": "kouyou-0005", "label": "高原"}]), "kind": "reference_link"}
        reg = {**REG, "sources": REG["sources"] + [ref]}
        cat = {**CAT, "entries": [e if e["id"] != "kouyou-0005" else {**e, "status_sources": ["test-ref"]} for e in CAT["entries"]]}
        self.assertEqual(sources.check_registry(reg, name="autumn_leaves", catalog_doc=cat, policy=POLICY), [])
        c = sources.candidates(cat, reg, DATES, POLICY)
        self.assertNotIn("test-ref", [x["id"] for x in c["read_plan"]])
        self.assertEqual([x["id"] for x in c["reference_links"]], ["test-ref"])
        self.assertIn("kouyou-0005", c["no_status_source"])                      # 現況の情報源には数えない
        p = [{**parts()[0], "catalog": cat, "candidates": c}]
        unread = body_lines(answer.compose(p, now=NOW, dates=DATES, policy=POLICY), POLICY["answer"]["headings"]["unread"])
        self.assertIn(f"- 試験の高原: 例年 10/11〜11/10、{POLICY['answer']['unread_no_url']}、{POLICY['answer']['reference_link']}: https://kankou.example.org/test-ref", unread)
        for subj, sid in (("birds", "tokyo-park-kasai-news"), ("birds", "wbsj-yokohama-blog"), ("flowers", "tokyo-park-jindai-news")):
            s = sources.sources_by_id(sources.load_registry(subj))[sid]
            self.assertEqual((s["kind"], s["approval"]["status"]), ("reference_link", "approved"), sid)   # 取り消さずに参考リンク


class AheadHeadingOrder(unittest.TestCase):
    """段階17b(2026-10-24、ユーザーの指示): 「対象の日に公式の見頃予測の時期」の見出しは、今の段階に関わらず、
    公式の見頃予測が対象の日にかかる地点を、予測の時期が対象の日に近い順に最大 5 件。「見ごろ〜最盛」と重ねない。"""
    def test_not_yet_places_whose_forecast_is_closest_come_first(self):
        far = [f"色づき{i}" for i in range(4)]
        covers = REG["sources"][0]["covers"] + [{"name": n, "label": n} for n in ["霧降滝", "日光の社寺"] + far]
        reg = {**REG, "sources": [{**REG["sources"][0], "covers": covers}] + REG["sources"][1:]}
        mk = lambda **kw: sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", **kw)
        recs = [mk(site="kouyou-0001", label="渓谷", state="◎", updated="2026-10-22", forecast="10月中旬～11月上旬"),
                mk(name="霧降滝", label="霧降滝", state="✕", updated="2026-10-15", forecast="10月下旬～11月上旬"),      # 予測の真ん中 10/31
                mk(name="日光の社寺", label="日光の社寺", state="✕", updated="2026-09-13", forecast="11月上旬～11月中旬")]  # 11/10
        recs += [mk(name=n, label=n, state="△", updated="2026-10-22", forecast="10月上旬～11月上旬") for n in far]  # 10/21(遠い)
        p = [{**parts()[0], "summary": sources.summarize(recs, registry=reg, catalog_doc=CAT, policy=POLICY, on=NOW.date(), dates=DATES)}]
        t = answer.compose(p, now=NOW, dates=DATES, policy=POLICY)
        sh = POLICY["answer"]["stage_headings"]
        ahead = t.split(f"### {sh['ahead']}")[1].split("\n## ")[0]
        got = [re.search(r"\*\*(.+?)\*\*", ln).group(1) for ln in ahead.splitlines() if re.match(r"\d+\. ", ln)]
        self.assertEqual(got[:2], ["霧降滝", "日光の社寺"])                          # 今は「まだ」でも、予測の時期が近い順で先に
        self.assertEqual(len(got), sources.val(POLICY["recommend"]["top_max"]))
        self.assertNotIn("試験の渓谷", got)                                           # 「見ごろ〜最盛」で選んだ名所は重ねない
        self.assertIn("試験の渓谷", t.split(f"### {sh['default']}")[1].split(f"### {sh['ahead']}")[0])

    def test_distance(self):
        row = {"forecast_window": ["2026-10-21", "2026-11-10"]}
        self.assertEqual(answer.forecast_distance(row, DATES), 0.5)
        self.assertIsNone(answer.forecast_distance({}, DATES))
