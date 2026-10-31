"""段階33: 花の名所の座標(Wikidata との照合)・地域なしの質問・N分咲き・一部の品種・来週以降の欄・catalog_audit --out・旬の花の種類。通信なし。合成のデータだけ。"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

import test_stage32 as T
from ikimonobiyori import catalog, catalog_audit, catalog_coords, regional

RP = regional.load_policy()
CP = RP["coordinates"]
H_LATER = RP["text"]["headings"]["early"]
H_REC = RP["text"]["headings"]["recommend"]


def entry(city="平塚市", pref="神奈川県", name="試験園"):
    return {"id": "hana-0001", "name": name, "tags": {"prefecture": pref, "city": city}}


def hit(lat, lon, desc, qid="Q1"):
    return {"qid": qid, "lat": lat, "lon": lon, "description": desc}


class Coordinates(unittest.TestCase):
    def test_1_accepts_only_matching_place_inside_bounds(self):
        pt, why = catalog_coords.judge(entry(), {"試験園": hit(35.33, 139.35, "平塚市にある公園")}, CP)
        self.assertEqual((pt["lat"], pt["lon"], pt["qid"]), (35.33, 139.35, "Q1"), why)

    def test_1_ward_and_city_mismatch_gives_no_point(self):
        for desc in ("小田原市にある公園", "横浜市西区にある公園", ""):
            pt, _ = catalog_coords.judge(entry(city="横浜市中区"), {"試験園": hit(35.4, 139.6, desc)}, CP)
            self.assertIsNone(pt, desc)
        pt, _ = catalog_coords.judge(entry(city="横浜市中区"), {"試験園": hit(35.4, 139.6, "横浜市にある公園")}, CP)
        self.assertIsNotNone(pt)

    def test_1_out_of_bounds_ambiguous_and_missing_give_no_point(self):
        pt, why = catalog_coords.judge(entry(), {"試験園": hit(34.0, 139.35, "平塚市にある公園")}, CP)
        self.assertIsNone(pt)
        self.assertIn("範囲の外", why)
        pt, why = catalog_coords.judge(entry(), {"試験園": hit(35.3, 139.3, "平塚市にある公園", "Q1"), "試験": hit(35.31, 139.31, "平塚市にある公園", "Q2")}, CP)
        self.assertIsNone(pt)
        self.assertIn("複数", why)
        pt, _ = catalog_coords.judge(entry(), {"試験園": None}, CP)
        self.assertIsNone(pt)
        pt, _ = catalog_coords.judge(entry(), {"試験園": hit(35.3, 139.3, "平塚市にある曖昧さ回避ページ")}, CP)
        self.assertIsNone(pt)

    def test_1_unlisted_prefecture_gets_no_point(self):
        pt, _ = catalog_coords.judge(entry(pref="東京都", city="港区"), {"試験園": hit(35.6, 139.7, "港区にある公園")}, CP)
        self.assertIsNone(pt)

    def test_1_coordinate_source_is_limited_to_two_kinds_by_schema(self):
        import jsonschema
        schema = json.loads((Path(catalog.__file__).parent / "schemas" / "site-catalog.schema.json").read_text(encoding="utf-8"))
        sub = {"$ref": "#/$defs/entry", "$defs": schema["$defs"]}
        base = T.site("hana-0001", "試験園", ["秋バラ"], point=(35.3, 139.3))
        for k, ok in (("wikidata", True), ("official_map", True), ("google_maps", False)):
            e = {**base, "coordinate_source": {"kind": k, "checked_on": "2026-10-31"}}
            errs = list(jsonschema.Draft202012Validator(sub).iter_errors(e))
            self.assertEqual(not [x for x in errs if "coordinate_source" in str(list(x.absolute_path))], ok, k)

    def test_1_insert_points_writes_point_and_source_without_touching_others(self):
        text = "entries:\n  - id: hana-0001\n    name: A\n    kind: area\n    status: approved\n  - id: hana-0002\n    name: B\n    kind: area\n    status: approved\n"
        rows = [{"id": "hana-0002", "name": "B", "point": {"lat": 35.3, "lon": 139.3, "qid": "Q9", "title": "B"}, "reason": "ok"}]
        new, n = catalog_coords.insert_points(text, rows, "2026-10-31")
        self.assertEqual(n, 1)
        import yaml
        d = {e["id"]: e for e in yaml.safe_load(new)["entries"]}
        self.assertNotIn("point", d["hana-0001"])
        self.assertEqual(d["hana-0002"]["point"]["lat"], 35.3)
        self.assertEqual(d["hana-0002"]["coordinate_source"]["kind"], "wikidata")

    def test_1_real_catalog_points_are_in_range_and_have_a_source(self):
        b = CP["bounds_by_prefecture"]["神奈川県"]
        n = 0
        for e in catalog.load_catalog("flowers")["entries"]:
            if "coordinate_source" in e:
                n += 1
                self.assertIn(e["coordinate_source"]["kind"], CP["allowed_sources"])
                self.assertTrue(b["lat"][0] <= e["point"]["lat"] <= b["lat"][1] and b["lon"][0] <= e["point"]["lon"] <= b["lon"][1], e["name"])
        self.assertGreater(n, 0)


class NoRegion(unittest.TestCase):
    def test_2_sites_with_points_appear_in_distance_question_and_without_do_not(self):
        w = [T.win("秋バラ", "10-15", "11-15")]
        ents = [T.site("hana-0001", "試験の座標あり園", ["秋バラ"], windows=w, point=(35.45, 139.6)),
                T.site("hana-0002", "試験の座標なし園", ["秋バラ"], windows=w),
                T.site("hana-0003", "試験の遠い園", ["秋バラ"], pref="北海道", windows=w, point=(43.0, 141.3))]
        t = T.answer_text(ents, [], region=None, nearby=False)
        self.assertIn("試験の座標あり園", t)
        self.assertNotIn("試験の座標なし園", t)
        self.assertNotIn("試験の遠い園", t)

    def test_3_region_question_keeps_other_prefectures_out_of_recommendation(self):
        w = [T.win("秋バラ", "10-15", "11-15")]
        ents = T.IN_KANAGAWA + [T.site("hana-0009", "試験の東京園", ["秋バラ"], pref="東京都", city="港区", windows=w, point=(35.66, 139.7))]
        t = T.answer_text(ents, [], nearby=False)
        self.assertNotIn("試験の東京園", "\n".join(T.section(t, H_REC)))


class Bunzaki(unittest.TestCase):
    def test_4_bunzaki_is_read_by_lower_bound(self):
        cases = {"２～３分咲き": "bud", "現在２～３分咲きです": "bud", "5分咲き": "bud", "８分咲き": "good", "8分咲き": "good", "７～８分咲き": "bud",
                 "8~9分咲き": "good", "10分咲き": "good", "満開": "full", "ほぼ満開": "good", "見頃": "good"}
        for raw, st in cases.items():
            self.assertEqual(regional.vocab_stage(raw, RP), st, raw)

    def test_4_unreadable_stays_unreadable(self):
        for raw in ("咲いています", "ブラウンがメイン", "満開に近い", "分咲き", "11分咲き"):
            self.assertIsNone(regional.vocab_stage(raw, RP), raw)

    def test_5_variety_only_peak_is_not_whole_garden_peak(self):
        for raw in ("「センセーション」が見頃を迎えています", "一部の品種が見頃", "ピンクの品種が見ごろです", "エリアによって満開"):
            self.assertTrue(regional.is_partial_variety(raw, RP), raw)
            self.assertIsNone(regional.vocab_stage(raw, RP), raw)
        for raw in ("見頃", "満開", "ほぼ満開", "２～３分咲き"):
            self.assertFalse(regional.is_partial_variety(raw, RP), raw)

    def test_5_partial_goes_to_last_line_only(self):
        w = [T.win("コスモス", "10-01", "11-10")]
        ents = [T.site("hana-0005", "試験のコスモス園", ["コスモス"], windows=w)]
        t = T.answer_text(ents, [T.mkrec("hana-0005", "コスモス", "「センセーション」が見頃を迎えています")], kinds=["コスモス"], nearby=False)
        self.assertEqual(T.section(t, H_REC), [])
        last = [ln for ln in t.splitlines() if ln.strip()][-1]
        self.assertIn("一部の品種が見頃", last)
        self.assertIn("センセーション", last)
        self.assertEqual(sum(1 for ln in t.splitlines() if "一部の品種が見頃" in ln), 1)

    def test_4_kurihama_style_state_is_before_peak_and_listed_for_later(self):
        ents = [T.site("hana-0005", "試験のコスモス園", ["コスモス"], windows=[T.win("コスモス", "10-01", "11-10")])]
        t = T.answer_text(ents, [T.mkrec("hana-0005", "コスモス", "現在２～３分咲きです")], kinds=["コスモス"], nearby=False)
        self.assertEqual(T.section(t, H_REC), [])
        later = "\n".join(T.section(t, H_LATER))
        self.assertIn("試験のコスモス園", later)
        self.assertIn("現在２～３分咲きです", later)
        self.assertIn("来週以降", later)


class Later(unittest.TestCase):
    def test_6_before_peak_event_and_window_are_listed_with_labels(self):
        ents = [T.site("hana-0001", "試験の見頃前園", ["秋バラ"], windows=[T.win("秋バラ", "10-15", "11-15")]),
                T.site("hana-0002", "試験のイベント園", ["秋バラ"], events=[T.ev("秋バラ", "試験フェス", "2026-11-07", "2026-11-20")]),
                T.site("hana-0003", "試験の例年園", ["秋バラ"], windows=[T.win("秋バラ", "11-10", "11-30")])]
        t = T.answer_text(ents, [T.mkrec("hana-0001", "バラ", "咲き始め")], nearby=False)
        later = "\n".join(T.section(t, H_LATER))
        self.assertIn("試験の見頃前園", later)
        self.assertIn("公式の状態「咲き始め」", later)
        self.assertIn("試験のイベント園", later)
        self.assertIn("今年のイベント期間つき", later)
        self.assertIn("試験の例年園", later)
        self.assertIn("例年の時期のみ", later)
        self.assertEqual(T.section(t, H_REC), [])

    def test_6_past_and_unapproved_host_only_are_not_listed(self):
        bad = {**T.win("秋バラ", "11-10", "11-30"), "source_host": "example.com", "unapproved_host": True}
        bad_ev = {**T.ev("秋バラ", "印つきフェス", "2026-11-07", "2026-11-20"), "source_host": "example.com", "unapproved_host": True}
        ents = [T.site("hana-0001", "試験の終盤園", ["秋バラ"], windows=[T.win("秋バラ", "10-15", "11-15")]),
                T.site("hana-0002", "試験の印つき時期園", ["秋バラ"], windows=[bad]),
                T.site("hana-0003", "試験の印つきイベント園", ["秋バラ"], events=[bad_ev]),
                T.site("hana-0004", "試験の遠い園", ["秋バラ"], windows=[T.win("秋バラ", "12-20", "12-30")])]
        t = T.answer_text(ents, [T.mkrec("hana-0001", "バラ", "終了")], nearby=False)
        later = "\n".join(T.section(t, H_LATER))
        for n in ("試験の終盤園", "試験の印つき時期園", "試験の印つきイベント園", "試験の遠い園"):
            self.assertNotIn(n, later)

    def test_6_no_match_means_no_heading_and_max_three(self):
        t = T.answer_text(T.IN_KANAGAWA, [], nearby=False)
        self.assertNotIn(H_LATER, t)
        ents = [T.site(f"hana-000{i}", f"試験の例年園{i}", ["秋バラ"], windows=[T.win("秋バラ", "11-10", "11-30")]) for i in range(1, 6)]
        t = T.answer_text(ents, [], nearby=False)
        self.assertEqual(len(T.section(t, H_LATER)), RP["later"]["max_items"]["value"])

    def test_7_no_forbidden_terms(self):
        ents = [T.site("hana-0001", "試験園", ["コスモス"], windows=[T.win("コスモス", "10-01", "11-10")]),
                T.site("hana-0002", "試験園2", ["コスモス"], windows=[T.win("コスモス", "11-10", "11-30")])]
        t = T.answer_text(ents, [T.mkrec("hana-0001", "コスモス", "「センセーション」が見頃です")], kinds=["コスモス"], nearby=False)
        self.assertEqual(regional.forbidden_found(t, RP), [])


class Audit(unittest.TestCase):
    def test_8_out_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "audit.md"
            with redirect_stdout(io.StringIO()):
                code = catalog_audit.main(["--out", str(p)])
            self.assertEqual(code, 0)
            self.assertIn("needs_confirmation", p.read_text(encoding="utf-8"))
            with redirect_stdout(io.StringIO()):
                catalog_audit.main([])
            self.assertEqual(len(list(Path(d).iterdir())), 1)


class Calendar(unittest.TestCase):
    def test_seasonal_kinds_from_target_date(self):
        ents = [T.site("hana-0001", "試験園", ["秋バラ", "コスモス"], windows=[T.win("秋バラ", "10-15", "11-15"), T.win("コスモス", "09-01", "10-20")])]
        self.assertEqual(list(regional.seasonal_kinds(ents, T.DATES, RP)), ["秋バラ"])
        self.assertEqual(list(regional.seasonal_kinds(ents, [date(2026, 10, 18)], RP)), ["コスモス", "秋バラ"])

    def test_few_kinds_line_at_end(self):
        ents = [T.site("hana-0001", "試験園", ["秋バラ"], windows=[T.win("秋バラ", "10-15", "11-15")])]
        part = T.build_part(ents, [])
        t = regional.compose(region=T.KANAGAWA, kinds=["秋バラ"], dates=T.DATES, now=T.NOW, part=part, nearby_part=None, policy=T.POLICY, seasonal=True)
        self.assertIn("登録している名所がまだ少なめです", [ln for ln in t.splitlines() if ln.strip()][-1])
        t2 = regional.compose(region=T.KANAGAWA, kinds=["秋バラ"], dates=T.DATES, now=T.NOW, part=part, nearby_part=None, policy=T.POLICY)
        self.assertNotIn("登録している名所がまだ少なめです", t2)


if __name__ == "__main__":
    unittest.main()
