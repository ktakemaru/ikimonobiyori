"""段階51(指示書 docs/stage51-alpine-flower-photos-instructions.md): 通信しない。
第1部: 種ごとの花期(チングルマ・コマクサ・ハクサンコザクラなど)と山ごとの記載。月を足さない・不一致は範囲で併記・今は見られない時期。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify, wildflower_species as WS


class SpeciesBloom(unittest.TestCase):
    def test_chingruma_season_and_class(self):
        r = WS.species_answer("チングルマ", date_="2026-11-06")
        self.assertIn("6月〜8月", r["text"])
        self.assertIn("立山黒部アルペンルート〈公式〉", r["text"])
        self.assertIn("見られる時期ではありません", r["text"])           # 11月は高山は花期外
        self.assertIs(r["in_season"], False)
        self.assertFalse(r["conflict"])
        self.assertIn("本州の山にそのまま当てはめられません", r["text"])   # 北海道の例は参考で、花期に混ぜない
        ref = [i for i in r["items"] if i["reference_only"]]
        self.assertEqual([i["bloom_text"] for i in ref], ["7月〜8月"])

    def test_in_season_month(self):
        r = WS.species_answer("チングルマ", month=7)
        self.assertIs(r["in_season"], True)
        self.assertIn("今年の開花状況は確かめられていません", r["text"])

    def test_komakusa_and_hakusanfuro_show_ranges_with_note(self):
        r = WS.species_answer("コマクサ", month=11)
        self.assertTrue(r["conflict"])
        self.assertIn("7月〜8月", r["text"])
        self.assertIn("5月〜7月", r["text"])
        self.assertIn("紹介サイトで幅がある", r["text"])
        self.assertEqual(r["text"].count("公式ではありません"), 2)
        r = WS.species_answer("ハクサンフウロ", month=11)
        self.assertTrue(r["conflict"])
        self.assertIn("6月〜7月", r["text"])
        self.assertIn("7月〜8月", r["text"])

    def test_no_month_is_not_invented(self):
        for name, timing in (("ハクサンコザクラ", "雪解け直後に咲き始める"), ("トウヤクリンドウ", "晩夏〜初秋")):
            r = WS.species_answer(name, month=7)
            self.assertIn(timing, r["text"])
            self.assertIsNone(r["in_season"])
            self.assertTrue(all(i["bloom"] is None for i in r["items"]))
            self.assertIn("月の記載がない", r["text"])

    def test_unknown_species_raises(self):
        with self.assertRaises(ValueError):
            WS.species_answer("存在しない花")

    def test_text_passes_the_generic_check_without_dev_words(self):
        for n in WS.names():
            r = WS.species_answer(n, month=11)
            res = ask_verify.generic_check(r["text"])
            bad = [e for e in res["errors"] if e["code"] not in ("ask_back_only", "too_few_candidates")]
            self.assertEqual(bad, [], (n, bad))

    def test_every_source_exists_and_has_a_class(self):
        facts, data = WS.load()
        for s in data["species"]:
            for i in s["items"]:
                for k in i["src"]:
                    self.assertIn(facts["sources"][k]["class"], ("official", "secondary"), (s["name"], k))
        for m in data["mountain_notes"]:
            for n in m["notes"]:
                for k in n.get("src") or []:
                    self.assertIn(k, facts["sources"])


class MountainNotes(unittest.TestCase):
    def test_senjo_notes_have_the_lodge_season_and_no_flower_calendar(self):
        r = WS.mountain_notes("m047")
        t = r["text"]
        self.assertIn("仙丈小屋は例年6月中旬〜10月中旬", t)
        self.assertIn("6月下旬〜11月上旬", t)
        self.assertIn("種ごとの開花月は見つかっていない", t)
        from ikimonobiyori import wildflower
        rows = [x for x in wildflower.load()["rows"] if "m047" in (x.get("sites") or [])]
        self.assertEqual(rows, [])                                           # 花暦のエントリは足していない

    def test_yarigatake_has_toyaku_without_months(self):
        t = WS.mountain_notes("m037")["text"]
        self.assertIn("トウヤクリンドウ(晩夏〜初秋)", t)
        with self.assertRaises(ValueError):
            WS.mountain_notes("m999")


if __name__ == "__main__":
    unittest.main()
