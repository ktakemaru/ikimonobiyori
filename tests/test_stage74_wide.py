"""段階74: 「遠くても」の質問(scope が wide)の答え。地域ごとの節に例年の時期の名所(今年の情報は未確認)を入れる・
「今年の情報が確認できていない候補」を地域ごとに分ける・冒頭の「範囲全体から選びました」・Stop フックの出力の形。
合成データ(通信しない。書き込みは一時フォルダだけ)。受け入れの確認だけ、リポジトリの名所カタログ(段階73 の冬桜)を読む。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP
from ikimonobiyori import answer_run as AR
from ikimonobiyori import catalog as CAT
from ikimonobiyori import observations as O
from ikimonobiyori import origins
from ikimonobiyori import skeleton as SK
from ikimonobiyori import stop_hook as SH

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=JST)


def spot(name, km, pref, current=True, kind=None, start="11-01", end="11-30", city=None):
    cur = {"state": "見頃", "state_raw": "見頃", "state_date": "2026-11-09", "publisher": "試験市", "url": f"https://hana.example.org/{name}",
           "source_class": "official", "freshness": "fresh", "age_days": 1, "read_at": "2026-11-10T09:00:00+09:00"} if current else None
    typ = {"text": f"{start}〜{end}", "start": start, "end": end, "url": f"https://hana.example.org/{name}/t", "publisher": "試験市", "source_class": "official"}
    if kind:
        typ["kind"] = kind
    return {"id": "t-" + name, "name": name, "city": city or name + "町", "prefecture": pref, "current": cur, "current_unknown": not current,
            "distance_km": km, "typical": [typ], "typical_line": f"例年の見頃: {start}〜{end}", "events": [], "history": [], "reason_labels": [],
            "practical": [], "festivals": [], "relation": "in_peak"}


def facts(cands, scope="wide"):
    d = {"schema": "ikimono-ask-facts/1", "now": "2026-11-10T09:00:00+09:00", "dates": ["2026-11-14"], "origin": "横浜", "region": "全範囲",
         "subjects": {"flowers": {"subject": "flowers", "candidates": cands, "avoid": [], "nearby_out_of_region": [], "alternatives": []}},
         "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": origins.line_for("横浜", wide=True)},
         "summary_pages": [], "this_round": {}}
    if scope:
        d["scope"] = scope
    return d


CANDS = [spot("試験A", 20, "神奈川県"), spot("試験B", 40, "神奈川県", current=False),
         spot("試験の冬桜", 100, "群馬県", current=False, kind="冬桜", start="11-11", end="12-20"),
         spot("試験の早い花", 90, "埼玉県", current=False, start="12-20", end="01-31")]


class WideSections(unittest.TestCase):
    def setUp(self):
        self.plan = AP.build(facts(CANDS), "flowers")
        self.secs = {s["label"]: s["items"] for s in self.plan["sections"]}

    def test_window_spot_enters_region_section_as_unconfirmed(self):
        gunma = self.secs["栃木・群馬"]
        self.assertEqual([i["name"] for i in gunma], ["試験の冬桜"])
        self.assertTrue(gunma[0]["unconfirmed"])
        p = next(p for p in self.plan["picks"] if p["name"] == "試験の冬桜")
        self.assertIn("今年の情報は未確認", p["note"])
        self.assertIn("冬桜", p["note"])

    def test_current_candidates_first_in_section(self):
        names = [i["name"] for i in self.secs["東京・神奈川"]]
        self.assertEqual(names[0], "試験A")
        self.assertIn("試験B", names)
        self.assertFalse(self.secs["東京・神奈川"][0].get("unconfirmed"))

    def test_spot_outside_window_is_not_added(self):
        self.assertNotIn("試験の早い花", [i["name"] for s in self.plan["sections"] for i in s["items"]])

    def test_picks_follow_section_order(self):
        order = [i["name"] for s in self.plan["sections"] for i in s["items"]]
        self.assertEqual([p["name"] for p in self.plan["picks"]], order[: len(self.plan["picks"])])

    def test_heading_and_origin_line(self):
        text = SK.compose(facts(CANDS), self.plan)
        self.assertIn("範囲全体から選びました。", text)
        self.assertNotIn("横浜からの距離で選びました", text)
        self.assertIn(AP.load_policy()["scope"]["wide"]["heading"], text)
        self.assertNotIn("今回のおすすめ", text)
        self.assertIn("今年の情報は未確認(冬桜の例年の時期に入っています)", text)

    def test_normal_scope_is_unchanged(self):
        plan = AP.build(facts(CANDS, scope=None), "flowers")
        self.assertFalse(any(i.get("unconfirmed") for s in plan["sections"] for i in s["items"]))
        self.assertNotIn("picks_heading", plan)
        self.assertEqual(origins.line_for("横浜"), "横浜からの距離で選びました。")


class NoThisYearByRegion(unittest.TestCase):
    def test_grouped_by_region_not_distance(self):
        pol = AP.scope_policy(AP.load_policy(), "wide")
        rows = [{"name": "近い山梨", "aim": "r_yamanashi_nagano", "score": 10, "breakdown": {"distance": 5}, "typical_line": None},
                {"name": "遠い神奈川", "aim": "r_tokyo_kanagawa", "score": 3, "breakdown": {"distance": 0}, "typical_line": None},
                {"name": "近い神奈川", "aim": "r_tokyo_kanagawa", "score": 4, "breakdown": {"distance": 3}, "typical_line": None}]
        out = AP._no_this_year_rows(rows, pol, region_mode=True)
        self.assertEqual([r["region"] for r in out], ["東京・神奈川", "東京・神奈川", "山梨・長野"])
        self.assertEqual([r["name"] for r in out][:2], ["遠い神奈川", "近い神奈川"])     # 距離の点を除いて並べる

    def test_skeleton_writes_region_labels(self):
        plan = {"no_this_year": [{"name": "甲", "typical_line": None, "region": "東京・神奈川"}, {"name": "乙", "typical_line": None, "region": "栃木・群馬"}]}
        out = SK._no_this_year(plan, {}, SK.cfg(), 80)
        self.assertEqual(out[0], "東京・神奈川")
        self.assertEqual(out[2], "栃木・群馬")


class WideDistance(unittest.TestCase):
    def test_coordinate_less_spot_measured_by_town_point_only_in_wide(self):
        cat_pol = CAT.load_policy()
        c = {"name": "試験", "city": "藤岡市", "point": None}
        self.assertIsNone(O._distance(c, "横浜", cat_pol))
        km = O._distance(c, "横浜", cat_pol, wide=True)
        self.assertIsNotNone(km)
        self.assertLess(km, cat_pol["range_limit"]["max_km"])


class StopHookOutput(unittest.TestCase):
    def test_feedback_form(self):
        out = SH.to_output({"decision": "block", "reason": "[印] 理由"}, "feedback")
        self.assertEqual(out, {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "[印] 理由"}})

    def test_block_form_is_default(self):
        o = {"decision": "block", "reason": "r"}
        self.assertEqual(SH.to_output(o, "block"), o)


class Acceptance(unittest.TestCase):
    def test_far_is_fine_shows_winter_cherries(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IKIMONOBIYORI_DATA_DIR": tmp}
            res = AR.run("遠くても構いません。今見られる花と場所を教えて", now=NOW, env=env, workdir=Path(tmp) / "w")
            text = res["text"]
            self.assertIn("範囲全体から選びました。", text)
            self.assertIn("桜山公園", text)                # 群馬県藤岡市
            self.assertIn("城峯公園", text)                # 埼玉県神川町
            self.assertIn("冬桜", text)
            self.assertIn("今年の情報は未確認", text)
            self.assertIn("栃木・群馬", text)
            self.assertIn("埼玉・千葉・茨城", text)
            plan = json.loads((Path(tmp) / "w" / "answer_plan.json").read_text(encoding="utf-8"))
            for s in plan["sections"]:
                flags = [bool(i.get("unconfirmed")) for i in s["items"]]
                self.assertEqual(flags, sorted(flags), s["label"])       # 今年の現況がある候補が節の先頭


if __name__ == "__main__":
    unittest.main()
