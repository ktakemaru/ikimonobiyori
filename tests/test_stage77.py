"""段階77: 新しい形の仕上げ(対象の日の言い切り・行事のカード・野鳥の遠くの候補・出典の名前と区分・西暦)と既定の切り替え。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import final_check as FC
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import observations as O
from ikimonobiyori import stop_hook as SH

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)
PL = "\n\n[場所]\n記録: 試験の渓谷\n"


def brief():
    c = GB.cfg()

    def f(fid, kind, content, observed=None, url="https://example.org/a"):
        return {"id": fid, "kind": kind, "kind_label": c["kinds"][kind], "place": "試験の渓谷", "content": content, "values": GB.values(content),
                "source": "試験町", "source_class": "official", "url": url, "observed": observed, "read_at": None}
    return {"id": "b-s77", "question": "今週末の紅葉は?", "candidates": [{"name": "試験の渓谷"}],
            "dates": {"today": "2026-11-10", "this_weekend": ["2026-11-14", "2026-11-15"], "next_weekend": ["2026-11-21", "2026-11-22"],
                      "periods": [["2026-11-14", "2026-11-15"]]},
            "facts": [f("F001", "current", "試験の渓谷: 真っ盛り(11/7時点、試験町)", "2026-11-07"),
                      f("F002", "safety", "試験の峠道: 令和8年11月19日11時〜令和9年4月15日11時 冬期閉鎖", url="https://example.org/r")],
            "cards": [], "fallback": {"text": "今の形の答え\n"}}


def codes(body):
    return [e["code"] for e in GV.check(body + PL, brief())["errors"]]


class StaleAsTarget(unittest.TestCase):
    def test_old_state_stated_as_the_target_day_fails(self):
        self.assertIn("stale_as_target", codes("今週末の紅葉は、試験の渓谷では真っ盛りです。[F001]"))
        self.assertIn("stale_as_target", codes("11月14日の試験の渓谷は真っ盛りです。[F001]"))

    def test_reported_with_the_date_or_as_an_outlook_passes(self):
        self.assertEqual(codes("11月7日時点では、試験の渓谷は真っ盛りでした。[F001] 今週末は盛りを過ぎているかもしれません。[F001]"), [])
        self.assertEqual(codes("試験の渓谷は11/7時点で真っ盛りで、今週末は見頃が続く見込みです。[F001]"), [])
        self.assertEqual(codes("試験の渓谷は真っ盛りです。[F001]"), [])            # 対象の日を言っていない文は今までどおり

    def test_hedge_word_does_not_match_inside_mikoro(self):
        self.assertIn("stale_as_target", codes("今週末は試験の渓谷が見頃です。[F001]"))


class Seireki(unittest.TestCase):
    def test_month_range_reads_both_months(self):
        self.assertEqual(sorted(GB.values("渡良瀬遊水地: 例年 11〜2月")["months"], key=int), ["2", "11"])
        self.assertEqual(sorted(GB.values("例年10〜12月")["months"], key=int), ["10", "12"])

    def test_era_years_are_converted(self):
        self.assertEqual(GB.seireki("令和8年11月19日〜令和9年4月15日"), "2026年11月19日〜2027年4月15日")
        self.assertEqual(GB.seireki("平成27年度の調査"), "2015年度の調査")
        self.assertEqual(GB.seireki("令和元年"), "2019年")

    def test_era_and_western_dates_are_the_same_value(self):
        self.assertEqual(GB.values("令和8年11月19日")["years"], GB.values("2026年11月19日")["years"])
        self.assertEqual(codes("試験の峠道は2026年11月19日11時から冬期閉鎖の予定です。[F002]"), [])

    def test_facts_are_stored_in_western_years(self):
        F = GB._Facts(GB.cfg(), set())
        row = F.add("safety", "試験の峠道: 令和8年11月19日から閉鎖", url="https://example.org/x")
        self.assertIn("2026年11月19日", row["content"])
        self.assertNotIn("令和", row["content"])


class Sources(unittest.TestCase):
    def test_empty_name_shows_the_domain(self):
        r = {"id": "F001", "source": None, "url": "https://www.example.org/page", "source_class": "secondary", "observed": None, "read_at": None}
        self.assertEqual(GV.final_sources([r], GB.cfg()), ["・example.org(公式ではありません) https://www.example.org/page"])

    def test_class_is_decided_by_the_host_only(self):
        for u in ("https://kanagawa-kankou.or.jp/spot/471", "https://www.kanagawa-kankou.or.jp/event/7882"):
            self.assertEqual(GB._source_class(u, "secondary"), GB._source_class(u, "official"))
        self.assertEqual(GB._source_class("https://www.gotokyo.org/jp/spot/1/", "official"), "secondary")
        self.assertEqual(GB._source_class(None, "official"), "official")


class Decisions(unittest.TestCase):
    """段階77 の報告書 §5 への本人の判断(2026-11-10)。"""
    def test_park_operator_page_is_official(self):
        self.assertEqual(GB._source_class("https://www.tptc.co.jp/park/03_08/guide", "secondary"), "official")

    def test_empty_name_uses_the_ledger_publisher_then_the_domain(self):
        c = GB.cfg()
        r = {"id": "F001", "source": None, "url": "https://www.kanagawa-park.or.jp/sakaigawa/guide.html", "source_class": "official",
             "observed": None, "read_at": None}
        got = GV.final_sources([r], c)[0]
        self.assertTrue(got.startswith("・神奈川県公園協会"), got)
        r2 = dict(r, url="https://www.example.org/a")
        self.assertTrue(GV.final_sources([r2], c)[0].startswith("・example.org("))

    def test_event_cards_need_the_event_topic(self):
        c = GB.cfg()
        topics = GB._event_topics(["試験の博物館の観察会「冬の地形地質観察会」: 2026年12月5日"], c)
        self.assertEqual([t["name"] for t in topics], ["地質"])
        geo = {"title": "丹沢の成り立ち", "subject": "丹沢", "category": "地形・地質・火山"}
        bloom = {"title": "檜洞丸のシロヤシオ", "subject": "檜洞丸", "category": "見頃の流れ", "facts": ["岩の多い尾根に咲く"]}
        self.assertTrue(GB._card_topic_hit(geo, topics))
        self.assertFalse(GB._card_topic_hit(bloom, topics))                     # 地名が合っても、行事の対象でなければ入れない
        self.assertEqual(GB._event_topics(["横浜自然観察の森のイベント「秋のクイズラリー」"], c), [])   # 施設名の「森」では植物にしない


class StateLine(unittest.TestCase):
    def test_date_head_does_not_leave_a_particle_or_open_paren(self):
        pol = O.load_policy()
        self.assertEqual(O.short_state("10/21の活動で13種(カルガモ・コガモ・オオバン・カイツブリ・カワウ・コサギ・アオサギ・ダイサギ)。強い風", pol), "活動で13種")
        self.assertEqual(O.short_state("のんびり見頃", pol), "のんびり見頃")          # 日付を除いていないときは外さない
        self.assertEqual(O.short_state("11/9現在、5割程度～見頃です。", pol), "5割程度～見頃です")


class Cards(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import knowledge as K
        self.p = K.path()
        self.old = self.p.read_text(encoding="utf-8") if self.p.exists() else None
        self.p.parent.mkdir(parents=True, exist_ok=True)

        def card(t, place, fact):
            return {"title": t, "category": "種の解説", "place": place, "place_aliases": [], "facts": [fact],
                    "condition": {"months": [], "year_dependent": False},
                    "source": {"name": "試験", "url": "https://www.pref.example.lg.jp/" + t, "checked_on": "2026-11-10"},
                    "confidence": "公的資料", "rights": "確認済み: 試験", "usage": "ガイドの目として1行", "subject": place}
        rows = [card("野鳥との接し方試験", "野鳥", "野鳥には近づきすぎない"), card("地形の一般試験", "地形", "地形は川が削る")]
        self.p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def tearDown(self):
        if self.old is None:
            self.p.unlink(missing_ok=True)
        else:
            self.p.write_text(self.old, encoding="utf-8")

    def test_event_question_has_no_general_cards(self):
        d = GB.build("神奈川で、野鳥や地形の観察会はある?", now=NOW)
        self.assertEqual([k for k in d["cards"] if k["link"] == GB.cfg()["card_links"]["theme"]], [])


class FarBirds(unittest.TestCase):
    def test_migratory_question_gets_distant_candidates(self):
        d = GB.build("渡り鳥が来ているとききました", now=NOW)
        typ = [r for r in d["candidates"] if r.get("rank") is None]
        self.assertTrue(typ)
        self.assertLessEqual(len(typ), GB.cfg()["typical_candidates"]["far_total"])
        self.assertTrue(all(r["group"] != "東京・神奈川" for r in typ))
        self.assertIn("冬鳥", {r.get("theme") for r in typ})                         # 白鳥の飛来地など(ガイドのカタログの冬鳥)


class Switch(unittest.TestCase):
    def test_default_form_is_guide_and_one_line_switches_back(self):
        self.assertEqual(GB.answer_form(), "guide")
        self.assertEqual(GB.answer_form({"answer_form": "classic", "answer_forms": ["classic", "guide"]}), "classic")
        self.assertEqual(GB.answer_form({"answer_form": "x", "answer_forms": ["classic", "guide"]}), "classic")

    def test_hook_after_switch(self):
        c = SH.cfg()

        def turn(*cmds, prompt="今週末の紅葉の情報は?"):
            return {"prompt": prompt, "calls": [{"name": "Bash", "input": {"command": x}, "result": ""} for x in cmds]}
        brief_cmd = 'python -X utf8 -m ikimonobiyori.ask brief "今週末の紅葉の情報は?"'
        verify_cmd = "python -X utf8 -m ikimonobiyori.ask verify d.txt --brief b1"
        ok = SH.decide({"last_assistant_message": "合格した文"}, turn(brief_cmd, verify_cmd), None, c, guide_ok=lambda m: m == "合格した文")
        self.assertFalse(ok["block"])
        ng = SH.decide({"last_assistant_message": "自分で書いた文"}, turn(brief_cmd), None, c, guide_ok=lambda m: False)
        self.assertEqual((ng["block"], ng["why"]), (True, "guide_no_verify"))
        none = SH.decide({"last_assistant_message": "紅葉は見頃です"}, turn(), None, c, guide_ok=lambda m: False)
        self.assertTrue(none["block"])
        self.assertIn("ask brief", " ".join(none["reasons"]))                       # 切り替えたあとは新しい形の手順を案内する

    def test_final_check_accepts_only_the_verified_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IKIMONOBIYORI_DATA_DIR": tmp}
            GV.remember_final("合格した最終の文\n", "q", "b1", NOW, env)
            self.assertTrue(FC.run("合格した最終の文\n", now=NOW, env=env).get("guide"))
            self.assertFalse(FC.run("書き足した文\n", now=NOW, env=env).get("guide"))


if __name__ == "__main__":
    unittest.main()
