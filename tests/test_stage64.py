"""段階64: どの型の質問も ask answer で答える。合成データ・通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import ask_verify as AV

import test_stage56 as T56

POL = AP.load_policy()
cand = T56.cand


def plan_of(cands, origin="大宮", dates=("2026-11-14", "2026-11-15")):
    f = T56.facts_of(cands, dates=dates)
    f["origin"] = origin
    return AP.build(f, "autumn_leaves", POL)


class Part1PickRules(unittest.TestCase):
    """第1部: 段階63 第7部(A+B)と、出発地に合わせた選び直し。"""

    def test_drive_is_one_of_the_pick_aims(self):
        self.assertIn("drive", POL["selection"]["pick_aims"])

    def test_near_section_puts_the_spot_with_a_current_state_first(self):
        cs = [cand("例年だけの庭園", km=30, typical=("11-01", "11-30")),
              cand("例年だけの公園", km=35, typical=("11-01", "11-30")),
              cand("例年だけの森", km=40, typical=("11-01", "11-30")),
              cand("試験の渓谷", km=50, state="色づき始め", sdate="2026-11-05", age=2, typical=("11-10", "12-05"), prefecture="埼玉県")]
        p = plan_of(cs)
        near = next(s for s in p["sections"] if s["aim"] == "near")
        self.assertEqual(near["items"][0]["name"], "試験の渓谷")              # 長瀞の型: 現況のある近場が、例年の窓だけの近場に押し出されない

    def test_estimated_distance_does_not_jump_ahead(self):
        a = cand("見積もりの名所", km=None, state="色づき始め", sdate="2026-11-05", age=2, typical=("11-10", "12-05"))
        b = cand("近い例年の庭園", km=20, typical=("11-01", "11-30"))
        p = plan_of([a, b], origin="横浜")
        near = next((s for s in p["sections"] if s["aim"] == "near"), None)
        if near and len(near["items"]) > 1:
            self.assertEqual(near["items"][0]["name"], "近い例年の庭園")

    def test_near_guarantee_only_uses_a_near_spot_with_a_current_state(self):
        far = lambda n, cl: {"name": n, "distance_km": 120, "has_current": True, "cluster": cl, "outlook": "in_peak", "score": 60, "current_date": "2026-11-05"}
        near_nocur = {"name": "近い例年だけ", "distance_km": 10, "has_current": False, "cluster": "c9", "outlook": "in_peak", "score": 40, "current_date": None}
        chosen = [far("A", "c1"), far("B", "c2"), far("C", "c3")]
        self.assertEqual(AP.ensure_near_pick(chosen, [{"aim": "near", "items": [near_nocur]}], POL), chosen)

    def test_far_spot_without_a_current_state_does_not_fill_the_picks(self):
        cs = [cand("遠い例年だけの庭園", km=83, typical=("10-15", "11-20"), festivals=[T56.lightup_fest()]),
              cand("中くらいの庭園", km=55, state="見頃", sdate="2026-11-06", age=1, typical=("11-01", "11-30"))]
        p = plan_of(cs)
        names = [x["name"] for x in p["picks"]]
        self.assertNotIn("遠い例年だけの庭園", names)
        self.assertIn("中くらいの庭園", names)
        self.assertIn("遠い例年だけの庭園", p.get("fill_skipped") or [])

    def test_few_line_when_far_spots_were_not_used(self):
        from ikimonobiyori import skeleton as SK
        t = POL["skeleton"]
        pl = {"picks": [{"name": "中くらいの庭園", "has_current": True, "outlook": "in_peak"}], "fill_skipped": ["遠い庭園"]}
        out = SK._subject_part({"candidates": []}, pl, "flowers", t, 80, set(), [], None)
        self.assertIn(t["few"].format(n=1), out)

    def test_pre_peak_state_is_not_called_late_from_the_window_only(self):
        c = cand("試験の滝", km=118, state="色づき始め", sdate="2026-11-04", age=4, typical=("11-01", "11-20"), prefecture="茨城県")
        self.assertEqual(AP.outlook_of(c, AP._d("2026-11-14"), POL, "autumn_leaves"), "toward")   # 袋田の滝の型

    def test_full_peak_near_the_window_end_is_still_late(self):
        c = cand("試験の滝", km=118, state="見頃", sdate="2026-11-04", age=4, typical=("11-01", "11-20"), prefecture="茨城県")
        self.assertEqual(AP.outlook_of(c, AP._d("2026-11-14"), POL, "autumn_leaves"), "late")

    def test_near_spot_with_this_year_event_stays_in_the_section(self):
        c = dict(cand("試験の自然観察公園", km=16, typical=None, prefecture="埼玉県"))
        r = {"distance_km": 16, "this_year": True, "aim": "near"}
        self.assertEqual(AP._min_score_of(r, POL), POL["selection"]["near_this_year_min_score"])
        self.assertEqual(AP._min_score_of(dict(r, this_year=False), POL), POL["selection"]["min_score"])
        self.assertEqual(AP._min_score_of(dict(r, distance_km=70, aim="drive"), POL), POL["selection"]["min_score"])
        self.assertTrue(c["name"])


class Part1LegacyVcLine(unittest.TestCase):
    """第1部(段階63 第7部 2): 段階55 の古い 1 行の形は不合格。"""

    FACTS = {"visitor_centers": [{"name": "試験自然観察センター", "url": "https://nature.example.org/news/1", "state": "紅葉が見ごろ", "species": []}]}

    def test_legacy_line_is_rejected(self):
        codes = [e["code"] for e in AV.vc_sentence_errors("試験自然観察センター発信、11/5時点: 紅葉が見ごろ（ジョウビタキ・シメ）\n", self.FACTS)]
        self.assertIn("vc_legacy_line", codes)

    def test_sentence_form_is_not_the_legacy_line(self):
        codes = [e["code"] for e in AV.vc_sentence_errors("試験自然観察センターは、11/5時点で「紅葉が見ごろ」と発信しています。\n", self.FACTS)]
        self.assertNotIn("vc_legacy_line", codes)

    def test_legacy_line_is_in_the_fact_gate(self):
        from ikimonobiyori import answer_gates as AG
        self.assertIn("vc_legacy_line", AG.contract()["gates"]["fact"]["codes"])


class Part2AutoFix(unittest.TestCase):
    """第2部: 決まり違反を検査(自動修正)で止める。本人の会話(2026-11-08)の実際の文を合成データにした。"""

    TEXT = ("藤の名所です。\n"
            "3件とも読んでよければ、そうします。\n"
            "さらに検索して一覧にし直せます。\n"
            "探して、記録することもできます。\n"
            "イキモノビヨリの記録にはスズランの名所がなく、種ごとの花期の一覧にも載っていないため、検索の結果をもとに答えています。\n"
            "「ask answer」は紅葉・花・野鳥の一般的な案内を返しただけで、記録はありませんでした。\n"
            "読みに行きますか。\n"
            "やりますか。\n"
            "秋ヶ瀬公園 定評、出どころの区分: 公式(参照数 3)\n"
            "写真つきのページにもできます。\n")

    def test_offers_questions_and_work_talk_are_deleted(self):
        from ikimonobiyori import answer_gates as AG
        fixed, removed = AG.delete_bad_sentences(self.TEXT, offers=["写真つきのページにもできます。"])
        self.assertEqual(fixed, "藤の名所です。\n写真つきのページにもできます。\n")
        self.assertEqual(len(removed), 8)

    def test_catalog_is_an_internal_word(self):
        self.assertTrue(AV.internal_word_errors("試験の公園はカタログにあります。", AV.load_rules()))

    def test_old_list_labels_are_stripped_from_ask_answers(self):
        from ikimonobiyori import answer_gates as AG
        t = "- 秋ヶ瀬公園(さいたま市) 定評、出どころの区分: 公式・紹介サイト（参照数 3）\n参照数は、その場所を紹介している独立した発行元の数です。\n"
        self.assertEqual(AG.strip_old_list(t), "- 秋ヶ瀬公園(さいたま市)\n")

    def test_event_period_is_not_a_typical_window(self):
        from ikimonobiyori import observations as O
        pol = O.load_policy()
        w = {"kind": "菊", "start": "10-29", "end": "11-19", "note": "ページに『10月29日(木)〜11月19日(木)』とあり年の記載はない(曜日から2026年と推定)"}
        self.assertTrue(O.event_derived(w, [], pol))                          # 川崎大師の型
        self.assertTrue(O.event_derived({"start": "11-01", "end": "11-30", "note": "菊花展は例年11月。人が検索して得た参考値"}, [], pol))   # こども植物園の型
        self.assertFalse(O.event_derived({"start": "06-11", "end": "07-20", "note": "6月中旬から7月中旬に咲きます"}, [], pol))
        self.assertTrue(O.event_derived({"start": "11-01", "end": "11-30", "note": "例年11月"}, [], pol, name="試験八幡宮 菊花展"))   # 名前が展示
        self.assertFalse(O.event_derived({"start": "11-01", "end": "11-30", "note": "例年11月"}, [], pol, name="試験ざる菊園"))

    def test_event_period_written_as_typical_fails_the_fact_gate(self):
        from ikimonobiyori import answer_gates as AG
        facts = {"subjects": {"flowers": {"subject": "flowers", "candidates": [
            {"name": "試験大師 菊花展", "typical": [{"text": "10/29〜11/19", "start": "10-29", "end": "11-19", "event_derived": True}]}]}}}
        mat = AV.Material(facts, AV.load_rules())
        errs = AV.event_as_typical_errors("① 試験大師 菊花展: 例年の見頃: 10/29〜11/19。\n", mat)
        self.assertEqual([e["code"] for e in errs], ["event_as_typical"])
        self.assertEqual(AG.gate_of("event_as_typical"), "fact")
        self.assertEqual(AV.event_as_typical_errors("① 試験大師 菊花展: 例年の時期は分かりません。\n", mat), [])


if __name__ == "__main__":
    unittest.main()
