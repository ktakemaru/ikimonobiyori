"""段階61: 外部の公的・研究機関の知識・データの取り込み。通信なし・合成データ。
第1部: 気象庁 生物季節観測の平年の目安(ikimonobiyori/jma_normals.py)。"""
import copy
import tempfile
import unittest
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as V
from ikimonobiyori import intent
from ikimonobiyori import jma_normals as JN
from ikimonobiyori.fetch import ParseError

POL = JN.policy()
LAYOUT = POL["layout"]
PHEN = {p["key"]: p for p in POL["phenomena"]}


def synthetic(code, name, rows, years, last_rm="e"):
    """合成の累年値 CSV(cp932 のバイト列)。rows = [(番号, 地点名, {年: (値, rm)}), ...]。"""
    hdr = ["番号", "地点名"]
    for i, y in enumerate(years):
        hdr += [str(y), last_rm if i == len(years) - 1 else "rm"]
    hdr += LAYOUT["summary_columns"]
    lines = [",".join([str(int(code)), name] + [""] * (len(hdr) - 2)), ",".join(hdr)]
    for no, nm, vals in rows:
        flat = []
        for y in years:
            flat += list(vals.get(y, ("0", "0")))
        lines.append(",".join([no, nm] + flat + ["0"] * len(LAYOUT["summary_columns"])))
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def small_policy(**over):
    """点数の下限を小さくした方針(合成データの年数で計算できるように)。"""
    p = copy.deepcopy(POL)
    p.update(over)
    return p


YEARS = list(range(1989, 2024))


class Compute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, code, data):
        (self.dir / f"{code}.csv").write_bytes(data)

    def test_mean_earliest_latest_within_period_only(self):
        # 東京: 1991〜2020 年に 11/20・11/30・12/10 の 3 年(平均 11/30)。期間の外(1990・2021)は使わない
        self.write("015", synthetic("015", "かえでの紅葉", [("662", "東京　　", {1990: ("1101", "8"), 1991: ("1120", "8"), 2000: ("1130", "8"),
                                                                                  2020: ("1210", "8"), 2021: ("1231", "8")})], YEARS))
        doc = JN.build(self.dir, "2026-11-07", small_policy(min_points=3))
        e = next(x for x in doc["entries"] if x["phenomenon"] == "kaede_koyo")
        self.assertEqual((e["mean"], e["mean_phrase"], e["earliest"], e["latest"], e["points"]), ("11-30", "11月下旬", "11-20", "12-10", 3))
        self.assertEqual(e["period"], {"from": 1991, "to": 2020})
        self.assertEqual(e["observed_years"], {"first": 1990, "last": 2021})

    def test_cross_year_values_average_across_new_year(self):
        # 秋の種目の 1 月の値は翌年の日付: 12/26 と 1/5 の平均は 12/31(5 月や 6 月にならない)
        self.write("016", synthetic("016", "かえでの落葉", [("662", "東京　　", {1995: ("1226", "8"), 1996: ("105", "8")})], YEARS))
        doc = JN.build(self.dir, "2026-11-07", small_policy(min_points=2))
        e = next(x for x in doc["entries"] if x["phenomenon"] == "kaede_rakuyo")
        self.assertEqual((e["mean"], e["earliest"], e["latest"]), ("12-31", "12-26", "01-05"))

    def test_remark_3_4_and_too_few_points_are_not_used(self):
        self.write("004", synthetic("004", "さくらの開花", [("662", "東京　　", {1991: ("325", "3"), 1992: ("320", "8")})], YEARS))
        doc = JN.build(self.dir, "2026-11-07", small_policy(min_points=2))
        self.assertFalse([x for x in doc["entries"] if x["phenomenon"] == "sakura_kaika"])      # 統計に使わない rm 3 を除くと 1 年だけ
        doc = JN.build(self.dir, "2026-11-07", small_policy(min_points=1))
        e = next(x for x in doc["entries"] if x["phenomenon"] == "sakura_kaika")
        self.assertEqual((e["mean"], e["points"]), ("03-20", 1))

    def test_unexpected_shape_stops(self):
        self.write("015", synthetic("015", "ちがう種目", [("662", "東京", {1991: ("1120", "8")})], YEARS))
        with self.assertRaises(ParseError):
            JN.build(self.dir, "2026-11-07")

    def test_source_and_processing_are_stated(self):
        doc = JN.build(self.dir, "2026-11-07")
        self.assertEqual(doc["source"]["url"], POL["source"]["page"])
        self.assertEqual(doc["source"]["retrieved_on"], "2026-11-07")
        self.assertIn("イキモノビヨリが平均等を計算", doc["processing"])
        self.assertIn("気象庁が作成した値(平年値)ではない", doc["processing"])
        self.assertEqual(len(doc["missing"]), len(POL["phenomena"]))         # ファイルがなければ推測で補わない
        out = self.dir / "n.yaml"
        JN.dump(doc, out)
        head = out.read_text(encoding="utf-8").splitlines()[:3]
        self.assertTrue(any("出典" in h and POL["source"]["page"] in h for h in head))
        self.assertTrue(any("加工" in h and "イキモノビヨリが平均等を計算" in h for h in head))

    def test_repository_table_has_source_and_processing(self):
        text = JN.NORMALS_PATH.read_text(encoding="utf-8")
        self.assertIn("出典: 気象庁「生物季節観測累年値」", text)
        self.assertIn("イキモノビヨリが平均等を計算", text)
        doc = JN.load()
        self.assertTrue(doc["entries"])
        self.assertTrue(all(e["period"]["from"] >= POL["period"]["from"] and e["period"]["to"] <= POL["period"]["to"] for e in doc["entries"]))


def entry(**kw):
    e = {"station": "東京", "station_no": "662", "phenomenon": "kaede_koyo", "name": "かえでの紅葉", "label": "かえでの紅葉", "kind": "plant",
         "observing": True, "mean": "11-28", "mean_phrase": "11月下旬", "earliest": "11-15", "latest": "12-04",
         "period": {"from": 1991, "to": 2020}, "points": 30, "observed_years": {"first": 1953, "last": 2025}}
    e.update(kw)
    return e


DOC = {"entries": [entry(), entry(station="横浜", station_no="670", mean_phrase="12月中旬"),
                   entry(phenomenon="uguisu", name="うぐいすの初鳴", label="うぐいすの初鳴き", kind="animal", observing=False, station="横浜",
                         mean_phrase="3月中旬", earliest="03-02", latest="04-11", points=28, observed_years={"first": 1953, "last": 2020})]}


class Lines(unittest.TestCase):
    def test_observing_line_states_period_points_city_tree_and_mountain_note(self):
        ls, src = JN.lines_for("東京の紅葉は、平年はいつ頃?", DOC)
        self.assertEqual(len(ls), 1)
        self.assertIn("東京(気象庁の標本木。都市部の観測)のかえでの紅葉は、平年は11月下旬ごろです", ls[0])
        self.assertIn("1991〜2020年の平均、30年分", ls[0])
        self.assertIn("山地の見頃とは別です", ls[0])
        self.assertEqual(src, POL["text"]["source_line"])
        self.assertIn("イキモノビヨリが計算", src)

    def test_ended_phenomenon_states_observation_period_and_no_this_year(self):
        ls, _ = JN.lines_for("ウグイスは、いつ頃から鳴きはじめる?", DOC)
        self.assertEqual(len(ls), 1)
        self.assertIn("気象庁の過去の観測(1953〜2020年)", ls[0])
        self.assertNotIn("今年の", ls[0])
        self.assertEqual(JN.answer_errors("\n".join(ls) + "\n" + POL["text"]["source_line"]), [])

    def test_this_year_on_ended_phenomenon_is_rejected(self):
        bad = "横浜のうぐいすの初鳴きは、気象庁の過去の観測(1953〜2020年)では、今年の初鳴きは3月中旬ごろでした。\n" + POL["text"]["source_line"]
        self.assertIn("ended_phenology_this_year", [e["code"] for e in JN.answer_errors(bad)])
        self.assertIn("ended_phenology_this_year", [e["code"] for e in V.generic_check(bad)["errors"]])

    def test_source_line_is_required(self):
        ls, _ = JN.lines_for("東京の紅葉は、平年はいつ頃?", DOC)
        self.assertIn("jma_normal_source_missing", [e["code"] for e in JN.answer_errors(ls[0])])

    def test_no_match_without_question_words_or_with_other_kinds(self):
        self.assertEqual(JN.match("冬桜について教えて"), [])
        self.assertEqual(JN.match("十月桜はいつ頃?"), [])              # 冬に咲く桜は、さくら(そめいよしの)の観測に当てない
        self.assertEqual(JN.match("紅葉のおすすめは"), [])            # 平年・いつ頃などの語がない
        self.assertIn("sakura_kaika", JN.match("横浜の桜は平年いつ頃咲く?"))
        self.assertEqual(JN.stations_in("ウグイスはいつ頃?"), POL["default_stations"])

    def test_skeleton_lines_use_origin_station(self):
        ls, src = JN.skeleton_lines(["autumn_leaves"], "東京", DOC)
        self.assertTrue(ls and ls[0].startswith("東京("))
        ls, _ = JN.skeleton_lines(["autumn_leaves"], "大宮", DOC)        # 地点にない出発地は既定の地点
        self.assertTrue(ls[0].startswith(POL["skeleton_station"] + "("))
        self.assertEqual(JN.skeleton_lines(["birds"], "東京", DOC), ([], None))

    def test_knowledge_answer_puts_normals_first_with_source(self):
        orig = JN.load
        JN.load = lambda path=None: DOC
        try:
            self.assertEqual(intent.classify("東京の紅葉は、平年はいつ頃?"), "normal")
            text = intent.compose("東京の紅葉は、平年はいつ頃?", cards=[])
            self.assertTrue(text.startswith("東京(気象庁の標本木。都市部の観測)"))
            self.assertIn("出典\n" + POL["text"]["source_line"], text)
            self.assertEqual(intent.check(text, []), [])
            self.assertFalse(text.rstrip().endswith("?"))
        finally:
            JN.load = orig



# ---- 第2部: 博物館などの行事・展示の台帳(ikimonobiyori/facility_events.py) ----
from datetime import date  # noqa: E402

from ikimonobiyori import facility_events as FE  # noqa: E402


def event_doc(status="pending", **ev):
    e = {"facility": "test-museum", "kind": "講座", "title": "試験の野鳥講座", "topics": ["野鳥"], "date": "2026-12-05", "weekday_text": "土曜",
         "time": "9時30分から16時", "deadline": "2026-11-24", "deadline_weekday_text": "火曜", "capacity": 15, "place": "試験の博物館",
         "url": "https://museum.example.org/event/1.html"}
    e.update(ev)
    return {"facilities": [{"id": "test-museum", "name": "試験の博物館", "prefecture": "神奈川県", "approval": {"status": status}}],
            "events": [e, {"facility": "test-museum", "kind": "展示", "label": "特別展", "title": "試験の展示", "topics": ["自然"],
                           "start": "2026-07-18", "end": "2026-11-08", "url": "https://museum.example.org/ex.html"}]}


class Events(unittest.TestCase):
    TODAY = date(2026, 11, 8)

    def test_repository_ledger_is_valid_and_pending(self):
        doc = FE.load()
        self.assertEqual(FE.validate(doc), [])
        self.assertIn("神奈川県立生命の星・地球博物館", FE.pending_facilities(doc))
        self.assertEqual(FE.lines_for("神奈川で、野鳥や地形の観察会はある?", self.TODAY, doc), ([], []))     # 承認待ちは出さない

    def test_approved_event_line_has_year_weekday_deadline_and_capacity(self):
        ls, urls = FE.lines_for("神奈川で、野鳥の観察会はある?", self.TODAY, event_doc("approved"))
        self.assertEqual(len(ls), 1)
        self.assertIn("2026年12月5日(土)", ls[0])
        self.assertIn("申し込みの締め切りは2026年11月24日(火)", ls[0])
        self.assertIn("定員15人", ls[0])
        self.assertEqual(urls, ["https://museum.example.org/event/1.html"])

    def test_weekday_mismatch_and_missing_year_are_rejected(self):
        self.assertTrue(FE.validate(event_doc(weekday_text="日曜")))
        self.assertTrue(FE.validate(event_doc(date="12-05")))
        self.assertEqual(FE.lines_for("野鳥の観察会はある?", self.TODAY, event_doc("approved", weekday_text="日曜")), ([], []))

    def test_past_events_and_other_topics_are_not_shown(self):
        self.assertEqual(FE.lines_for("野鳥の観察会はある?", date(2026, 12, 6), event_doc("approved"))[0], [])
        ls, _ = FE.lines_for("自然の展示はある?", self.TODAY, event_doc("approved"))
        self.assertEqual(ls, ["試験の博物館の特別展「試験の展示」: 2026年7月18日〜2026年11月8日。"])         # 会期を年つきで(現況ではない)
        self.assertEqual(FE.lines_for("自然の展示はある?", date(2026, 11, 9), event_doc("approved"))[0], [])
        self.assertEqual(FE.match("紅葉のおすすめは?"), [])

    def test_event_question_answer_uses_only_approved_events(self):
        q = "神奈川で、野鳥の観察会はある?"
        self.assertEqual(intent.classify(q), "event")
        self.assertIsNone(intent.compose(q, cards=[], today=self.TODAY, events=event_doc("pending")))
        text = intent.compose(q, cards=[], today=self.TODAY, events=event_doc("approved"))
        self.assertTrue(text.startswith("試験の博物館の講座"))
        self.assertIn("出典\nhttps://museum.example.org/event/1.html", text)
        self.assertEqual(V.question_errors(text, V.load_rules()), [])


# ---- 第3部: 外来種のカード(知識の答え・ガイドの目) ----
def ias_card(title="試験ガメ(外来種)", place="試験ガメ", aliases=("水辺", "外来種"), year=None):
    return {"title": title, "category": "保全・マナー", "place": place, "place_aliases": list(aliases),
            "facts": ["リスト第2版で防除推進外来種", "飼っている場合は野外に放さない"],
            "condition": {"months": [], "year_dependent": bool(year), **({"year": year} if year else {})},
            "source": {"name": "環境省", "title": "試験のリスト", "url": "https://env.example.go.jp/list.xlsx", "checked_on": "2026-11-08"},
            "confidence": "公的資料", "rights": "確認済み: 公共データ利用規約", "usage": "ガイドの目"}


class InvasiveCards(unittest.TestCase):
    def test_named_species_card_is_main_text_not_only_a_guide_line(self):
        text = intent.compose("試験ガメを見かけたら、どうすればいい?", cards=[ias_card()])
        self.assertTrue(text.startswith("試験ガメ(外来種): リスト第2版で防除推進外来種"))
        self.assertEqual(intent.check(text, [ias_card()]), [])

    def test_unnamed_conservation_card_stays_a_guide_line(self):
        cards = [ias_card(), {**ias_card(title="水辺の歩き方", place="水辺", aliases=()), "category": "出会い方・歩き方"}]
        text = intent.compose("水辺について教えて", cards=cards)
        self.assertIn("ガイドの目: ", text)
        self.assertFalse(text.startswith("ガイドの目"))

    def test_year_prefix_of_a_year_dependent_card_counts_as_card_fact(self):
        card = ias_card(title="試験のリストのカテゴリ", place="試験リスト", aliases=("外来種",), year=2026)
        text = intent.compose("外来種について教えて", cards=[ias_card(), card])
        self.assertEqual([e for e in intent.check(text, [ias_card(), card]) if e["code"] == "knowledge_fact_not_in_card"], [])


# ---- 第4部: 調査の数の目安(年つき)と、この冬の記録ではないことの 1 文 ----
def count_card(year=2026):
    return {"title": "試験ドリの飛来数の目安", "category": "シーズンの目安", "place": "試験ドリ", "place_aliases": [],
            "facts": [f"{year}年1月の全国調査で、試験県は1,234羽"], "condition": {"months": [], "year_dependent": True, "year": year},
            "source": {"name": "環境省生物多様性センター", "title": "試験の調査", "url": "https://biodic.example.go.jp/r7.xlsx", "checked_on": "2026-11-08"},
            "confidence": "公的資料", "rights": "確認済み: 公共データ利用規約", "usage": "知識"}


def explain_card():
    return {**count_card(), "title": "試験ドリの調査とは", "category": "季節の仕組み", "facts": ["毎年1月に数える調査"],
            "condition": {"months": [], "year_dependent": False}, "source": {**count_card()["source"], "url": "https://biodic.example.go.jp/top.html"}}


class SurveyCounts(unittest.TestCase):
    def test_count_question_puts_the_count_first_and_says_it_is_not_this_winter(self):
        cards = [count_card(), explain_card()]
        text = intent.compose("試験ドリは、どのくらい来ている?", cards=cards)
        self.assertTrue(text.startswith("試験ドリの飛来数の目安"))
        self.assertIn("2026年の調査の数で、この冬の飛来の記録は確認できていません。", text)
        self.assertEqual(intent.check(text, cards), [])
        self.assertFalse(text.rstrip().endswith("?"))

    def test_no_note_without_now_words_or_without_dated_count_cards(self):
        self.assertNotIn("この冬の飛来の記録", intent.compose("試験ドリについて教えて", cards=[count_card(), explain_card()]))
        self.assertNotIn("この冬の飛来の記録", intent.compose("試験ドリは来ている?", cards=[explain_card()]))


if __name__ == "__main__":
    unittest.main()
