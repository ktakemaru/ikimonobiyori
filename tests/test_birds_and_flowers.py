"""野鳥(birds)を紅葉・冬鳥と同じ型に(段階17 フェーズ3)と、花(flowers。フェーズ4)。通信なし。
話題 → 対象、未実装の対象の答え方、iNaturalist の利用条件の状態、干潟の潮位表の案内。"""
import re
import unittest

import helpers as H  # noqa: F401  (通信禁止)
from helpers import ROOT

from ikimonobiyori import answer, catalog, sources

import test_answer as TA

POLICY = sources.load_policy()


class Birds(unittest.TestCase):
    def test_birds_is_answerable_with_the_same_machinery(self):
        got = {s["subject"]: s for s in sources.subjects_status()}
        self.assertTrue(got["birds"]["implemented"])
        self.assertEqual(got["birds"]["engine_status"], "implemented")          # v0 の計算の状態(手順で答えられるかとは別)
        self.assertEqual([s["label"] for s in POLICY["stages"]["birds"]["items"]], ["少ない", "増えている", "多い", "減っている"])
        self.assertEqual(sources.stage_errors(POLICY), [])
        self.assertEqual(dict((p.name, e) for p, e in sources.check_all())["birds.yaml"], [])

    def test_no_count_thresholds_and_coarse_locations(self):
        reg = sources.load_registry("birds")
        for s in reg["sources"]:
            self.assertFalse(any(re.search(r"\d", k) for k in ((s.get("notation") or {}).get("map") or {})), s["id"])   # 種数・羽数から段階を決めない
        r = sources.make_record(registry=reg, policy=POLICY, source_id="tokyo-port-birdpark-today", site="yacho-0001", label="今日の野鳥公園",
                                read_at="2026-10-24T14:45:00+09:00", state="30種", observed="2026-10-22")
        self.assertEqual((r["stage"], r["freshness_basis"], sources.validate_record(r, registry=reg, policy=POLICY)), (None, "observed_date", []))
        entries = catalog.approved_entries(catalog.load_catalog("birds"))
        self.assertGreaterEqual(len(entries), 5)
        for e in entries:
            self.assertEqual(e["location_precision"], "area_10km", e["id"])
            self.assertLessEqual(catalog.decimals(e["point"]["lat"]), 1)
            self.assertTrue(e.get("status_sources"), e["id"])                    # 公式の観察情報があるものだけ

    def test_tidal_flats_point_to_the_tide_table(self):
        for e in catalog.approved_entries(catalog.load_catalog("birds")):
            if "coast" in e["tags"].get("terrain", []):
                self.assertIn("tide_table", [u["kind"] for u in e.get("related_urls") or []], e["id"])
        hosts = {u["url"].split("/")[2] for e in catalog.approved_entries(catalog.load_catalog("birds")) for u in e.get("related_urls") or []}
        self.assertEqual(hosts, {"www.data.jma.go.jp"})
        from ikimonobiyori.config import load_config
        allowed = {h for v in load_config()["live"]["allowed_hosts_by_subject"].values() for h in v}
        self.assertNotIn("www.data.jma.go.jp", allowed)                          # 潮位表のホストを許可に足さない

    def test_the_answer_mentions_the_tide_table(self):
        cat = {**TA.CAT, "entries": [{**TA.CAT["entries"][0], "related_urls": [{"kind": "tide_table", "url": "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php"}]}]
               + TA.CAT["entries"][1:]}
        parts = TA.parts()
        parts[0]["catalog"] = cat
        t = answer.compose(parts, now=TA.NOW, dates=TA.DATES, policy=POLICY)
        self.assertIn(f"試験の渓谷: {POLICY['answer']['tide_note']}", t)


class Topics(unittest.TestCase):
    def test_birds_in_general_use_both_subjects(self):
        self.assertEqual(sources.topic_subjects("野鳥", POLICY), ["birds", "wintering_birds"])
        self.assertIsNone(sources.topic_subjects("恐竜", POLICY))                 # ないものは推測しない
        ready = {s["subject"] for s in sources.subjects_status() if s["implemented"]}
        for word, subs in POLICY["topics"]["items"].items():
            self.assertTrue(set(subs) <= ready, word)

    def test_unimplemented_subjects_get_a_short_answer_without_unrelated_subjects(self):
        st = {s["subject"]: s for s in sources.subjects_status()}
        ready_names = {s["name"] for s in st.values() if s["implemented"]}
        for sid, s in st.items():
            if s["implemented"]:
                self.assertNotIn("unimplemented_answer", s)
                continue
            text = s["unimplemented_answer"]
            self.assertLessEqual(text.count("。"), 3, sid)                        # 1〜2 文(近い対象の 1 文を足しても 3 文まで)
            rel = POLICY["unimplemented"]["related"].get(sid)
            others = ready_names - ({st[rel]["name"]} if rel in st and st[rel]["implemented"] else set())
            self.assertFalse([n for n in others if n in text], (sid, text))      # 関係のない実装済みの対象を並べない
            self.assertEqual(answer.forbidden_found(text, POLICY), [])


class DataTerms(unittest.TestCase):
    def test_inaturalist_is_user_confirmed(self):
        self.assertEqual((POLICY["data_terms"]["inaturalist"]["status"], POLICY["data_terms"]["inaturalist"]["checked_on"]), ("user_confirmed", "2026-10-21"))
        ds = (ROOT / "docs" / "data-sources.md").read_text(encoding="utf-8")
        self.assertIn("ユーザー確認済み(2026-10-21)", ds)
        for f in ("CLAUDE.md", "AGENTS.md"):
            s = (ROOT / f).read_text(encoding="utf-8")
            self.assertNotIn("人の目で確認するまで未確認", s, f)
            self.assertIn("ユーザー確認済み(2026-10-21", s, f)
            self.assertIn("野鳥の実通信は増やさない", s, f)                        # 実通信の制限は変えない


if __name__ == "__main__":
    unittest.main()
