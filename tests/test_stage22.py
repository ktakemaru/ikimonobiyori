"""段階22 A-1: 同じ名所に公式の項目が複数あるときの主項目の選び方(答えと提案で共有)。A-2: 「外しました」の行・注意の文の型。
通信なし。合成のデータだけ。"""
import re
import unittest
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

import test_answer as TA
from ikimonobiyori import answer, catalog, profiles, proposals, sources

POLICY = TA.POLICY
A = POLICY["answer"]
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=JST)
DATES = [date(2026, 10, 31), date(2026, 11, 1)]
PROFILES = profiles.load_profiles()
CAT_POLICY = catalog.load_policy()


def registry(primary=None):
    covers = [{"site": "kouyou-0001", "label": "【北】木々"}, {"site": "kouyou-0001", "label": "【北】草紅葉"},
              {"site": "kouyou-0002", "label": "湖畔"}]
    for c in covers:
        if c["label"] == primary:
            c["primary"] = True
    return {**TA.REG, "sources": [TA.src("test-koyo", covers)]}


def mk(reg, label, site="kouyou-0001", **kw):
    return sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", site=site, label=label, **kw)


def part(reg, recs, dates=DATES, early=False):
    return {"subject": "autumn_leaves", "name": "紅葉", "catalog": TA.CAT, "registry": reg,
            "summary": sources.summarize(recs, registry=reg, catalog_doc=TA.CAT, policy=POLICY, on=NOW.date(), dates=dates, early=early),
            "candidates": sources.candidates(TA.CAT, reg, dates, POLICY), "care": None}


def main_label(reg, recs, d):
    p = part(reg, recs)
    rows = [r for r in p["summary"]["rows"] if r.get("site") == "kouyou-0001"]
    return sources.primary_for(rows, d, reg, POLICY)[0]["label"]


def doc(reg, recs, dates=DATES):
    return proposals.build([part(reg, recs, dates)], PROFILES, policy=POLICY, catalog_policy=CAT_POLICY, now=NOW, dates=dates)


def rep_by_day(reg, recs):
    return {p["id"].split(":")[-2]: p["details"]["representative_label"] for p in doc(reg, recs)["proposals"]
            if p["details"]["site_id"] == "kouyou-0001"}


def text(reg, recs, dates=DATES, **kw):
    return answer.compose([part(reg, recs, dates, early=kw.get("early", False))], now=NOW, dates=dates, policy=POLICY, **kw)


def rec_lines(t):
    return TA.body_lines(t, A["headings"]["recommend"])


class PrimaryItem(unittest.TestCase):
    def test_a_forecasts_differ_the_one_whose_forecast_hits_is_primary(self):
        reg = registry()
        recs = [mk(reg, "【北】草紅葉", state="◎", updated="2026-10-25", forecast="9月下旬"),
                mk(reg, "【北】木々", state="◎", updated="2026-10-25", forecast="10月中旬～10月下旬")]
        self.assertEqual(main_label(reg, recs, date(2026, 10, 31)), "【北】木々")
        self.assertEqual(rep_by_day(reg, recs)["2026-10-31"], "【北】木々")
        t = text(reg, recs)
        line = next(ln for ln in rec_lines(t) if "試験の渓谷" in ln)
        self.assertIn("・木々", line)
        self.assertIn("10/31(土)は" + A["forecast_last_third"], line)
        self.assertNotIn(A["forecast_ended"].split(":")[0], t)                                        # 草紅葉(補助の項目)を理由に外さない
        ev = TA.body_lines(t, A["headings"]["evidence"])
        note = A["item_disagreement"]["past"].format(other="草紅葉", forecast="9月下旬", main="木々")
        self.assertIn(f"- 試験の渓谷: {note}", ev)                                                    # 予測が食い違う 1 行
        p = next(p for p in doc(reg, recs)["proposals"] if p["id"].endswith("2026-10-31:kouyou-0001"))
        self.assertEqual(p["details"]["item_notes"], [note])
        self.assertEqual([x["label"] for x in p["details"]["secondary_items"]], ["【北】草紅葉"])
        self.assertEqual({k for k in p["details"]["secondary_items"][0]},
                         {"label", "official_state", "stage", "official_observed", "official_updated", "official_forecast", "forecast_status"})

    def test_b_the_newer_state_date_is_primary(self):
        reg = registry()
        recs = [mk(reg, "【北】木々", state="◯", updated="2026-10-22"), mk(reg, "【北】草紅葉", state="◯", updated="2026-10-24")]
        self.assertEqual(main_label(reg, recs, DATES[0]), "【北】草紅葉")
        self.assertEqual(set(rep_by_day(reg, recs).values()), {"【北】草紅葉"})

    def test_c_fading_is_never_primary(self):
        reg = registry()
        recs = [mk(reg, "【北】木々", state="◯", updated="2026-10-20"), mk(reg, "【北】草紅葉", state="▼", updated="2026-10-25")]
        self.assertEqual(main_label(reg, recs, DATES[0]), "【北】木々")
        self.assertEqual(set(rep_by_day(reg, recs).values()), {"【北】木々"})

    def test_d_newer_peak_beats_older_good_like_chuzenji(self):
        reg = registry()
        recs = [mk(reg, "【北】草紅葉", state="◯", observed="2026-10-22", updated="2026-10-22", forecast="10月中旬～11月上旬"),
                mk(reg, "【北】木々", state="◎", observed="2026-10-25", updated="2026-10-25", forecast="10月中旬～11月上旬")]
        self.assertEqual(main_label(reg, recs, DATES[0]), "【北】木々")
        line = next(ln for ln in rec_lines(text(reg, recs)) if "試験の渓谷" in ln)
        self.assertIn("公式「◎」", line)
        self.assertIn("10/25時点", line)

    def test_more_advanced_state_then_the_registry_primary(self):
        reg = registry()
        recs = [mk(reg, "【北】木々", state="◯", updated="2026-10-24"), mk(reg, "【北】草紅葉", state="◎", updated="2026-10-24")]
        self.assertEqual(main_label(reg, recs, DATES[0]), "【北】草紅葉")                                 # ③ 状態が進んでいる
        same = [mk(reg, "【北】木々", state="◎", updated="2026-10-24"), mk(reg, "【北】草紅葉", state="◎", updated="2026-10-24")]
        self.assertEqual(main_label(reg, same, DATES[0]), "【北】木々")                                   # 決まらなければ地点の書き方の順
        reg2 = registry(primary="【北】草紅葉")
        same2 = [mk(reg2, "【北】木々", state="◎", updated="2026-10-24"), mk(reg2, "【北】草紅葉", state="◎", updated="2026-10-24")]
        self.assertEqual(main_label(reg2, same2, DATES[0]), "【北】草紅葉")                               # ④ 台帳の主項目

    def test_e_the_primary_can_change_by_day(self):
        reg = registry()
        recs = [mk(reg, "【北】木々", state="◎", updated="2026-10-25", forecast="10月下旬"),               # 10/21〜10/31
                mk(reg, "【北】草紅葉", state="◎", updated="2026-10-25", forecast="11月上旬")]              # 11/1〜11/10
        self.assertEqual(rep_by_day(reg, recs), {"2026-10-31": "【北】木々", "2026-11-01": "【北】草紅葉"})
        self.assertEqual(main_label(reg, recs, date(2026, 10, 31)), "【北】木々")                          # 答えは最初の対象の日で選ぶ

    def test_plan_b_is_judged_on_the_primary(self):
        reg = registry()
        # 主項目(木々)は予測がかかる。補助の項目(草紅葉)は予測を過ぎて状態も古い → 補助の項目のせいで外さない
        recs = [mk(reg, "【北】木々", state="◯", updated="2026-10-24", forecast="10月中旬～11月上旬"),
                mk(reg, "【北】草紅葉", state="◎", updated="2026-10-18", forecast="9月下旬")]
        t = text(reg, recs)
        self.assertTrue(any("試験の渓谷" in ln for ln in rec_lines(t) if re.match(r"\d+\. ", ln)))
        self.assertEqual({p["suitability"]["band"] for p in doc(reg, recs)["proposals"] if p["details"]["site_id"] == "kouyou-0001"}, {"maybe"})

    def test_the_registry_allows_one_primary_per_place(self):
        cat_ids = {e["id"] for e in TA.CAT["entries"]}
        src = TA.src("test-koyo", [{"site": "kouyou-0001", "label": "a", "primary": True}, {"site": "kouyou-0001", "label": "b", "primary": True}])
        errs = sources.check_source(src, subject="autumn_leaves", policy=POLICY, catalog_ids=cat_ids)
        self.assertTrue(any("主項目" in e for e in errs), errs)
        self.assertEqual(sources.schema_errors({**TA.REG, "sources": [TA.src("x-y", [{"site": "kouyou-0001", "label": "a", "primary": True}])]}), [])

    def test_the_real_registry_marks_senjogahara_trees_and_chuzenji_lake(self):
        reg = sources.load_registry("autumn_leaves")
        nikko = sources.sources_by_id(reg)["nikko-kankou-autumn-leaves"]
        self.assertEqual({c["site"]: c["label"] for c in nikko["covers"] if c.get("primary")},
                         {"kouyou-0002": "【奥日光】戦場ヶ原、小田代原の木々", "kouyou-0003": "【奥日光】中禅寺湖、華厳滝"})



class LeftOutLine(unittest.TestCase):
    """A-2 の 1: 「外しました」の行は、予測の時期を過ぎたために外した名所だけ。▼・✕は書かない。"""
    def lake(self, reg):
        return mk(reg, "湖畔", site="kouyou-0002", state="◯", updated="2026-10-24", forecast="10月中旬～11月上旬")

    def test_which_names_are_written(self):
        reg = registry()
        head = A["forecast_ended"].split(":")[0]
        for state, updated, listed in (("◎", "2026-10-18", True), ("◯", "2026-10-18", True), ("△", "2026-10-18", True),
                                       ("◎", None, True), ("▼", "2026-10-24", False), ("✕", "2026-10-24", False), ("▼", "2026-10-18", False)):
            with self.subTest(state=state, updated=updated):
                t = text(reg, [mk(reg, "【北】木々", state=state, updated=updated, forecast="10月上旬～10月中旬"), self.lake(reg)])
                got = [ln for ln in rec_lines(t) if ln.startswith(head)]
                self.assertEqual(bool(got), listed, t)
                if listed:
                    self.assertEqual(got, [A["forecast_ended"].format(names="試験の渓谷")])


class SentenceTypes(unittest.TestCase):
    """A-2 の 2: 注意の文の見頃予測の部分は「」で囲む(ハブも同じ型を使う。docs/proposal-mapping.md)。"""
    def test_forecast_is_quoted_in_every_fixed_sentence(self):
        for t in list(A["past_forecast"]["sentences"].values()) + list(A["item_disagreement"].values()) + [A["reasons"]["forecast"]]:
            self.assertIn("「{forecast}」", t)
            self.assertEqual(t.count("{forecast}"), 1)

    def test_the_mapping_doc_has_the_same_sentences(self):
        from pathlib import Path
        doc_text = (Path(__file__).resolve().parents[1] / "docs" / "proposal-mapping.md").read_text(encoding="utf-8")
        for t in list(A["past_forecast"]["sentences"].values()) + list(A["item_disagreement"].values()):
            self.assertIn(t, doc_text)


if __name__ == "__main__":
    unittest.main()
