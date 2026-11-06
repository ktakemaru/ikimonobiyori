"""段階55: 曜日チェックの年またぎ（第7部）ほか。合成データ・通信しない。"""
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import festivals as F, season


def chk(text, year=2026):
    return season.weekday_check(text, year)


class CrossYear(unittest.TestCase):
    def test_cross_year_range_with_explicit_years_passes(self):
        r = chk("2026年12月25日（金）〜2027年1月3日（日）")
        self.assertEqual((r["checked"], r["mismatches"]), (2, []))

    def test_omitted_end_year_is_the_next_matching_date(self):
        for t in ("2026年12月25日（金）～1月3日（日）", "12/25(金)〜1/3(日)"):
            self.assertEqual(chk(t)["mismatches"], [], t)
        self.assertEqual(chk("2026年12月25日（金）～1月4日（日）")["mismatches"], ["1月4日（日）"])     # 2027-01-04 は月曜

    def test_each_date_is_checked_in_its_own_year(self):
        self.assertEqual(chk("2026年12月25日（土）～2027年1月3日（日）")["mismatches"], ["2026年12月25日（土）"])
        self.assertEqual(chk("2026年12月25日（金）～2027年1月3日（月）")["mismatches"], ["2027年1月3日（月）"])

    def test_day_only_end_inherits_the_month(self):
        self.assertEqual(chk("2026年10月23日（金）～24日（土）"), {"checked": 2, "mismatches": []})
        self.assertEqual(chk("10月30日（金）～11月1日（日）、11月6日（金）～8日（日）")["mismatches"], [])

    def test_known_calendar_values(self):
        self.assertEqual(date(2026, 12, 25).weekday(), 4)           # 金
        self.assertEqual(date(2027, 1, 1).weekday(), 4)             # 金
        self.assertEqual(date(2027, 1, 3).weekday(), 6)             # 日

    def test_same_year_behaviour_is_unchanged(self):
        self.assertEqual(chk("11/21(土)")["mismatches"], [])
        self.assertEqual(chk("11/21(日)")["mismatches"], ["11/21(日)"])
        self.assertEqual(chk("10/25(土)")["mismatches"], ["10/25(土)"])           # 2026年の10/25は日曜（前年の暦の日付）
        self.assertEqual(chk("2/30(月)")["mismatches"], ["2/30(月)"])             # 存在しない日付は不一致
        self.assertEqual(chk("日付なし")["checked"], 0)

    def test_previous_year_by_weekday(self):
        self.assertFalse(season.previous_year_by_weekday("2026年12月25日（金）〜2027年1月3日（日）", date(2026, 11, 7)))
        self.assertTrue(season.previous_year_by_weekday("12/25(木)〜1/3(土)", date(2026, 11, 7)))        # 前年の暦のまま残った日付
        self.assertIsNone(season.previous_year_by_weekday("曜日なしの 12/25〜1/3", date(2026, 11, 7)))


class FestivalCrossYear(unittest.TestCase):
    def fest(self, raw, start="2026-12-25", end="2027-01-03"):
        return {"id": "t", "name": "試験の冬の催し", "start": start, "end": end, "raw": raw, "organizer": "試験", "organizer_class": "official",
                "url": "https://example.org/", "spots": ["x"]}

    def test_cross_year_event_is_usable(self):
        ok, why = F.usable(self.fest(["2026年12月25日（金）〜2027年1月3日（日）"]), date(2026, 11, 7))
        self.assertEqual((ok, why), (True, None))

    def test_wrong_weekday_is_dropped(self):
        ok, why = F.usable(self.fest(["2026年12月25日（土）〜2027年1月3日（日）"]), date(2026, 11, 7))
        self.assertEqual((ok, why), (False, "weekday_mismatch"))

    def test_last_season_event_is_still_dropped(self):
        ok, why = F.usable(self.fest(["2025年12月25日（木）〜2026年1月3日（土）"], "2025-12-25", "2026-01-03"), date(2026, 11, 7))
        self.assertEqual((ok, why), (False, "other_year"))

    def test_moonlight_rose_garden_is_now_present(self):
        doc = F.load()
        self.assertIn("ibaraki-moonlight-rose-2026", {f["id"] for f in doc["festivals"]})
        self.assertEqual(F.dropped(date(2026, 11, 7), doc), {})


class NoYamakeiUrlInData(unittest.TestCase):
    """段階55 第8部（利用者の決定 2026-11-06）: 事実データに山と溪谷オンラインの URL を置かない。台帳の承認待ち情報源（ビジターセンター）と
    取り扱い規則（policy の restricted_sources）は除く。"""
    ALLOWED = {"sources/secondary/autumn_leaves.yaml", "observations/policy.yaml", "visitor_centers/policy.yaml"}

    def test_fact_data_has_no_yamakei_url(self):
        from pathlib import Path
        from ikimonobiyori.paths import DATA_FILES_DIR
        bad = []
        for p in Path(DATA_FILES_DIR).rglob("*"):
            if p.is_file() and p.suffix in (".yaml", ".yml", ".json", ".jsonl", ".md", ".html"):
                rel = p.relative_to(DATA_FILES_DIR).as_posix()
                if rel in self.ALLOWED:
                    continue
                if "yamakei-online" in p.read_text(encoding="utf-8", errors="replace"):
                    bad.append(rel)
        self.assertEqual(bad, [])

    def test_a_synthetic_leak_would_be_found(self):
        self.assertIn("yamakei-online", "出どころ: https://www.yamakei-online.com/x")

    def test_removed_facts_are_gone_and_others_stay(self):
        from ikimonobiyori import wildflower_species as WS
        facts, data = WS.load()
        self.assertFalse([k for k in facts["sources"] if "yamakei" in facts["sources"][k]["url"]])
        names = {s["name"] for s in data["species"]}
        self.assertIn("コマクサ", names)
        notes_sites = {m["site"] for m in data["mountain_notes"]}
        self.assertNotIn("m076", notes_sites)                       # 会津駒ヶ岳: 山と溪谷オンラインだけが出どころの記載を削除


# ---- 第2部: ビジターセンター・自然観察施設の台帳 ----
from ikimonobiyori import visitor_centers as V  # noqa: E402

VP = V.load_policy()


def center(**kw):
    c = {"id": "vc-test", "name": "試験自然観察センター", "operator": "試験財団", "operator_kind": "財団", "site_url": "https://nature.example.org/",
         "info_url": "https://nature.example.org/news/", "frequency": "毎週", "format": "html", "class": "official", "within_range": True,
         "terms": {"url": "https://nature.example.org/policy", "reprint_banned": False, "note": "転載・自動取得の記載なし"},
         "approval": {"status": "pending", "reason": "承認待ち"}}
    c.update(kw)
    return c


def report(**kw):
    r = {"center": "vc-test", "date": "2026-11-05", "state": "紅葉が見ごろ", "species": ["ジョウビタキ", "シメ"], "url": "https://nature.example.org/news/1"}
    r.update(kw)
    return r


class VisitorCenterLedger(unittest.TestCase):
    TODAY = date(2026, 11, 7)

    def test_valid_center_passes_and_ledger_starts_pending(self):
        self.assertEqual(V.validate_center(center(), VP), [])
        for c in V.load_centers():                              # 新しく足す施設はすべて承認待ち（承認は本人）
            self.assertEqual(c["approval"]["status"], "pending", c["id"])

    def test_required_fields_and_ranges(self):
        self.assertTrue(V.validate_center(center(name=None), VP))
        self.assertTrue(V.validate_center(center(**{"class": "official?"}), VP))
        self.assertTrue(V.validate_center(center(format="docx"), VP))
        self.assertTrue(V.validate_center(center(site_url="javascript:alert(1)"), VP))

    def test_excluded_hosts(self):
        for u in ("https://www.facebook.com/x", "https://x.com/y", "https://tenki.jp/a", "https://www.yamakei-online.com/mt_info/info_detail.php"):
            self.assertTrue(V.validate_center(center(info_url=u), VP), u)

    def test_state_is_limited_to_30_chars_and_not_a_sentence(self):
        self.assertEqual(V.validate_report(report(), VP), [])
        self.assertTrue(V.validate_report(report(state="あ" * 31), VP))
        self.assertEqual(V.validate_report(report(state="あ" * 30), VP), [])
        self.assertTrue(V.validate_report(report(state="色づき始めました。山頂は寒いです"), VP))

    def test_species_are_limited_to_10_one_word_each(self):
        self.assertEqual(V.validate_report(report(species=[f"鳥{i}" for i in range(10)]), VP), [])
        self.assertTrue(V.validate_report(report(species=[f"鳥{i}" for i in range(11)]), VP))
        self.assertTrue(V.validate_report(report(species=["ジョウビタキが木にとまっていました。"]), VP))

    def test_article_text_is_not_accepted(self):
        self.assertTrue(V.validate_report(report(body="記事の本文"), VP))
        self.assertTrue(V.validate_report(report(text="お便りの文章"), VP))
        self.assertTrue(V.validate_report(report(date="11/5"), VP))                      # 年のない日付は受け付けない

    def test_pending_center_is_never_used(self):
        c = center()
        self.assertEqual(V.usable_center(c, self.TODAY, VP), (False, "not_approved"))
        self.assertEqual(V.usable_report(report(), [c], self.TODAY, VP), (False, "not_approved"))
        self.assertEqual(V.approved_centers(self.TODAY, [c], VP), [])
        self.assertEqual(len(V.pending_centers([c])), 1)

    def test_approved_center_is_used_and_revoked_is_not(self):
        ok = center(approval={"status": "approved", "approved_by": "利用者", "reason": "承認"})
        self.assertEqual(V.usable_report(report(), [ok], self.TODAY, VP), (True, None))
        rv = center(approval={"status": "revoked", "reason": "取り消し"})
        self.assertEqual(V.usable_center(rv, self.TODAY, VP), (False, "revoked"))
        noone = center(approval={"status": "approved", "reason": "承認者なし"})
        self.assertEqual(V.usable_center(noone, self.TODAY, VP), (False, "invalid"))        # 承認した人が書かれていない承認は通さない

    def test_reprint_ban_must_be_stated_in_the_note(self):
        bad = center(terms={"url": "https://nature.example.org/policy", "reprint_banned": True, "note": "規約あり"})
        self.assertTrue(V.validate_center(bad, VP))
        good = center(terms={"url": "https://nature.example.org/policy", "reprint_banned": True, "note": "転載禁止の明示あり（無断転載を禁ずる）"})
        self.assertEqual(V.validate_center(good, VP), [])

    def test_season_end_uses_dated_year(self):
        appr = {"status": "approved", "approved_by": "利用者", "reason": "承認"}
        last_year = center(approval=appr, season_end={"last_issue": "2025-10-31"})
        self.assertEqual(V.usable_center(last_year, self.TODAY, VP), (False, "previous_season"))      # 前シーズンの最終号しかない
        ended = center(approval=appr, season_end={"last_issue": "2026-10-31"})
        self.assertEqual(V.usable_center(ended, self.TODAY, VP), (False, "ended"))                   # 今シーズンの最終号を過ぎた
        running = center(approval=appr, season_end={"last_issue": "2026-12-25"})
        self.assertEqual(V.usable_center(running, self.TODAY, VP), (True, None))
        self.assertTrue(V.validate_center(center(season_end={"last_issue": "10/31"}), VP))             # 年のない日付は受け付けない

    def test_old_report_of_previous_season_is_not_used(self):
        appr = {"status": "approved", "approved_by": "利用者", "reason": "承認"}
        self.assertEqual(V.usable_report(report(date="2025-11-05"), [center(approval=appr)], self.TODAY, VP), (False, "previous_season"))

    def test_report_line_has_only_short_words_date_and_center(self):
        line = V.report_line(center(), report(), VP)
        self.assertEqual(line, "試験自然観察センター発信、11/5時点: 紅葉が見ごろ（ジョウビタキ・シメ）")


if __name__ == "__main__":
    unittest.main()
