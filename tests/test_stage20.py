"""段階20: 見頃予測が対象の日より前に終わる名所を外す・日付の書き方・部位ごとの状態・読む情報源の漏れ・ほかの候補。通信なし。合成のデータだけ。"""
import re
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

import test_answer as TA
from ikimonobiyori import answer, sources

POLICY, NOW, DATES = TA.POLICY, TA.NOW, TA.DATES
A = POLICY["answer"]


def rec(site="kouyou-0001", label="渓谷", **kw):
    return sources.make_record(registry=TA.REG, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", site=site, label=label, **kw)


def text(recs, **kw):
    return answer.compose(TA.parts(recs), now=NOW, dates=kw.pop("dates", DATES), policy=POLICY, **kw)


def lines(t, key):
    return TA.body_lines(t, A["headings"][key])


def picked(t):
    return [m.group(1) for ln in lines(t, "recommend") for m in [re.search(r"^\d+\. \*\*(.+?)\*\*", ln)] if m]


class ThirdsAndEnded(unittest.TestCase):
    def test_the_thirds_are_jma_ones(self):
        f = lambda y, m, d: sources.last_third_start(date(y, m, d), POLICY)
        self.assertEqual([f(2026, 10, 10), f(2026, 10, 11), f(2026, 10, 20), f(2026, 10, 21), f(2026, 10, 31), f(2026, 11, 1)],
                         [date(2026, 10, 1), date(2026, 10, 11), date(2026, 10, 11), date(2026, 10, 21), date(2026, 10, 21), date(2026, 11, 1)])

    def test_a_forecast_ending_before_the_day_is_left_out_by_name_only(self):
        t = text([rec(state="◎", updated="2026-10-22", forecast="10月上旬～10月中旬"),                       # 10/20 に終わる
                  rec("kouyou-0002", "湖畔", state="◯", updated="2026-10-22", forecast="10月中旬～11月上旬")])
        self.assertEqual(picked(t), ["試験の湖畔"])
        self.assertIn(A["forecast_ended"].format(names="試験の渓谷"), lines(t, "recommend"))
        self.assertNotIn(A["other_candidates"].split("(")[0], t)                       # 外した名所を「ほかの候補」に二重に出さない

    def test_a_forecast_ending_on_the_day_stays_and_warns_of_the_end(self):
        t = text([rec(state="◎", updated="2026-10-22", forecast="10月中旬～10月下旬")])      # 10/31 に終わる。対象の日 10/31 は最後の旬
        self.assertEqual(picked(t), ["試験の渓谷"])
        self.assertIn(A["forecast_last_third"], t)

    def test_the_day_after_the_last_third_it_is_out(self):
        t = text([rec(state="◎", updated="2026-10-22", forecast="10月中旬～10月下旬")], dates=[date(2026, 11, 1)])
        self.assertEqual(picked(t), [])
        self.assertIn(A["forecast_ended"].format(names="試験の渓谷"), lines(t, "recommend"))

    def test_a_forecast_in_the_middle_has_no_warning(self):
        t = text([rec(state="◎", updated="2026-10-22", forecast="10月中旬～11月中旬")])      # 11/20 に終わる。対象の日 10/31・11/1 は最後の旬の前
        self.assertNotIn(A["forecast_last_third"], t)

    def test_the_answer_has_no_work_report(self):
        t = text([rec(state="◎", updated="2026-10-22")])
        for w in ("提案", "biyori-proposal", "テスト", "作業メモ"):
            self.assertNotIn(w, t)
        memo = answer.work_memo(POLICY, record_failed=True)
        self.assertIn(A["work_memo_heading"], memo)
        self.assertIsNone(answer.work_memo(POLICY))


class ProposalAgrees(unittest.TestCase):
    def test_a_day_after_the_forecast_ended_is_no(self):
        from ikimonobiyori import proposals
        row = {"order": 3, "freshness": {"class": "fresh"}, "forecast_window": ["2026-10-11", "2026-10-20"]}
        band, _ = proposals.decide(row, date(2026, 10, 31), policy=POLICY, on=NOW.date(), scope={2, 3})
        self.assertEqual(band, "no")
        band, _ = proposals.decide(row, date(2026, 10, 20), policy=POLICY, on=NOW.date(), scope={2, 3})
        self.assertEqual(band, "maybe")


class OtherCandidates(unittest.TestCase):
    def test_places_whose_forecast_hits_but_were_not_picked_are_named(self):
        n = POLICY["recommend"]["top_max"]["value"]
        cat = {**TA.CAT, "entries": [TA.site(f"kouyou-9{i:03d}", f"試験の地{i}", ("10-11", "11-10"), ["test-many"]) for i in range(n + 1)]}
        reg = {**TA.REG, "sources": [TA.src("test-many", [{"site": e["id"], "label": f"地{i}"} for i, e in enumerate(cat["entries"])])]}
        recs = [sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-many", site=e["id"], label=f"地{i}",
                                    state="◎", updated="2026-10-22", forecast="10月中旬～11月上旬") for i, e in enumerate(cat["entries"])]
        soon = [date(2026, 10, 26)]                                                      # 読んだ日に近い日(先の日の見出しを足さない)
        p = [{**TA.parts()[0], "catalog": cat, "summary": sources.summarize(recs, registry=reg, catalog_doc=cat, policy=POLICY, on=NOW.date(), dates=soon),
              "candidates": sources.candidates(cat, reg, soon, POLICY)}]
        t = answer.compose(p, now=NOW, dates=soon, policy=POLICY)
        self.assertEqual(len(picked(t)), n)
        others = [ln for ln in lines(t, "recommend") if ln.startswith(A["other_candidates"].split("(")[0])]
        self.assertEqual(len(others), 1)
        left = [e["name"] for e in cat["entries"] if e["name"] not in picked(t)]
        self.assertEqual(len(left), 1)
        self.assertIn(left[0], others[0])


class Dates(unittest.TestCase):
    def row(self, **kw):
        r = rec(state="◎", **kw)
        return sources.summarize([r], registry=TA.REG, catalog_doc=TA.CAT, policy=POLICY, on=NOW.date(), dates=DATES)["rows"][0]

    def test_observed_date_is_a_point_in_time(self):
        self.assertEqual(answer.as_of(self.row(observed="2026-10-22", updated="2026-10-22"), NOW.date(), POLICY), "10/22時点")

    def test_updated_date_alone_is_not_called_a_point_in_time(self):
        s = answer.as_of(self.row(updated="2026-10-22"), NOW.date(), POLICY)
        self.assertEqual(s, "公式の更新日は10/22")
        self.assertNotIn("時点", s)

    def test_both_far_apart_are_both_told(self):
        s = answer.as_of(self.row(observed="2026-10-15", updated="2026-10-22"), NOW.date(), POLICY)
        self.assertEqual(s, "10/15時点、公式の更新日は10/22")

    def test_the_year_of_a_bare_observed_date_comes_from_the_same_items_update_date(self):
        r = self.row(observed_md="10-20", updated="2026-10-22")
        self.assertEqual((r["official_observed"], r["observed_year_inferred"]), ("2026-10-20", POLICY["freshness"]["observed_year_from_update_mark"]))
        self.assertEqual(answer.as_of(r, NOW.date(), POLICY), "10/20時点")


class Parts(unittest.TestCase):
    PARTS = [{"part": "山頂", "state": "△"}, {"part": "中腹", "state": "◎"}, {"part": "山麓", "state": "◯"}]

    def test_states_that_differ_by_part_are_told_as_written(self):
        r = rec(state=None, updated="2026-10-22", observed="2026-10-22", parts=self.PARTS)
        self.assertEqual(sources.validate_record(r, registry=TA.REG, policy=POLICY), [])
        t = text([r])
        ev = "\n".join(lines(t, "evidence"))
        self.assertIn("山頂「△」、中腹「◎」、山麓「◯」", ev)
        self.assertNotIn("真っ盛り", ev)                                                # 1 つの「◎」にまとめない
        self.assertEqual(picked(t), [])                                                  # 部位ごとに違う地点を 1 つの段階でおすすめしない

    def test_bad_parts_are_refused(self):
        r = rec(state=None, updated="2026-10-22", parts=[{"part": "山頂"}])
        self.assertTrue(sources.validate_record(r, registry=TA.REG, policy=POLICY))


class ReadEverythingThatOverlaps(unittest.TestCase):
    def test_every_approved_source_of_a_place_in_or_near_its_season_is_planned(self):
        c = sources.candidates(TA.CAT, TA.REG, DATES, POLICY)
        planned = {s["id"] for s in c["read_plan"]}
        margin = POLICY["candidates"]["window_margin_days"]["value"]
        seen = 0
        for e in TA.CAT["entries"]:
            tw = e.get("typical_window")
            near = tw and min(sources.days_from_window(d, tw) for d in DATES) <= margin
            for sid in e["status_sources"]:
                if near and sources.is_approved(sources.sources_by_id(TA.REG)[sid]):
                    seen += 1
                    self.assertIn(sid, planned, (e["id"], sid))
        self.assertGreater(seen, 0)

    def test_an_unread_planned_source_gets_a_reason_line(self):
        p = TA.parts([])                                                                 # 何も読めなかった
        t = answer.compose(p, now=NOW, dates=DATES, policy=POLICY, unread_reasons={"test-koyo": "ページが開けなかった"})
        self.assertIn(A["unread_reason"].format(reason="ページが開けなかった"), "\n".join(lines(t, "unread")))
        t2 = answer.compose(p, now=NOW, dates=DATES, policy=POLICY)
        self.assertIn(A["unread_reason_unknown"], "\n".join(lines(t2, "unread")))


if __name__ == "__main__":
    unittest.main()
