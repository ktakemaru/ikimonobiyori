"""段階60(指示書 docs/stage60-followup-instructions.md)。通信しない。合成データだけ。"""
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O

P = O.load_policy()
CFG = O.merge_cfg(P)
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=JST)
D = [date(2026, 11, 7), date(2026, 11, 8)]


def spot(i, name, city="試験町", point=None, **kw):
    s = {"id": i, "subject": "autumn_leaves", "name": name, "prefecture": "神奈川県", "city": city, "area": "試験",
         "typical": [{"text": "11月上旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/1", "year": 2026, "source_class": "secondary"}],
         "pages": []}
    if point:
        s["point"] = {"lat": point[0], "lon": point[1]}
    s.update(kw)
    return s


def rec(name, state="色づきはじめ", d="2026-11-06", city="試験町"):
    return {"subject": "autumn_leaves", "name": name, "city": city, "prefecture": "神奈川県", "state": state, "state_date": d,
            "url": "https://kankou.example.org/koyo", "publisher": "試験の観光協会", "source_class": "official"}


class Part1NameMerge(unittest.TestCase):
    """第1部: 同じ名所の別名(表記ゆれ)を 1 つにまとめる。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def facts(self, spots, rows):
        O.record(rows, env=self.env, now=NOW)
        return O.facts("autumn_leaves", region="神奈川", dates=D, now=NOW, env=self.env, spots_doc={"spots": spots},
                       catalogs={"autumn_leaves": {"entries": []}})

    def names(self, f):
        return [c["name"] for c in f["candidates"]]

    def test_official_label_without_area_prefix_joins_the_listed_spot(self):
        f = self.facts([spot("t-1", "試験 山寺(長安寺)")], [rec("山寺(長安寺)"), rec("試験 山寺(長安寺)", d="2026-11-05")])
        self.assertEqual(self.names(f).count("試験 山寺(長安寺)"), 1)
        self.assertNotIn("山寺(長安寺)", self.names(f))                       # 2 回目の候補にならない
        self.assertEqual(len(f["candidates"]), 1)

    def test_variants_outside_the_list_become_one_candidate(self):
        f = self.facts([spot("t-1", "試験の湖")], [rec("宮ノ沢"), rec("試験 宮ノ沢", d="2026-11-05"), rec("試験の湖")])
        extra = [c for c in f["candidates"] if c.get("outside_list")]
        self.assertEqual(len(extra), 1)
        self.assertIn("試験 宮ノ沢", extra[0]["aliases"])                       # 別名として残す(消さない)

    def test_list_of_spots_is_not_merged_into_one_part(self):
        self.assertFalse(O.name_contained("華厳の滝", "中禅の湖・華厳の滝", CFG))
        self.assertTrue(O.name_contained("山寺(長安寺)", "試験 山寺(長安寺)", CFG))

    def test_short_names_and_ambiguous_hits_are_not_merged(self):
        self.assertFalse(O.name_contained("湯本", "試験 湯本", CFG))            # 下限の字数より短い
        cands = [O._from_spot(spot("a", "北 試験の滝"), P, {}), O._from_spot(spot("b", "南 試験の滝"), P, {})]
        self.assertIsNone(O.match_record(rec("試験の滝"), cands, P, {}))         # 2 つに当たるときは結びつけない

    def test_city_must_not_conflict(self):
        cands = [O._from_spot(spot("a", "試験 山寺(長安寺)", city="別の町"), P, {})]
        self.assertIsNone(O.match_record(rec("山寺(長安寺)", city="試験町"), cands, P, {}))

    def test_alias_dictionary_maps_official_label(self):
        cands = [O._from_spot(spot("a", "試験の美術館"), P, {})]
        self.assertIs(O.match_record(rec("試験(美術館の丘)"), cands, P, {O._key("試験(美術館の丘)"): O._key("試験の美術館")}), cands[0])
        self.assertIn("湖尻", O.place_alias_table())                             # 箱根町観光協会の地点の書き方(台帳の covers)

    def test_candidates_near_with_similar_names_are_merged_as_alias(self):
        spots = [spot("a", "試験 紅葉の谷", point=(35.0, 139.0)), spot("b", "紅葉の谷", point=(35.001, 139.001)),
                 spot("c", "紅葉の谷", city="遠い町", point=(35.5, 139.5))]
        cands = O.all_candidates("autumn_leaves", P, {"spots": spots}, {"autumn_leaves": {"entries": []}})
        ids = [c["id"] for c in cands]
        self.assertEqual(ids.count("b"), 0)                                       # 約140m・同じ町 → 別名
        self.assertIn("c", ids)                                                   # 遠い・別の町は別の名所
        a = next(c for c in cands if c["id"] == "a")
        self.assertIn("紅葉の谷", a["aliases"])
        self.assertEqual(a["merged"], ["b"])

    def test_same_point_with_different_names_is_not_merged(self):
        spots = [spot("a", "試験の湖", point=(35.0, 139.0)), spot("b", "試験の峠", point=(35.0, 139.0))]
        cands = O.all_candidates("autumn_leaves", P, {"spots": spots}, {"autumn_leaves": {"entries": []}})
        self.assertEqual({c["id"] for c in cands}, {"a", "b"})

    def test_merge_rule_values_are_in_the_policy(self):
        self.assertEqual(CFG["max_km"], 0.3)
        self.assertGreaterEqual(CFG["min"], 3)


SKELETON = """見頃に向かう可能性がある場所を選びました。
対象の日は11/7(土)・11/8(日)です。
今回のおすすめ
① 試験の湖 約42km: 今の状況は色づきはじめ(11/6時点、試験の観光協会)。例年の見頃: 11月中旬。見頃に向かう可能性があります。
② 試験の峠 約58km: 紹介サイトでは見頃とされています(11/5時点、試験サイト。公式ではありません)。見頃が続いている可能性があります。

出典
https://kankou.example.org/koyo
https://kouyou.example.com/list
"""

POLISHED = """見頃に向かう可能性がある場所を選びました。
対象の日は11/7(土)・11/8(日)です。
今回のおすすめ
① まずは試験の湖(約42km)。今の状況は色づきはじめで(11/6時点、試験の観光協会)、例年の見頃は11月中旬です。見頃に向かう可能性があります。
② 足を延ばすなら試験の峠(約58km)。紹介サイトでは見頃とされています(11/5時点、試験サイト。公式ではありません)。見頃が続いている可能性があります。

出典
https://kankou.example.org/koyo
https://kouyou.example.com/list
"""

NAMES = ["試験の湖", "試験の峠", "試験の滝", "カエデ", "イチョウ", "試験の観光協会"]


class Part2FactConsistency(unittest.TestCase):
    """第2部: 整えた文章と骨組みの事実の一致検査。"""

    def codes(self, text):
        from ikimonobiyori import polish as PL
        return [(e["code"], e["kind"]) for e in PL.check(SKELETON, text, NAMES)["errors"]]

    def test_polished_text_with_the_same_facts_passes(self):
        self.assertEqual(self.codes(POLISHED), [])

    def test_added_facts_fail(self):
        for extra, kind in (("12/1にまつりがあります。", "date"), ("駐車場は200台です。", "number"),
                            ("イチョウも見られます。", "name"), ("詳しくは https://other.example.net/ を。", "url"),
                            ("約3kmの散策路があります。", "km"), ("9:00に開きます。", "time"), ("12月上旬まで続きます。", "month")):
            text = POLISHED.replace("出典\n", extra + "\n出典\n")
            self.assertIn(("polish_added_fact", kind), self.codes(text), extra)

    def test_added_facility_name_fails(self):
        self.assertIn(("polish_added_fact", "name"), self.codes(POLISHED.replace("足を延ばすなら", "試験の滝の帰りに")))

    def test_dropped_important_facts_fail(self):
        cases = {"current_date": POLISHED.replace("(11/6時点、試験の観光協会)", "(試験の観光協会)"),
                 "phrase": POLISHED.replace("見頃が続いている可能性があります。", "見頃です。"),
                 "certainty": POLISHED.replace("。公式ではありません", ""),
                 "source": POLISHED.replace("https://kouyou.example.com/list\n", "")}
        for kind, text in cases.items():
            self.assertIn(("polish_dropped_fact", kind), self.codes(text), kind)

    def test_rewrite_limit_is_one(self):
        from ikimonobiyori import polish as PL
        use, st = PL.decide(None, SKELETON, False, True)
        self.assertEqual((use, st["attempts"]), ("retry", 1))
        use, st = PL.decide(st, SKELETON, False, True)
        self.assertEqual(use, "skeleton")                                         # 2 回目も通らなければ骨組みのまま
        use, st = PL.decide(st, SKELETON + "x", True, True)
        self.assertEqual((use, st["attempts"]), ("polished", 1))                 # 骨組みが変われば数え直す
        use, _ = PL.decide({"skeleton": SKELETON, "attempts": 1}, SKELETON, True, False)
        self.assertEqual(use, "skeleton")                                         # 通常の検査に落ちても同じ
        self.assertEqual(PL.cfg()["max_rewrites"], 1)

    def test_flow_falls_back_to_the_skeleton_after_one_rewrite(self):
        from ikimonobiyori import ask
        with tempfile.TemporaryDirectory() as d:
            f = ask.Flow(d, now=NOW, env={"IKIMONOBIYORI_DATA_DIR": d})
            bad = POLISHED.replace("(11/6時点、試験の観光協会)", "(試験の観光協会)")
            use, final, fr, _ = f.polish_check(bad, SKELETON, generic=True)
            self.assertEqual((use, final), ("retry", None))
            self.assertFalse(fr["ok"])
            use, final, _, _ = f.polish_check(bad, SKELETON, generic=True)
            self.assertEqual(use, "skeleton")
            self.assertEqual(final, SKELETON)                                     # 通らない文を除いた版ではなく、骨組みのまま
            self.assertEqual(Path(d, "final.txt").read_text(encoding="utf-8"), SKELETON)


if __name__ == "__main__":
    unittest.main()
