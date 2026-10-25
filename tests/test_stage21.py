"""段階21: 終盤の注意を日ごとに書く・予測の時期を過ぎても公式の状態が新しい名所は残す(案B)・部位ごとの状態を根拠に添える・名前の重なりを直す。
通信なし。合成のデータだけ。読んだ時刻は 2026-10-24 13:54(+09:00)、対象の日は 10/31(土)・11/1(日)。"""
import json
import re
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

import test_answer as TA
from ikimonobiyori import answer, proposals, sources

POLICY, NOW, DATES = TA.POLICY, TA.NOW, TA.DATES
A = POLICY["answer"]
PF = A["past_forecast"]


def rec(site="kouyou-0001", label="渓谷", **kw):
    return sources.make_record(registry=TA.REG, policy=POLICY, read_at=NOW.isoformat(), source_id="test-koyo", site=site, label=label, **kw)


def text(recs, dates=DATES, **kw):
    p = [{**TA.parts(recs)[0], "summary": sources.summarize(recs, registry=TA.REG, catalog_doc=TA.CAT, policy=POLICY, on=NOW.date(), dates=dates,
                                                            early=kw.get("early", False)),
          "candidates": sources.candidates(TA.CAT, TA.REG, dates, POLICY)}]
    return answer.compose(p, now=NOW, dates=dates, policy=POLICY, **kw)


def lines(t, key):
    return TA.body_lines(t, A["headings"][key])


def picked(t):
    return [m.group(1) for ln in lines(t, "recommend") for m in [re.search(r"^\d+\. \*\*(.+?)\*\*", ln)] if m]


def rec_line(t, name="試験の渓谷"):
    return next(ln for ln in lines(t, "recommend") if name in ln and re.match(r"\d+\. ", ln))


def sentence(kind, forecast, when, state="◎"):
    return PF["sentences"][kind].format(forecast=forecast, when=when, state=state)


def lake():
    return rec("kouyou-0002", "湖畔", state="◯", updated="2026-10-22", forecast="10月中旬～11月上旬")        # 予測が対象の日にかかる


class PastForecastKept(unittest.TestCase):
    def test_a_peak_one_day_old_is_kept_with_the_fixed_sentence_and_ranked_after(self):
        t = text([rec(state="◎", updated="2026-10-23", forecast="10月上旬～10月中旬"), lake()])               # 予測は 10/20 に終わる。状態は 1 日前
        self.assertEqual(picked(t), ["試験の湖畔", "試験の渓谷"])                                                  # 予測がかかる名所より後ろ(◎でも)
        line = rec_line(t)
        self.assertIn(sentence("peak", "10月上旬～10月中旬", PF["when_updated"].format(md="10/23")), line)      # 更新日だけ → 「公式の更新日は10/23で、」
        self.assertNotIn("10/31(土)は", line)                                                                  # 両方の日に当てはまるので日を省く
        self.assertNotIn(A["forecast_ended"].split(":")[0], t)                                               # 外していない

    def test_a_dated_state_says_as_of(self):
        t = text([rec(state="◎", updated="2026-10-23", observed="2026-10-23", forecast="10月上旬～10月中旬")])
        self.assertIn(sentence("peak", "10月上旬～10月中旬", PF["when_observed"].format(md="10/23")), t)

    def test_a_peak_five_days_old_is_left_out_by_name_only(self):
        t = text([rec(state="◎", updated="2026-10-19", forecast="10月上旬～10月中旬"), lake()])
        self.assertEqual(picked(t), ["試験の湖畔"])
        self.assertIn(A["forecast_ended"].format(names="試験の渓谷"), lines(t, "recommend"))

    def test_the_limit_is_three_days(self):
        self.assertEqual(sources.val(PF["state_max_days"]), 3)
        self.assertEqual(picked(text([rec(state="◎", updated="2026-10-21", forecast="10月上旬～10月中旬")])), ["試験の渓谷"])   # ちょうど 3 日前
        self.assertEqual(picked(text([rec(state="◎", updated="2026-10-20", forecast="10月上旬～10月中旬")])), [])            # 4 日前

    def test_fading_is_left_out_even_if_new(self):
        t = text([rec(state="▼", updated="2026-10-23", forecast="10月上旬～10月中旬"), lake()])
        self.assertEqual(picked(t), ["試験の湖畔"])
        # 段階22 A-2(ユーザー承認): ▼・✕はもともと候補ではないので「外しました」の行に書かない
        self.assertNotIn(A["forecast_ended"].split(":")[0], t)

    def test_a_new_starting_state_is_kept_with_the_starting_sentence(self):
        t = text([rec(state="△", updated="2026-10-23", forecast="10月上旬～10月中旬")], early=True)             # 始まりも含める質問
        self.assertEqual(picked(t), ["試験の渓谷"])
        self.assertIn(sentence("starting", "10月上旬～10月中旬", PF["when_updated"].format(md="10/23")), t)
        self.assertIn("まだ色づき始め", t)
        self.assertNotIn("終わりに近い", t)

    def test_an_unknown_state_date_is_left_out(self):
        t = text([rec(state="◎", updated=None, forecast="10月上旬～10月中旬"), lake()])
        self.assertEqual(picked(t), ["試験の湖畔"])
        self.assertIn(A["forecast_ended"].format(names="試験の渓谷"), lines(t, "recommend"))

    def test_it_is_judged_per_day(self):
        t = text([rec(state="◎", updated="2026-10-23", forecast="10月中旬～10月下旬")])                         # 10/31 に終わる: 10/31 は予測の内、11/1 は過ぎた
        self.assertEqual(picked(t), ["試験の渓谷"])
        line = rec_line(t)
        self.assertIn("11/1(日)は公式の見頃予測は「10月中旬～10月下旬」ですが", line)                            # 11/1 だけに文が付く
        self.assertIn("10/31(土)は" + A["forecast_last_third"], line)                                         # 10/31 は最後の旬

    def test_the_proposal_agrees(self):
        row = {"order": 3, "freshness": {"class": "fresh", "age_days": 1}, "forecast_window": ["2026-10-11", "2026-10-20"]}
        band, keys = proposals.decide(row, date(2026, 10, 31), policy=POLICY, on=NOW.date(), scope={2, 3})
        self.assertEqual((band, keys), ("maybe", ["forecast_past"]))
        for bad in ({"order": 3, "freshness": {"class": "old", "age_days": 5}}, {"order": 4, "freshness": {"class": "fresh", "age_days": 1}},
                    {"order": 3, "freshness": {"class": "unknown", "age_days": None}}):
            self.assertEqual(proposals.decide({**row, **bad}, date(2026, 10, 31), policy=POLICY, on=NOW.date(), scope={2, 3})[0], "no")
        self.assertEqual(proposals.decide(row, date(2026, 10, 20), policy=POLICY, on=NOW.date(), scope={2, 3}), ("maybe", []))   # 予測の終わりの日まではこれまでどおり


class LastThirdPerDay(unittest.TestCase):
    def test_only_the_day_in_the_last_third_is_written(self):
        t = text([rec(state="◎", updated="2026-10-23", forecast="10月下旬～11月上旬")])                         # 予測は 11/10 まで。最後の旬は 11/1〜11/10
        line = rec_line(t)
        self.assertIn("11/1(日)は" + A["forecast_last_third"], line)
        self.assertNotIn("10/31", line)

    def test_a_single_day_question_omits_the_day(self):
        t = text([rec(state="◎", updated="2026-10-23", forecast="10月中旬～10月下旬")], dates=[date(2026, 10, 31)])
        line = rec_line(t)
        self.assertIn("。" + A["forecast_last_third"], line)
        self.assertNotIn("10/31(土)は", line)

    def test_both_days_in_the_last_third_omit_the_day(self):
        both = [date(2026, 10, 24), date(2026, 10, 25)]                                                       # 予測 10/31 まで → 最後の旬は 10/21〜10/31
        line = rec_line(text([rec(state="◎", updated="2026-10-23", forecast="10月中旬～10月下旬")], dates=both))
        self.assertIn("。" + A["forecast_last_third"], line)
        self.assertNotIn("10/24(土)は", line)
        self.assertNotIn("10/25(日)は", line)

    def test_no_note_in_the_middle_of_the_window(self):
        self.assertNotIn(A["forecast_last_third"], text([rec(state="◎", updated="2026-10-23", forecast="10月中旬～11月中旬")]))


class PartsInEvidence(unittest.TestCase):
    PARTS = [{"part": "山頂", "state": "終盤"}, {"part": "中腹", "state": "見ごろ"}, {"part": "山麓", "state": "色づき始め"}]

    def test_the_body_states_are_added_to_the_evidence_as_written(self):
        r = rec(state="◎", updated="2026-10-23", parts=self.PARTS)
        self.assertEqual(sources.validate_record(r, registry=TA.REG, policy=POLICY), [])
        t = text([r])
        ev = "\n".join(lines(t, "evidence"))
        self.assertIn("公式「◎」(真っ盛り)", ev)
        self.assertIn(A["parts_with_state"] + ": 山頂「終盤」、中腹「見ごろ」、山麓「色づき始め」", ev)
        self.assertIn("公式の更新日は10/23", ev)                                                               # 更新日だけ
        self.assertNotIn("山頂", rec_line(t))                                                                  # おすすめの行は短いまま

    def test_the_observed_date_is_written_when_it_differs_from_the_update(self):
        r = rec(state="◎", updated="2026-10-23", observed="2026-10-18", parts=self.PARTS)
        ev = "\n".join(lines(text([r]), "evidence"))
        self.assertIn("10/18時点", ev)
        self.assertIn("公式の更新日は10/23", ev)


class ReaderTakesBodyParts(unittest.TestCase):
    """日光のコードの読み取り: 本文が部位ごとに状態を書いているときだけ、書かれたとおりに official_parts へ(日付は取らない)。合成のページ。"""
    def test_parts_only_when_every_piece_is_part_and_state(self):
        from ikimonobiyori.fetch import status_pages as sp
        html = ("<div><h3>【鬼怒川・川治】日塩もみじライン</h3><p>現在の状況：◎</p><p>10/18山頂 終盤・中腹 見ごろ・山麓 色づき始め</p>"
                "<p>最終更新日：2026年10月22日</p></div>"
                "<div><h3>【奥日光】竜頭滝</h3><p>現在の状況：◯</p><p>10/19現在　見本の紹介文です。色づき始めました。</p><p>最終更新日：2026年10月22日</p></div>"
                "<div><h3>【奥日光】湯ノ湖、湯滝</h3><p>現在の状況：◎</p><p>見本の文章です</p><p>最終更新日：2026年10月22日</p></div>")
        covers = [{"site": "kouyou-0027", "label": "【鬼怒川・川治】日塩もみじライン"}, {"site": "kouyou-0026", "label": "【奥日光】竜頭滝"},
                  {"site": "kouyou-0001", "label": "【奥日光】湯ノ湖、湯滝"}]
        items, _ = sp.parse_nikko(html, covers)
        got = {it["label"]: it for it in items}
        shio = got["【鬼怒川・川治】日塩もみじライン"]
        self.assertEqual(shio["parts"], [{"part": "山頂", "state": "終盤"}, {"part": "中腹", "state": "見ごろ"}, {"part": "山麓", "state": "色づき始め"}])
        self.assertEqual((shio["state"], shio["updated"]), ("◎", "2026-10-22"))                                # 状態は「現在の状況」の原文のまま
        self.assertNotIn("observed_md", shio)                                                                  # 「10/18」は観察日として取らない
        self.assertNotIn("parts", got["【奥日光】竜頭滝"])                                                      # 文章は部位ではない
        self.assertEqual(got["【奥日光】竜頭滝"]["observed_md"], "10-19")
        self.assertNotIn("parts", got["【奥日光】湯ノ湖、湯滝"])


class NamesDoNotOverlap(unittest.TestCase):
    def test_a_label_already_in_the_name_is_not_repeated(self):
        names = {"kouyou-0003": "中禅寺湖・いろは坂(中禅寺温泉付近)", "kouyou-0002": "奥日光 戦場ヶ原(赤沼付近)"}
        n = lambda site, label: answer.place_name({"site": site, "label": label}, names, frozenset(names))
        self.assertEqual(n("kouyou-0003", "【奥日光】いろは坂"), "中禅寺湖・いろは坂(中禅寺温泉付近)")
        self.assertEqual(n("kouyou-0003", "【奥日光】中禅寺湖、華厳滝"), "中禅寺湖・いろは坂(中禅寺温泉付近)・華厳滝")
        self.assertEqual(n("kouyou-0002", "【奥日光】戦場ヶ原、小田代原の木々"), "奥日光 戦場ヶ原(赤沼付近)・小田代原の木々")
        self.assertEqual(n("kouyou-0002", "【奥日光】小田代原の草紅葉"), "奥日光 戦場ヶ原(赤沼付近)・小田代原の草紅葉")

    def test_a_single_label_site_is_just_the_name(self):
        self.assertEqual(answer.place_name({"site": "kouyou-0001", "label": "渓谷"}, {"kouyou-0001": "試験の渓谷"}), "試験の渓谷")


class NoMeaninglessFixedSentence(unittest.TestCase):
    def test_no_such_sentence_anywhere(self):
        self.assertNotIn("いちばん新しい", json.dumps(POLICY, ensure_ascii=False))
        for t in (text(TA.records()), text([rec(state="◎", updated="2026-10-23")])):
            self.assertNotIn("いちばん新しい", t)


if __name__ == "__main__":
    unittest.main()
