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


# ---- 第2部: 季節の花・高山植物・紅葉の樹種の写真(野鳥と同じ仕組みの拡張) ----
import json

from ikimonobiyori import guide, guide_photos
from ikimonobiyori.fetch import inat_photos
from test_stage39 import Net, cand, search, taxon, NOSLEEP, TODAY

POLICY = guide.load_policy()
PH = POLICY["photos"]


class PhotoThemes(unittest.TestCase):
    def run_ensure(self, names, net, theme):
        return guide_photos.ensure(names, theme=theme, policy=POLICY, http_get=net.get, http_bytes=net.get_bytes, today=TODAY, sleep=NOSLEEP)

    def test_themes_for_alpine_flowers_and_autumn_trees_exist(self):
        self.assertIn("紅葉", PH["themes"])
        for th in ("花", "野草", "紅葉"):
            self.assertEqual(PH["themes"][th]["class_name"], "Plantae")
            self.assertIn("variety", PH["themes"][th]["ranks"])               # 高山植物は変種・亜種のことが多い
        self.assertEqual(PH["themes"]["野鳥"].get("ranks"), None)              # 鳥は従来どおり species だけ

    def test_prefetch_lists_have_the_requested_species(self):
        for n in ("チングルマ", "ハクサンコザクラ", "ミヤマキンバイ", "コマクサ", "トウヤクリンドウ", "ニッコウキスゲ", "ハクサンフウロ", "タテヤマリンドウ", "ミヤマリンドウ"):
            self.assertIn(n, PH["prefetch"]["野草"], n)
        for n in ("コスモス", "キバナコスモス", "バラ", "キク", "ダリア", "サザンカ", "ツワブキ", "ロウバイ", "スイセン", "カワヅザクラ"):
            self.assertIn(n, PH["prefetch"]["花"], n)
        for n in ("イロハモミジ", "イチョウ", "ケヤキ"):
            self.assertIn(n, PH["prefetch"]["紅葉"], n)

    def test_variety_is_accepted_for_plants_but_not_for_birds(self):
        c = inat_photos.parse_search(json.loads(search(cand(1, "Primula cuneifolia var. hakusanensis", "ハクサンコザクラ", rank="variety"))))
        pht = {**PH, "class_name": "Plantae", "ranks": PH["themes"]["野草"]["ranks"]}
        row, why = inat_photos.decide("ハクサンコザクラ", c, pht)
        self.assertIsNone(why)
        self.assertEqual(row["taxon_id"], 1)
        row, why = inat_photos.decide("ハクサンコザクラ", c, PH)
        self.assertIsNone(row)

    def test_alpine_flower_is_saved_then_second_run_uses_the_cache_without_requests(self):
        net = Net({"/taxa?": (200, search(cand(7101, "Geum testus", "ミヤマ試験花", rank="variety"))), "/taxa/7101": (200, taxon(7101, "Geum testus"))})
        r1 = self.run_ensure(["ミヤマ試験花"], net, "野草")
        self.assertEqual(r1["results"], {"ミヤマ試験花": "saved"})
        net2 = Net({})
        r2 = self.run_ensure(["ミヤマ試験花"], net2, "野草")
        self.assertEqual((r2["results"], r2["requests"], net2.n), ({"ミヤマ試験花": "cached"}, 0, 0))   # 2 回目は通信 0 件

    def test_autumn_tree_theme_saves_species_and_caches(self):
        net = Net({"/taxa?": (200, search(cand(7102, "Acer testus", "イロハ試験モミジ"))), "/taxa/7102": (200, taxon(7102, "Acer testus"))})
        self.assertEqual(self.run_ensure(["イロハ試験モミジ"], net, "紅葉")["results"], {"イロハ試験モミジ": "saved"})
        net2 = Net({})
        self.assertEqual(self.run_ensure(["イロハ試験モミジ"], net2, "紅葉")["requests"], 0)

    def test_nc_license_photo_is_not_used(self):
        p = {"id": 9, "license_code": "cc-by-nc", "attribution": "(c) x, CC BY-NC", "medium_url": "https://inaturalist-open-data.s3.amazonaws.com/photos/9/medium.jpg"}
        net = Net({"/taxa?": (200, search(cand(7103, "Primula testus", "NC試験花"))),
                   "/taxa/7103": (200, json.dumps({"results": [{"id": 7103, "name": "Primula testus", "default_photo": p}]})),
                   "wikidata.org": (200, json.dumps({"query": {"search": []}}))})
        self.assertEqual(self.run_ensure(["NC試験花"], net, "野草")["results"], {"NC試験花": "none"})      # ライセンスが明確でない写真は使わない


if __name__ == "__main__":
    unittest.main()
