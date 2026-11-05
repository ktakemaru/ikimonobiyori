"""段階51(指示書 docs/stage51-alpine-flower-photos-instructions.md): 通信しない。
第1部: 種ごとの花期(チングルマ・コマクサ・ハクサンコザクラなど)と山ごとの記載。月を足さない・不一致は範囲で併記・今は見られない時期。"""
import unittest
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify, wildflower_species as WS


ROOT = Path(__file__).resolve().parent.parent


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


# ---- 第3部: 試用(2026-11-06「今週末、紅葉や花、野鳥を楽しめるところを教えて」)で見つかった答えの崩れ 5 点 ----
import copy

from ikimonobiyori import ask_verify as V
from test_stage37 import Base, BFACTS, GOOD_BIRDS, RULES as R37, codes as codes37

STRICT = copy.deepcopy(BFACTS)
STRICT["lines"] = {"fetch": ["11/1 に 試験の遊水地 の 1ページを読み直し、新しい記録が 1件増えました。"], "answer_rules": "stage51", "open_urls": None}
for _c in STRICT["subjects"]["birds"]["candidates"]:
    _c["inat"] = {"site_url": "https://www.inaturalist.org/", "url": "https://api.inaturalist.org/v1/observations/species_counts?x=1"}

GOOD51 = """明日(11/2)は、試験の遊水地・試験の森・試験の公園で、冬鳥のカモ類が見られそうです。
今回のおすすめ
① 試験の遊水地: この時期に見られる鳥は、コガモ・オナガガモが多く記録されています(iNaturalist、神奈川県で一年の平均より多い傾向。公式ではありません)。10/21時点で「冬鳥のコガモが増えて来ました」(試験の遊水地)。
② 試験の森: この時期に見られる鳥は、コガモ・オナガガモです(iNaturalist、神奈川県の傾向。公式ではありません)。
③ 試験の公園: この時期に見られる鳥は、コガモ・オナガガモです。明日(11/2・月)は試験の里が休みです(公園には入れます)。
出典: https://birds.example.org/ https://www.inaturalist.org/
"""


def c51(text, facts=STRICT):
    return codes37(V.check(text, facts, R37))


class TrialDefects(unittest.TestCase):
    def test_the_good_answer_passes_under_the_new_rules(self):
        r = V.check(GOOD51, STRICT, R37)
        self.assertTrue(r["ok"], V.report_lines(r))

    # 1. 作業の報告を答えに出さない
    def test_1_work_report_is_rejected(self):
        for line in ("11/1 に 試験の遊水地 の 1ページを読み直し、新しい記録が 1件増えました。",
                     "日光市観光協会・昭和記念公園ほかも読みに行きましたが、新しい情報は取れませんでした。",
                     "記録が新しいため、今回は読み直していません。"):
            self.assertIn("work_report", c51(GOOD51 + line + "\n"), line)
        self.assertIn("process_phrase", [e["code"] for e in V.generic_check("読みに行きましたが、新しい情報は取れませんでした。\n")["errors"]])

    def test_1b_open_urls_line_is_allowed_and_old_style_facts_keep_the_old_behaviour(self):
        ok = GOOD51 + "読めなかったページ(ご自身で開いてください): https://www.hakone.or.jp/\n"
        self.assertNotIn("work_report", c51(ok))
        self.assertTrue(V.check(GOOD_BIRDS, BFACTS, R37)["ok"])                  # 印のない古い形の facts は従来どおり（既存のテストの期待値は変えない）

    def test_1c_facts_carry_the_mark_and_only_the_failed_pages_line(self):
        from ikimonobiyori import ask
        rnd = {"failed": [{"url": "https://b.example/", "reason": "x"}], "new_records": 1}
        self.assertEqual(ask.open_urls_line(rnd), "読めなかったページ(ご自身で開いてください): https://b.example/")
        self.assertIsNone(ask.open_urls_line({"failed": []}))

    # 2. 冒頭とおすすめの食い違い
    def test_2_lead_must_match_the_three_picks(self):
        bad = GOOD51.replace("で、冬鳥のカモ類が見られそうです。", "の冬鳥と、少し足を延ばして庭園の紅葉が楽しめます。", 1)
        self.assertIn("lead_mismatch", c51(bad))
        ok = GOOD51.replace("で、冬鳥のカモ類が見られそうです。", "の冬鳥が楽しめます。", 1)
        self.assertNotIn("lead_mismatch", c51(ok))
        named = GOOD51.replace("明日(11/2)は、", "明日(11/2)は、試験の山も良い日です。", 1)
        self.assertNotIn("lead_mismatch", c51(named))                           # 候補の名前でない語は対象外

    # 3. iNaturalist の傾向
    def test_3_inat_needs_the_label_and_the_scope(self):
        no_label = GOOD51.replace("神奈川県で一年の平均より多い傾向。公式ではありません", "神奈川県で一年の平均より多い傾向")
        self.assertIn("inat_unlabeled", c51(no_label))
        no_scope = GOOD51.replace("神奈川県で一年の平均より多い傾向。公式ではありません", "一年の平均より多い傾向。公式ではありません")
        self.assertIn("inat_scope_missing", c51(no_scope))

    # 4. 出典リスト
    def test_4_sources_used_in_the_body_are_in_the_list(self):
        self.assertIn("source_missing", c51(GOOD51.replace("https://birds.example.org/ ", "")))
        self.assertIn("source_missing", c51(GOOD51.replace(" https://www.inaturalist.org/", "")))

    # 5. 見込みと転載
    def test_5_forecast_is_hedged_and_official_text_is_not_copied_whole(self):
        self.assertIn("assertive_forecast", c51(GOOD51 + "週末は見ごろに入る時期です。\n"))
        self.assertNotIn("assertive_forecast", c51(GOOD51 + "週末は見ごろに入っている可能性があります。\n"))
        self.assertIn("long_quote", c51(GOOD51 + "11/3時点で「△ 色づきはじめました。護摩堂横見ごろ始まりました」です。\n"))
        self.assertNotIn("long_quote", c51(GOOD51 + "11/3時点で「◎ 真っ盛り」です。\n"))

    def test_skill_files_do_not_tell_to_copy_the_work_report(self):
        for f in (".claude/skills/ikimono-weekend/SKILL.md", "AGENTS.md", "CLAUDE.md"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertNotIn("そのまま写す**取りに行った結果の 1〜3 行", t)
            self.assertIn("lines.open_urls", t)
            self.assertIn("答えに書かない", t)


class FactsMark(Base):
    def test_facts_have_the_mark_and_keep_the_old_fetch_lines(self):
        f, doc = self.run_flow()
        self.assertEqual(doc["lines"]["answer_rules"], "stage51")
        self.assertIn("open_urls", doc["lines"])
        self.assertIn("fetch", doc["lines"])                                    # 作業の記録としては残す（既存の期待値は変えない）


if __name__ == "__main__":
    unittest.main()
