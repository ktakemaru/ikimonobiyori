"""段階52: ウェザーニュース由来(転載を含む)の予想を答えの材料にしない。通信しない。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ikimonobiyori import observations as O  # noqa: E402


class WeathernewsExcluded(unittest.TestCase):
    def setUp(self):
        self.pol = O.load_policy()

    def test_reprint_is_rejected_at_record(self):
        rec = {"subject": "autumn_leaves", "name": "御岳昇仙峡", "city": "甲府市", "state": "見頃予想:11月8日(日)頃から", "state_date": "2026-10-29",
               "url": "https://koyo.walkerplus.com/topics/article/161896/", "publisher": "ウォーカープラス(ウェザーニューズ予想)", "source_class": "secondary"}
        self.assertTrue(O.validate(rec, self.pol))
        self.assertTrue(O._reprint_of_blocked(rec, self.pol))

    def test_hosts_are_not_read(self):
        for h in ("weathernews.jp", "n-kishou.com"):
            self.assertTrue(O._blocked_host(h, self.pol), h)
        self.assertFalse(O._blocked_host("koyo.walkerplus.com", self.pol))

    def test_other_walkerplus_content_is_kept(self):
        rec = {"subject": "autumn_leaves", "name": "三溪園", "city": "横浜市", "state": "紅葉の状態の記載なし", "typical": "11月中旬～12月中旬",
               "url": "https://koyo.walkerplus.com/list/ar0314/", "publisher": "ウォーカープラス", "source_class": "secondary"}
        self.assertFalse(O.validate(rec, self.pol))

    def test_existing_reprint_rows_do_not_reach_facts(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            p = O.log_path("autumn_leaves", env, self.pol)
            p.parent.mkdir(parents=True, exist_ok=True)
            row = {"subject": "autumn_leaves", "name": "高尾山", "state": "見頃予想:11月13日(金)頃から", "state_date": "2026-10-29",
                   "url": "https://koyo.walkerplus.com/topics/article/161896/", "publisher": "ウォーカープラス(ウェザーニューズ予想)",
                   "source_class": "secondary", "read_at": "2026-11-06T05:00:00+09:00"}
            p.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual(O.read_records("autumn_leaves", env, self.pol), [])

    def test_summary_pages_do_not_include_reprint(self):
        for subj in self.pol["summary_pages"].values():
            for pages in subj.values():
                for pg in pages:
                    self.assertNotIn("161896", pg["url"])
                    self.assertNotIn("n-kishou", pg["url"])


# ---- 第3部: 日付の統一・古い表示 ----
import helpers as H  # noqa: E402,F401
from ikimonobiyori import ask  # noqa: E402
from test_stage51 import STRICT, GOOD51, c51  # noqa: E402


class DatesAndStaleDisplay(unittest.TestCase):
    def test_date_range_on_one_state_is_rejected(self):
        self.assertIn("date_range", c51(GOOD51 + "箱根は10/29～11/3時点で「色づきはじめ」です。\n"))
        self.assertIn("date_range", c51(GOOD51 + "箱根は10/29〜11/3時点で「色づきはじめ」です。\n"))
        self.assertNotIn("date_range", c51(GOOD51 + "箱根は10/29時点で「色づきはじめ」です。\n"))
        self.assertNotIn("date_range", c51(GOOD51 + "菊花展が10/31～11/23にあります。\n"))          # 行事の期間は対象外

    def test_hakone_state_far_from_read_date_is_reference_only(self):
        cur = {"state": "色づきはじめ", "state_date": "2026-10-29", "read_at": "2026-11-06T05:00:00+09:00", "publisher": "箱根町観光協会"}
        subj = {"autumn_leaves": {"candidates": [{"name": "箱根強羅公園", "current": dict(cur)},
                                                   {"name": "箱根湖尻", "current": dict(cur, state_date="2026-11-05")},
                                                   {"name": "日光", "current": dict(cur, publisher="日光市観光協会")}]}}
        ask.mark_stale_display(subj, ask.load_policy())
        c = subj["autumn_leaves"]["candidates"]
        self.assertTrue(c[0]["current"]["reference_only"])
        self.assertEqual(c[0]["current"]["gap_days"], 8)
        self.assertNotIn("reference_only", c[1]["current"])        # 2 日前までは現況として使える
        self.assertNotIn("reference_only", c[2]["current"])        # 箱根町観光協会以外は対象外

    def test_reference_only_state_must_be_written_as_reference(self):
        f = copy.deepcopy(STRICT)
        c0 = f["subjects"]["birds"]["candidates"][0]
        c0["current"] = {**(c0.get("current") or {}), "state": "色づきはじめ", "reference_only": True, "url": "https://www.inaturalist.org/"}
        name = c0["name"]
        bad = GOOD51 + f"{name}は10/29時点で「色づきはじめ」です。\n"
        self.assertIn("stale_state_asserted", c51(bad, f))
        ok = GOOD51 + f"{name}は10/29時点の参考として「色づきはじめ」との表示があります。\n"
        self.assertNotIn("stale_state_asserted", c51(ok, f))


class PracticalInfo(unittest.TestCase):
    def facts(self, practical):
        f = copy.deepcopy(STRICT)
        f["lines"]["practical_rules"] = True
        for c in f["subjects"]["birds"]["candidates"]:
            c["practical"] = []
        if practical:
            f["subjects"]["birds"]["candidates"][0]["practical"] = [{"text": "11/6の昭和記念公園は有料エリア9:30~21:00", "publisher": "試験", "url": "https://birds.example.org/"}]
        return f

    def test_practical_line_must_be_used_when_a_read_page_has_it(self):
        f = self.facts(True)
        self.assertIn("practical_missing", c51(GOOD51, f))
        self.assertNotIn("practical_missing", c51(GOOD51 + "11/6の昭和記念公園は有料エリア9:30~21:00です。\n", f))

    def test_fallback_sentence_when_nothing_was_read(self):
        f = self.facts(False)
        self.assertIn("practical_fallback_missing", c51(GOOD51, f))
        self.assertNotIn("practical_fallback_missing", c51(GOOD51 + "アクセスや混雑は出かける前に公式ページで確認してください。\n", f))

    def test_old_facts_without_the_mark_are_unchanged(self):
        self.assertNotIn("practical_fallback_missing", c51(GOOD51))


if __name__ == "__main__":
    unittest.main()


# ---- 第5部: 高山植物ページに種ごとの花期 ----
class AlpinePageSpecies(unittest.TestCase):
    def page(self, month):
        from datetime import datetime
        from ikimonobiyori import wildflower, wildflower_page, guide
        r = wildflower.overview(month=month)
        r["focus"] = "alpine"
        return wildflower_page.build_overview(r, policy=guide.load_policy(), now=datetime(2026, 11, 6, 6, 0), photo_for=lambda n: None)

    def text(self, html):
        import re
        return re.sub(r"<style.*?</style>|<[^>]+>", "\n", html, flags=re.S)

    def test_november_page_says_out_of_season_and_shows_each_species_with_class(self):
        t = self.text(self.page(11))
        self.assertIn("今は11月で、高山の花は見られない時期です", t)
        self.assertIn("チングルマの花期は例年6月〜8月です", t)
        self.assertIn("〈公式〉", t)
        self.assertIn("〈公式ではありません〉", t)

    def test_conflicts_are_shown_together_and_no_month_is_not_invented(self):
        t = self.text(self.page(11))
        self.assertIn("コマクサの花期は、出どころによって幅があります", t)
        self.assertIn("5月〜7月", t)
        self.assertIn("ハクサンコザクラは、月の記載がなく", t)
        self.assertNotIn("ハクサンコザクラの花期は例年", t)

    def test_in_season_month_has_no_out_of_season_banner(self):
        self.assertNotIn("高山の花は見られない時期です", self.text(self.page(7)))


# ---- 第6部: 学名での Commons 検索（通信しない） ----
from ikimonobiyori import guide as G52, guide_photos as GP52  # noqa: E402
from test_stage39 import Net, search as nsearch, NOSLEEP, TODAY  # noqa: E402

POL52 = G52.load_policy()


def commons_pages(title, lic, text, artist="Foo Bar"):
    p = {"title": title, "imageinfo": [{"descriptionurl": "https://commons.wikimedia.org/wiki/" + title, "mime": "image/jpeg",
                                         "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/500px-x.jpg",
                                         "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist},
                                                          "Categories": {"value": text}, "ImageDescription": {"value": text}}}]}
    return json.dumps({"query": {"pages": [p]}})


class ScientificCommons(unittest.TestCase):
    def run_ensure(self, net):
        return GP52.ensure(["ハクサンコザクラ"], theme="野草", policy=POL52, http_get=net.get, http_bytes=net.get_bytes, today=TODAY, sleep=NOSLEEP)

    def net(self, lic, text):
        return Net({"/taxa?": (200, nsearch()),
                    "list=search": (200, json.dumps({"query": {"search": [{"title": "File:Primula_cuneifolia.jpg"}]}})),
                    "prop=imageinfo": (200, commons_pages("File:Primula_cuneifolia.jpg", lic, text))})

    def test_policy_has_the_scientific_names_from_the_instructions(self):
        sci = POL52["photos"]["scientific_names"]["value"]
        self.assertEqual(sci["ハクサンコザクラ"], "Primula cuneifolia")
        self.assertEqual(sci["ツワブキ"], "Farfugium japonicum")
        self.assertNotIn("バラ", sci)                                        # 園芸種は学名で決めない

    def test_photo_with_scientific_name_and_allowed_license_is_saved_and_cached(self):
        net = self.net("CC BY-SA 4.0", "Primula cuneifolia flowers")
        self.assertEqual(self.run_ensure(net)["results"], {"ハクサンコザクラ": "saved"})
        net2 = Net({})
        self.assertEqual(self.run_ensure(net2)["results"], {"ハクサンコザクラ": "cached"})     # 2 回目は通信しない
        self.assertEqual(net2.n, 0)

    def test_nc_license_and_missing_scientific_name_are_not_used(self):
        self.assertEqual(self.run_ensure(self.net("CC BY-NC 4.0", "Primula cuneifolia"))["results"], {"ハクサンコザクラ": "none"})
        self.assertEqual(self.run_ensure(self.net("CC BY 4.0", "a pretty flower"))["results"], {"ハクサンコザクラ": "none"})


# ---- 第7部: 出典リストと冒頭文 ----
class SourcesAndLead(unittest.TestCase):
    def facts(self):
        f = copy.deepcopy(STRICT)
        f["lines"]["practical_rules"] = True
        for c in f["subjects"]["birds"]["candidates"]:
            c["practical"] = []
        return f

    def test_source_not_used_in_the_body_is_rejected(self):
        f = self.facts()
        self.assertNotIn("source_unused", c51(GOOD51, f))
        extra = GOOD51 + "https://www.kawasakidaishi.com\n"
        self.assertIn("source_unused", c51(extra, f))

    def test_old_facts_do_not_get_the_new_source_rule(self):
        self.assertNotIn("source_unused", c51(GOOD51 + "https://www.kawasakidaishi.com\n"))

    def test_lead_must_not_be_assertive_when_a_pick_is_hedged(self):
        f = self.facts()
        hedged = GOOD51.replace("③ 試験の公園: この時期に見られる鳥は、コガモ・オナガガモです。", "③ 試験の公園: 見ごろに近い可能性があります。この時期に見られる鳥は、コガモ・オナガガモです。")
        self.assertNotIn("lead_too_assertive", c51(hedged, f))                        # 冒頭は「見られそうです」
        bad = hedged.replace("で、冬鳥のカモ類が見られそうです。", "で、冬鳥のカモ類が同時に楽しめる週末です。", 1)
        self.assertIn("lead_too_assertive", c51(bad, f))
        self.assertNotIn("lead_too_assertive", c51(bad.replace("可能性があります", "です"), f))   # おすすめに弱い確かさがなければ対象外


class StrictNames(unittest.TestCase):
    def test_shared_area_prefix_does_not_match_another_spot(self):
        from ikimonobiyori import ask_verify as V
        shared = frozenset({"箱根"})
        self.assertNotIn("箱根", V.strict_names("箱根(芦ノ湖)", shared))
        self.assertIn("芦ノ湖", V.strict_names("箱根(芦ノ湖)", shared))
        self.assertIn("中禅寺湖・いろは坂", V.strict_names("中禅寺湖・いろは坂(中禅寺温泉付近)", frozenset()))   # 共通でない前半の形は残す
