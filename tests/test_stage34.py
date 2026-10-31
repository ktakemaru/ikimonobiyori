"""段階34: 観察の記録(record)・状態の正規化・取りに行く対象(refresh --plan)・答えの材料(facts)。通信なし。合成のデータだけ。"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import observations as O

P = O.load_policy()
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 1, 10, 0, tzinfo=JST)
D = [date(2026, 11, 2)]

SPOTS = {"spots": [
    {"id": "t-k-1", "subject": "autumn_leaves", "name": "試験の湖", "prefecture": "神奈川県", "city": "試験町", "area": "試験",
     "typical": [{"text": "11月上旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/1", "year": 2026, "source_class": "secondary"}],
     "pages": [{"url": "https://kouyou.example.com/1", "publisher": "試験サイト", "source_class": "secondary"}], "search": "試験の湖 紅葉"},
    {"id": "t-k-2", "subject": "autumn_leaves", "name": "試験の美術館", "prefecture": "神奈川県", "city": "試験町", "area": "試験",
     "typical": [{"text": "11月中旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/2", "year": 2026, "source_class": "secondary"}],
     "pages": []},
    {"id": "t-k-3", "subject": "autumn_leaves", "name": "試験の峠", "prefecture": "神奈川県", "city": "試験市",
     "typical": [{"text": "10月中旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/3", "year": 2026, "source_class": "secondary"}],
     "pages": []},
    {"id": "t-k-4", "subject": "autumn_leaves", "name": "試験の寺", "prefecture": "神奈川県", "city": "試験市",
     "typical": [{"text": "11月下旬～12月中旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/4", "year": 2026, "source_class": "secondary"}],
     "pages": []},
    {"id": "t-k-5", "subject": "autumn_leaves", "name": "試験の温泉", "prefecture": "神奈川県", "city": "試験町",
     "typical": [{"text": "11月上旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/5", "year": 2026, "source_class": "secondary"}],
     "pages": []},
    {"id": "t-k-6", "subject": "autumn_leaves", "name": "試験の都の庭", "prefecture": "東京都", "city": "試験区",
     "typical": [{"text": "11月上旬～11月下旬", "publisher": "試験サイト", "url": "https://kouyou.example.com/6", "year": 2026, "source_class": "secondary"}],
     "pages": []},
    {"id": "t-h-1", "subject": "flowers", "name": "試験の庭園", "prefecture": "神奈川県", "city": "試験市", "flower_kinds": ["菊"],
     "events": [{"name": "試験の菊花展", "kind": "菊", "start": "2026-10-31", "end": "2026-11-23", "url": "https://hana.example.org/", "publisher": "試験の庭園", "source_class": "official"}],
     "pages": []},
]}
CATALOGS = {"autumn_leaves": {"entries": []}, "flowers": {"entries": []}}


def rec(spot, state, state_date, cls="secondary", url="https://kouyou.example.com/list", **kw):
    return {"subject": kw.pop("subject", "autumn_leaves"), "spot": spot, "state": state, "state_date": state_date, "url": url,
            "publisher": "試験サイト", "source_class": cls, **kw}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows, at=NOW):
        return O.record(rows, env=self.env, now=at)

    def facts(self, subject="autumn_leaves", region="神奈川", now=NOW, dates=D):
        return O.facts(subject, region=region, dates=dates, now=now, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)

    def plan(self, now=NOW):
        return O.plan("autumn_leaves", region="神奈川", dates=D, now=now, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)


class Record(Base):
    def test_1_records_with_source_class(self):
        out = self.write([rec("t-k-1", "色づき始め", "2026-10-31")])
        self.assertEqual((out["written"], out["rejected"]), (1, []))
        rows = O.read_records("autumn_leaves", self.env)
        self.assertEqual((rows[0]["source_class"], rows[0]["state_norm"], rows[0]["host"]), ("secondary", "色づき始め", "kouyou.example.com"))
        self.assertEqual(rows[0]["read_at"], NOW.isoformat())

    def test_1_rejects_missing_url_state_or_class(self):
        bad = [{**rec("t-k-1", "青葉", None), "url": None}, {**rec("t-k-1", "", None)}, {**rec("t-k-1", "青葉", None), "source_class": None}]
        out = self.write(bad)
        self.assertEqual(out["written"], 0)
        self.assertEqual([r["index"] for r in out["rejected"]], [0, 1, 2])

    def test_1_any_host_is_accepted(self):
        out = self.write([rec("t-k-1", "青葉", None, url="https://blog.unknown-host.example.net/p/1")])
        self.assertEqual(out["written"], 1)

    def test_1_raw_text_is_cut_to_80_chars(self):
        self.write([rec("t-k-1", "あ" * 200, None)])
        self.assertEqual(len(O.read_records("autumn_leaves", self.env)[0]["state"]), 80)

    def test_1_same_fact_same_day_is_not_duplicated(self):
        self.write([rec("t-k-1", "青葉", "2026-10-31")])
        out = self.write([rec("t-k-1", "青葉", "2026-10-31")])
        self.assertEqual((out["written"], out["duplicates"]), (0, 1))


class Normalize(unittest.TestCase):
    def test_2_autumn_four_words(self):
        for raw, want in (("青葉", "青葉"), ("色づき始め", "色づき始め"), ("そろそろ見ごろ", "色づき始め"), ("見頃", "見頃"),
                          ("見ごろ", "見頃"), ("落葉", "見頃過ぎ"), ("見頃過ぎ", "見頃過ぎ"), ("大山周辺はまだ色づき始め", "色づき始め")):
            self.assertEqual(O.normalize("autumn_leaves", raw, P), want, raw)

    def test_2_flowers_bloom_ratio(self):
        for raw, want in (("8分咲き", "見頃"), ("5〜8分咲き", "見頃前"), ("３分咲き", "見頃前"), ("満開", "見頃"), ("見頃", "見頃"),
                          ("咲き始め", "見頃前"), ("見頃過ぎ", "見頃過ぎ"), ("終了", "見頃過ぎ"), ("五分咲き", "見頃前"),
                          ("開花状況は約3割。これから見頃を迎えます", "見頃前"), ("11月中旬頃に見頃を迎える予定", "見頃前"), ("見頃を迎えました", "見頃")):
            self.assertEqual(O.normalize("flowers", raw, P), want, raw)

    def test_2_variety_only_peak_is_not_garden_peak(self):
        self.assertEqual(O.normalize("flowers", "「プリンセスミチコ」が見頃です", P), P["unknown_state"])
        self.assertEqual(O.normalize("flowers", "一部の品種が見頃", P), P["unknown_state"])

    def test_2_unreadable_is_kept_as_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            O.record([rec("t-k-1", "ブラウンがメイン", None)], env={"IKIMONOBIYORI_DATA_DIR": d}, now=NOW)
            r = O.read_records("autumn_leaves", {"IKIMONOBIYORI_DATA_DIR": d})[0]
        self.assertEqual((r["state_norm"], r["state"]), (P["unknown_state"], "ブラウンがメイン"))

    def test_typical_text_parsing(self):
        self.assertEqual(O.parse_typical("11月中旬～12月上旬", P), ("11-11", "12-10"))
        self.assertEqual(O.parse_typical("12月上旬", P), ("12-01", "12-10"))
        self.assertEqual(O.parse_typical("11月20日頃", P), ("11-15", "11-25"))
        self.assertIsNone(O.parse_typical("記載なし", P))


class Plan(Base):
    def test_3_none_stale_very_stale_listed_fresh_not(self):
        self.write([rec("t-k-1", "色づき始め", "2026-10-31")])                       # 新しい(1 日前)
        self.write([rec("t-k-2", "青葉", "2026-10-22")])                           # 古い(10 日前)
        self.write([rec("t-k-3", "青葉", "2026-09-01")])                           # かなり古い
        p = self.plan()
        cls = {i["id"]: i["freshness"]["class"] for i in p["items"]}
        self.assertEqual(cls["t-k-2"], "stale")
        self.assertEqual(cls["t-k-3"], "very_stale")
        self.assertEqual(cls["t-k-4"], "none")
        self.assertNotIn("t-k-1", cls)
        self.assertIn("試験の湖", p["fresh"])
        self.assertTrue(p["needs_fetch"])
        self.assertNotIn("t-k-6", cls)                                               # 地域の外は出ない

    def test_3_summary_pages_come_first(self):
        p = self.plan()
        self.assertTrue(p["summary_pages"])
        self.assertEqual(p["summary_pages"][0]["url"], P["summary_pages"]["autumn_leaves"]["神奈川県"][0]["url"])
        self.assertTrue(all("search" in i for i in p["items"]))

    def test_3_all_fresh_means_nothing_to_fetch(self):
        self.write([rec(f"t-k-{i}", "色づき始め", "2026-10-31") for i in range(1, 6)])
        p = self.plan()
        self.assertEqual((p["needs_fetch"], p["items"], p["summary_pages"]), (False, [], []))


class Facts(Base):
    def names(self, f):
        return [c["name"] for c in f["candidates"]]

    def test_4_all_records_60_days_old_still_three_candidates(self):
        old = (NOW - timedelta(days=60)).date().isoformat()
        self.write([rec(f"t-k-{i}", "青葉", old) for i in range(1, 6)], at=NOW - timedelta(days=60))
        f = self.facts()
        self.assertGreaterEqual(len(f["candidates"]), 3)
        self.assertTrue(all(c["current"]["freshness"] == "very_stale" for c in f["candidates"] if c["current"]))

    def test_4_empty_records_still_three_candidates(self):
        f = self.facts()
        self.assertGreaterEqual(len(f["candidates"]), 3)
        self.assertTrue(all(c["current"] is None and c["evidence"] == "typical_only" for c in f["candidates"]))
        self.assertTrue(all(c["typical"] for c in f["candidates"]))

    def test_4_secondary_values_are_used_and_labelled(self):
        self.write([rec("t-k-1", "色づき始め", "2026-10-31")])
        c = next(x for x in self.facts()["candidates"] if x["id"] == "t-k-1")
        self.assertEqual((c["current"]["state"], c["current"]["source_class"], c["current"]["state_date"]), ("色づき始め", "secondary", "2026-10-31"))
        self.assertIn("coming", c["reasons"])

    def test_4_avoid_and_alternatives(self):
        self.write([rec("t-k-4", "青葉", "2026-10-31"), rec("t-k-1", "色づき始め", "2026-10-31")])
        f = self.facts()
        self.assertEqual([a["id"] for a in f["avoid"]], ["t-k-4"])
        self.assertEqual(f["avoid"][0]["avoid"], "too_early")
        self.assertNotIn("試験の寺", self.names(f))
        self.assertEqual([a["name"] for a in f["alternatives"]], ["試験の庭園"])
        self.assertEqual(f["alternatives"][0]["events"][0]["name"], "試験の菊花展")

    def test_4_past_peak_is_avoided(self):
        self.write([rec("t-k-3", "落葉", "2026-10-31")])
        f = self.facts()
        self.assertEqual(next(a for a in f["avoid"] if a["id"] == "t-k-3")["avoid"], "past")

    def test_4_ordering_peak_first_then_fresh_over_typical(self):
        self.write([rec("t-k-5", "見頃", "2026-10-31", cls="official"), rec("t-k-1", "色づき始め", "2026-10-31")])
        f = self.facts()
        self.assertEqual(f["candidates"][0]["id"], "t-k-5")
        self.assertEqual(f["candidates"][0]["evidence"], "fresh_official")
        ids = [c["id"] for c in f["candidates"]]
        self.assertLess(ids.index("t-k-1"), ids.index("t-k-2"))                     # 色づき始めで例年の見頃にかかる > 例年の見頃の前(記録なし)

    def test_4_unknown_name_record_is_kept_outside_list(self):
        self.write([{"subject": "autumn_leaves", "name": "一覧にない谷", "city": "試験村", "state": "色づき始め", "state_date": "2026-10-31",
                     "url": "https://news.example.jp/a", "publisher": "試験新聞", "source_class": "secondary"}])
        f = self.facts()
        self.assertIn("一覧にない谷", self.names(f))

    def test_4_outside_list_record_follows_its_area(self):
        self.write([{"subject": "autumn_leaves", "name": "別の地域の山", "state": "見ごろ", "state_date": "2026-10-31", "prefecture": "神奈川県",
                     "url": "https://pref.example.jp/a", "publisher": "試験県", "source_class": "official"},
                    {"subject": "autumn_leaves", "name": "試験の宿場", "state": "色づきはじめ", "state_date": "2026-10-31", "area": "試験",
                     "url": "https://kankou.example.jp/a", "publisher": "試験町観光協会", "source_class": "official"}])
        regions = {"regions": [{"name": "試験", "aliases": [], "match": {"areas": ["試験"]}}]}
        import unittest.mock as M
        with M.patch.object(O.S, "load_regions", return_value=regions):
            f = O.facts("autumn_leaves", region="試験", dates=D, now=NOW, env=self.env, spots_doc=SPOTS, catalogs=CATALOGS)
        names = self.names(f)
        self.assertIn("試験の宿場", names)
        self.assertNotIn("別の地域の山", names)

    def test_4_no_internal_terms_in_labels(self):
        self.write([rec("t-k-1", "色づき始め", "2026-10-31")])
        f = self.facts()
        labels = " ".join(" ".join(c["reason_labels"]) + c["relation_label"] for c in f["candidates"])
        self.assertEqual(O.self_check(labels, P), [])

    def test_cli_record_and_facts_run(self):
        p = Path(self.tmp.name) / "reads.json"
        p.write_text(json.dumps([rec("t-k-1", "色づき始め", "2026-10-31")], ensure_ascii=False), encoding="utf-8")
        import os
        old = os.environ.get("IKIMONOBIYORI_DATA_DIR")
        os.environ["IKIMONOBIYORI_DATA_DIR"] = self.tmp.name
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = O.main(["record", "--batch", str(p)])
            self.assertEqual(rc, 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                O.main(["refresh", "--plan", "--subject", "autumn_leaves", "--region", "神奈川", "--date", "2026-11-02", "--now", NOW.isoformat()])
            out = json.loads(buf.getvalue())
            self.assertTrue(out["summary_pages"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                O.main(["facts", "--subject", "autumn_leaves", "--region", "神奈川", "--date", "2026-11-02", "--now", NOW.isoformat()])
            self.assertGreaterEqual(json.loads(buf.getvalue())["summary"]["candidate_count"], 3)
        finally:
            if old is None:
                os.environ.pop("IKIMONOBIYORI_DATA_DIR", None)
            else:
                os.environ["IKIMONOBIYORI_DATA_DIR"] = old


class RealSpots(unittest.TestCase):
    """実際の名所の一覧(spots.yaml)の形と、神奈川の候補の数(記録なし)。"""

    def test_spots_have_required_fields_and_unique_ids(self):
        doc = O.load_spots()
        ids = [s["id"] for s in doc["spots"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in doc["spots"]:
            self.assertIn(s["subject"], P["subjects"])
            self.assertTrue(s.get("prefecture") and s.get("city"), s["id"])
            for t in s.get("typical") or []:
                self.assertTrue(t.get("url") and t.get("source_class") in ("official", "secondary"), s["id"])
                self.assertIsNotNone(O.parse_typical(t["text"], P), (s["id"], t["text"]))

    def test_kanagawa_has_three_or_more_candidates_for_each_subject_without_records(self):
        with tempfile.TemporaryDirectory() as d:
            for subj in ("autumn_leaves", "flowers", "birds"):
                f = O.facts(subj, region="神奈川", dates=D, now=NOW, env={"IKIMONOBIYORI_DATA_DIR": d}, with_alternatives=False)
                self.assertGreaterEqual(len(f["candidates"]) + len(f["avoid"]), 3, subj)


if __name__ == "__main__":
    unittest.main()
