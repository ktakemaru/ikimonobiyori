"""場所を分けた記録の現況・見頃の終わりごろ・行事の期間・安全の案内・今日の書き方(2026-11-28 の残る問題 1〜4・6)。合成データ(通信しない)。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as V
from ikimonobiyori import observations as O

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=JST)
BLOG = "https://www.kanagawaparks.com/kurihama/blog/"
QUESTION = "横浜から行ける場所で、花を見たい。見頃の花と場所を教えて。"


def rec(**kw):
    return {"subject": "flowers", "name": "くりはま花の国", "city": "横須賀市", "state": "つばき園では曙が開花しました。", "part": "つばき園",
            "state_date": "2026-11-27", "url": BLOG, "publisher": "試験の指定管理者", "source_class": "official", **kw}


class Tmp(unittest.TestCase):
    def setUp(self):
        self.old = os.environ["IKIMONOBIYORI_DATA_DIR"]
        os.environ["IKIMONOBIYORI_DATA_DIR"] = tempfile.mkdtemp(prefix="ikimono-part-")
        self.addCleanup(os.environ.__setitem__, "IKIMONOBIYORI_DATA_DIR", self.old)

    def kurihama(self, *records):
        O.record(list(records), now=NOW - timedelta(minutes=5))
        f = O.facts("flowers", region="神奈川", dates=[NOW.date()], now=NOW, origin="横浜")
        return next(x for x in f["candidates"] + f["avoid"] if x["name"] == "くりはま花の国")


class PartKind(unittest.TestCase):
    KINDS = ["コスモス", "ツバキ"]

    def test_hiragana_place_name_gives_the_flower(self):
        self.assertEqual(O.part_kind(rec(), self.KINDS), "ツバキ")           # 記録に kind がなく、本文はひらがな

    def test_other_flower_in_the_text_wins_over_the_place_name(self):
        r = rec(state="コスモス園の右サイドの皇帝ダリアは満開です", part="コスモス園")
        self.assertEqual(O.part_kind(r, self.KINDS, {"皇帝ダリア"}), "皇帝ダリア")

    def test_unknown_flower_is_not_counted(self):
        self.assertIsNone(O.part_kind(rec(state="色づいています", part="山頂"), self.KINDS))


class PartAsCurrent(Tmp):
    def test_part_record_counts_only_for_its_own_flower(self):
        c = self.kurihama(rec())
        self.assertEqual((c["current"]["kind"], c["current"]["part"]), ("ツバキ", "つばき園"))
        self.assertIsNone(c["avoid"])
        self.assertTrue(AP.has_this_year(c, 2026))

    def test_ended_cosmos_does_not_hide_tsubaki_and_tsubaki_is_not_cosmos(self):
        c = self.kurihama(rec(state="コスモスまつり終了について", part=None, state_date="2026-11-16"), rec())
        self.assertEqual(c["current"]["kind"], "ツバキ")
        self.assertNotIn("コスモス", c["current"]["state_raw"])

    def test_user_record_and_autumn_part_are_not_counted(self):
        O.record([{"subject": "autumn_leaves", "name": "試験の山", "part": "山頂", "state": "見頃", "state_date": "2026-11-27",
                   "url": BLOG, "publisher": "試験", "source_class": "official"}], now=NOW)
        f = O.facts("autumn_leaves", region="神奈川", dates=[NOW.date()], now=NOW, origin="横浜")
        self.assertFalse([x for x in f["candidates"] if x["name"] == "試験の山"])

    def test_brief_current_and_missing_do_not_contradict(self):
        """資料の「今年の現況」に事実がある場所は、「足りないもの」の現況がない候補にも、現況がないという行にも出ない。"""
        O.record([rec(), rec(name="県立相模原公園", city="相模原市", state="サザンカ 開花中", part="シャラノキゲート付近")], now=NOW - timedelta(minutes=5))
        d = GB.build(QUESTION, now=NOW)
        have = GB.places_with_current(d["facts"])
        self.assertIn(O._key("くりはま花の国"), have)
        for line in d["missing"]:
            if "現況がない候補" in line or "今年の情報が確認できていない候補" in line:
                for name in ("くりはま花の国", "県立相模原公園"):
                    self.assertNotIn(name, line)
        for f in d["facts"]:
            if f.get("place") and GB._has_current(f["place"], have):
                self.assertNotIn("今年の現況は分かりません", f["content"])
                self.assertNotIn("今年の情報は確認できていません", f["content"])
        fact = next(f for f in d["facts"] if f["kind"] == "current" and "くりはま花の国" in f["content"])
        self.assertIn("(つばき園)", fact["content"])


class OpenQuestionKinds(Tmp):
    def test_dahlia_in_cosmos_garden_is_not_a_cosmos_current(self):
        """コスモス園の皇帝ダリアの記録は、コスモスを聞いた質問の今年の現況にしない。ツバキのつばき園の記録は、ツバキの現況。"""
        from ikimonobiyori import current_status as CS
        O.record([rec(kind="皇帝ダリア", part="コスモス園の右サイド", state="コスモス園の右サイドの皇帝ダリアは満開です", state_date="2026-11-20"),
                  rec()], now=NOW - timedelta(minutes=5))
        cond = {"subjects": ["flowers"]}

        def states(words):
            return [r["state"] for r in CS.open_records("試験の質問", cond, NOW, species_words=words) if r["_name"] == "くりはま花の国"]
        self.assertEqual(states(["コスモス"]), [])
        self.assertEqual(states(["ツバキ", "つばき"]), ["つばき園では曙が開花しました。"])
        self.assertEqual(len(states(["皇帝ダリア"])), 1)


class LatePeak(unittest.TestCase):
    TEXT = "まだ見頃ですが、落葉が目立つようになってきました"

    def test_peak_with_falling_leaves_is_late_not_past(self):
        self.assertEqual(O.normalize("autumn_leaves", self.TEXT), "見頃")
        self.assertTrue(O.is_late_peak("autumn_leaves", self.TEXT))
        pol = AP.load_policy()
        c = {"current": {"state": "見頃", "late_peak": True, "state_date": "2026-11-27", "source_class": "official"}, "relation": "in_peak",
             "typical": [{"start": "11-11", "end": "11-30"}]}
        self.assertEqual(AP.outlook_of(c, NOW.date(), pol, "autumn_leaves"), "late")
        self.assertEqual(AP.outlook_of({**c, "typical": []}, NOW.date(), pol, "autumn_leaves"), "late")

    def test_other_wordings_are_unchanged(self):
        for text in ("山頂は落葉、山麓は見ごろ", "見頃過ぎ、落葉が目立ちます", "落葉が目立つ", "カラマツが見ごろです。落葉も進んでいる"):
            self.assertEqual(O.normalize("autumn_leaves", text), "見頃過ぎ", text)


class Events(Tmp):
    def test_newest_official_period_replaces_the_older_one(self):
        old = rec(part=None, state="コスモスまつり開催のお知らせ", state_date="2026-10-27",
                  event={"name": "試験まつり", "start": "2026-10-31", "end": "2026-11-29"})
        listed, kept = O.latest_events([], [{**old, "read_at": "2026-11-01T10:00:00+09:00"},
                                            {**old, "read_at": "2026-11-20T10:00:00+09:00", "event": {"name": "試験まつり", "start": "2026-10-31", "end": "2026-11-19"}}])
        self.assertEqual([e["end"] for e in kept], ["2026-11-19"])

    def test_cosmos_festival_period_follows_the_blog_notice(self):
        c = self.kurihama(rec(part=None, state="コスモス: 2分咲き", state_date="2026-10-27",
                              event={"name": "コスモスまつり", "start": "2026-10-31", "end": "2026-11-29"}))
        self.assertFalse([e for e in c["events"] if e["name"] == "コスモスまつり"])        # 11/28 は期間の後
        self.assertNotIn("11/29", str(c["typical_line"]))
        self.assertNotIn("コスモスまつりがあります", str(c["typical_line"]))


class SafetyNotice(Tmp):
    NOTICE = "9月の台風被害から復旧中で、園内はまだ全面復旧していません"

    def notice(self, text=None, day="2026-11-28"):
        return {"subject": "flowers", "name": "くりはま花の国", "notice": text or self.NOTICE, "state_date": day, "url": BLOG,
                "publisher": "試験の指定管理者", "source_class": "official", "basis": "page"}

    def facts(self, *records):
        O.record(list(records), now=NOW - timedelta(minutes=5))
        F = GB._Facts(GB.cfg(), set())
        GB._notice_facts(F, [{"name": "くりはま花の国"}], NOW, None, GB.cfg())
        return F.rows

    def test_active_notice_becomes_a_required_fact(self):
        rows = self.facts(self.notice())
        self.assertEqual([(r["kind"], r["fields"]["must_attach"]) for r in rows], [("safety", True)])
        brief = {"facts": rows}
        body = "**くりはま花の国**のつばき園が候補です。"
        self.assertEqual([e["code"] for e in V.must_attach_errors([{"ids": []}], body, brief, GB.cfg())], ["safety_notice_missing"])
        self.assertEqual(V.must_attach_errors([{"ids": [rows[0]["id"]]}], body, brief, GB.cfg()), [])
        self.assertEqual(V.must_attach_errors([{"ids": []}], "ほかの公園が候補です。", brief, GB.cfg()), [])

    def test_lifted_or_old_notice_is_not_required(self):
        self.assertEqual(self.facts(self.notice(day="2026-11-20"), self.notice("通行止めは解除されました")), [])

    def test_old_notice_is_not_required(self):
        self.assertEqual(self.facts(self.notice(day="2026-10-01")), [])


class TodayAndSpaces(unittest.TestCase):
    BRIEF = {"route": "season_place", "dates": {"today": "2026-11-28", "periods": [["2026-11-28", "2026-11-29"]]}}

    def codes(self, body, brief=None):
        return [e["code"] for e in V.today_errors(body, brief or self.BRIEF, GB.cfg())]

    def test_today_must_be_written_when_the_asked_day_is_today(self):
        self.assertEqual(self.codes("サザンカが目当てです。"), ["today_not_marked"])
        self.assertEqual(self.codes("今週末は11/28からです。"), ["today_not_marked"])
        self.assertEqual(self.codes("今日(11/28・土)に出かけるなら候補です。"), [])
        self.assertEqual(self.codes("今日（11/28・土）に出かけるなら候補です。"), [])

    def test_not_required_for_other_days_or_knowledge_questions(self):
        self.assertEqual(self.codes("説明です。", {**self.BRIEF, "route": "knowledge"}), [])
        self.assertEqual(self.codes("説明です。", {"route": "plan", "dates": {"today": "2026-11-28", "periods": [["2026-12-05"]]}}), [])

    def test_no_extra_space_after_marker_removal(self):
        out = V.strip_markers(["開花中です。[F001] 紅葉の丘も見られます。[F002]", "- 次の行 [F003]"], GB.cfg())
        self.assertEqual(out, "開花中です。紅葉の丘も見られます。\n- 次の行\n")


if __name__ == "__main__":
    unittest.main()
