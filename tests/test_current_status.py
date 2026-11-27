"""今年の現況を場所ごと・出どころごとに並べる(指示書 docs/current-status-instructions.md。2026-11-28)。通信しない。
記録はすべて作り物(出どころの名前に「作り物」・ホストは example)。一時のデータ置き場にだけ書く。"""
import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import current_status as CS
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import observations as O

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
Q = "今週末、筑波山で紅葉を見たい"
HOSTS = ["tsukuba-a.example.jp", "tsukuba-b.example.jp"]
A, B = "https://tsukuba-a.example.jp/koyo", "https://tsukuba-b.example.jp/koyo"
RECS = [
    {"subject": "autumn_leaves", "name": "筑波山", "part": "山頂", "state": "終了", "state_date": "2026-11-20", "url": A,
     "publisher": "試験の発信元A(作り物)", "source_class": "official", "basis": "page"},
    {"subject": "autumn_leaves", "name": "筑波山", "part": "山頂", "state": "見ごろ", "state_date": "2026-11-22", "url": B,
     "publisher": "試験の発信元B(作り物)", "source_class": "official", "basis": "page"},
    {"subject": "autumn_leaves", "name": "筑波山", "part": "中腹", "state": "見頃", "state_date": "2026-11-20", "url": A,
     "publisher": "試験の発信元A(作り物)", "source_class": "official", "basis": "page"},
    {"subject": "autumn_leaves", "name": "筑波山", "state": "今見頃", "state_date": "2026-11-22", "url": "https://koyo-test.example.com/tsukuba",
     "publisher": "試験の紹介サイト(作り物)", "source_class": "secondary", "basis": "page"},
    {"subject": "autumn_leaves", "name": "筑波山", "part": "山頂", "state": "紅葉と言える所は無い", "state_date": "2026-11-26",
     "source_class": "user", "unseen": ["筑波山神社"]},
    {"subject": "autumn_leaves", "name": "筑波山", "part": "中腹", "state": "少し残る程度", "state_date": "2026-11-26", "source_class": "user"},
]
FOOT = "\n[場所]\n記録: 筑波山\n知識: なし\n"

_ORIG = GB.cfg


def _on():
    c = copy.deepcopy(_ORIG())
    c["official_hosts"] = list(c.get("official_hosts") or []) + HOSTS
    return c


def _off():
    c = _on()
    c["current_status"]["enabled"] = False
    return c


class CurrentStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-current-status-")
        cls.empty = tempfile.TemporaryDirectory(prefix="ikimono-current-status-empty-")
        GB._HOSTS = None
        with mock.patch.object(GB, "cfg", _on):
            with mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.empty.name}):
                cls.bare = GB.build(Q, now=NOW)
            cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
            cls.env.start()
            cls.rec = O.record(RECS, now=NOW - timedelta(hours=1))
            cls.doc = GB.build(Q, now=NOW)
            GB.save(cls.doc)
            cls.md = GB.render_md(cls.doc)
        with mock.patch.object(GB, "cfg", _off):
            cls.off = GB.build(Q, now=NOW)
        cls.ids = {(r["part"], r["state"]): r["fact"] for r in cls.doc["current_status"]["places"][0]["current_parts"]}
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()
        cls.empty.cleanup()

    def check(self, text, doc=None):
        with mock.patch.object(GB, "cfg", _on):
            return GV.check(text + FOOT, doc or self.doc)

    def codes(self, text, doc=None):
        return {e["code"] for e in self.check(text, doc)["errors"]}

    def f(self, part, state):
        return self.ids[(part, state)]

    # ---- 記録(第 2・3 部) ----
    def test_records_written(self):
        self.assertEqual((self.rec["written"], self.rec["rejected"]), (len(RECS), []))

    def test_record_checks(self):
        pol = O.load_policy()
        base = {"subject": "autumn_leaves", "name": "筑波山", "state": "見頃", "state_date": "2026-11-20", "url": A, "source_class": "official"}
        self.assertEqual(O.validate(base, pol), [])
        self.assertTrue(O.validate({**base, "part": "あ" * 31}, pol))                         # part は 30 字まで
        self.assertTrue(O.validate({**base, "unseen": ["神社"]}, pol))                         # unseen は利用者の記録だけ
        user = {"subject": "autumn_leaves", "name": "筑波山", "state": "少し残る程度", "state_date": "2026-11-26", "source_class": "user"}
        self.assertEqual(O.validate(user, pol), [])                                            # URL は求めない
        self.assertTrue(O.validate({**user, "state_date": None}, pol))                         # 確認した日が要る
        self.assertTrue(O.validate({**user, "state": "あ" * 81}, pol))                         # 80 字まで(切り詰めない)
        self.assertTrue(O.validate({**base, "source_class": "other"}, pol))

    def test_same_state_other_part_is_another_record(self):
        rows = O.read_records("autumn_leaves", include_detail=True)
        self.assertEqual(len([r for r in rows if r.get("name") == "筑波山"]), len(RECS))   # 山頂と中腹の記録が 1 つにまとまらない

    def test_detail_records_not_used_for_ranking(self):
        names = [r.get("part") or r.get("source_class") for r in O.read_records("autumn_leaves") if r.get("name") == "筑波山"]
        self.assertEqual(names, ["secondary"])                                                 # 既定では part・利用者の記録を外す
        self.assertEqual(self.doc["candidates"], self.bare["candidates"])                     # 候補と順番・点数は記録が無いときと同じ
        self.assertEqual(self.doc["fallback"], self.bare["fallback"])
        self.assertEqual(self.doc["rules"], self.bare["rules"])

    # ---- 資料(第 2〜5 部) ----
    def test_current_parts(self):
        p = self.doc["current_status"]["places"][0]
        self.assertEqual(p["name"], "筑波山")
        self.assertEqual(len(p["current_parts"]), len(RECS))
        dates = [r["state_date"] for r in p["current_parts"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        facts = {f["id"]: f for f in self.doc["facts"]}
        for r in p["current_parts"]:
            self.assertEqual(facts[r["fact"]]["kind"], "current")
            self.assertEqual(facts[r["fact"]]["source_class"], r["source_class"])

    def test_user_fact_phrase(self):
        f = next(x for x in self.doc["facts"] if x["id"] == self.f("山頂", "紅葉と言える所は無い"))
        self.assertEqual(f["source_class"], "user")
        self.assertIn("11月26日に現地で確認した記録では", f["content"])
        self.assertIn("(公式の発表ではありません)", f["content"])
        self.assertIsNone(f["url"])

    def test_unseen_and_spread(self):
        p = self.doc["current_status"]["places"][0]
        self.assertEqual([u["words"] for u in p["unseen"]], ["筑波山神社"])
        sp = {g["part"]: g for g in p["spread"]}
        self.assertEqual(set(sp), {"山頂"})                                                    # 中腹は「見頃」どうしで、ばらつきではない
        self.assertEqual(set(sp["山頂"]["facts"]), {self.f("山頂", "終了"), self.f("山頂", "見ごろ"), self.f(None, "今見頃")})
        self.assertTrue(sp["山頂"]["whole_vs_part"])
        self.assertEqual(self.doc["current_status"]["spread_line"], "発信元によって、状況の伝え方にばらつきがあります。")

    def test_markdown(self):
        for s in ("## 聞かれた名所の今年の現況(場所ごと・出どころごと)", "確認していない: 筑波山神社", "ばらつき(山頂)",
                  "発信元によって、状況の伝え方にばらつきがあります。", "11月26日に現地で確認した記録では、筑波山の山頂は",
                  "筑波山(名所全体としての表示): 今見頃"):
            self.assertIn(s, self.md, s)
        self.assertLess(self.md.index("## 聞かれた名所の今年の現況"), self.md.index("## 候補と順位"))

    def test_research_target(self):
        t = [x for x in self.doc["research"]["targets"] if x.get("kind") == "current_status"]
        self.assertEqual([x["where"] for x in t], ["筑波山"])                                    # 利用者の記録だけでは「新しい」に数えない
        self.assertEqual(t[0]["search_words"], "筑波山 紅葉 2026")
        self.assertIn("ask research searched --brief " + self.doc["id"], self.md)

    def test_off_is_like_main(self):
        self.assertNotIn("current_status", self.off)
        self.assertFalse([x for x in self.off["research"]["targets"] if x.get("kind") == "current_status"])
        self.assertEqual(self.off["candidates"], self.doc["candidates"])
        with mock.patch.object(GB, "cfg", _off):
            r = GV.check("筑波山は終了です。[F001]" + FOOT, self.off)
        self.assertFalse({"part_widened", "spread_hidden", "current_research_skipped"} & {e["code"] for e in r["errors"]})

    # ---- 照合(第 2・3・5・6 部) ----
    def draft_ok(self):
        f = self.f
        return (f"筑波山の山頂は、発信元によって、状況の伝え方にばらつきがあります。\n"
                f"11月26日に現地で確認した記録では、山頂は「紅葉と言える所は無い」でした(公式の発表ではありません)。[{f('山頂', '紅葉と言える所は無い')}]\n"
                f"山頂は、試験の発信元Bでは11/22時点で見ごろ[{f('山頂', '見ごろ')}]、試験の発信元Aでは11/20時点で終了[{f('山頂', '終了')}]と出ていて、"
                f"紹介サイトでは筑波山全体として11/22時点で今見頃[{f(None, '今見頃')}]とされています。\n"
                f"11月26日に現地で確認した記録では、中腹は「少し残る程度」でした(公式の発表ではありません)。[{f('中腹', '少し残る程度')}]\n"
                "筑波山神社の周辺は確認していません。\n")

    def test_verify(self):
        f = self.f
        self.assertIn("current_research_skipped", self.codes(self.draft_ok()))                 # 調べる対象があるのに調べた印が無い
        CS.note_searched(self.doc["id"], "筑波山", found=False, reason="作り物の試験", now=NOW)
        r = self.check(self.draft_ok())
        self.assertTrue(r["ok"], r["errors"])
        self.assertIn("part_widened", self.codes(f"筑波山は終了です。[{f('山頂', '終了')}]\n"))
        self.assertIn("spread_hidden", self.codes(f"山頂は見ごろです。[{f('山頂', '見ごろ')}]\n"))
        self.assertIn("unseen_place_state", self.codes(
            f"11月26日に現地で確認した記録では、山頂と同じく筑波山神社も紅葉は無いそうです(公式の発表ではありません)。[{f('山頂', '紅葉と言える所は無い')}]\n"))
        self.assertIn("user_record_unlabeled", self.codes(f"山頂は紅葉と言える所は無いそうです。[{f('山頂', '紅葉と言える所は無い')}]\n"))
        again = GB.build(Q, now=NOW)                                                           # 調べた印のあとの資料には「調べる」が出ない
        self.assertFalse([x for x in again["research"]["targets"] if x.get("kind") == "current_status"])
        self.assertIn("新しい情報は見つからなかった", GB.render_md(again))

    def test_schema(self):
        import json
        from jsonschema import Draft202012Validator
        schema = json.loads((H.ROOT / "ikimonobiyori" / "schemas" / "guide-brief.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([e.message[:120] for e in Draft202012Validator(schema).iter_errors(self.doc)], [])

    def test_switches(self):
        def with_off(part):
            def f():
                c = _on()
                c["current_status"][part]["enabled"] = False
                return c
            return f
        with mock.patch.object(GB, "cfg", with_off("research")):
            d = GB.build(Q, now=NOW)
        self.assertFalse([x for x in d["research"]["targets"] if x.get("kind") == "current_status"])
        with mock.patch.object(GB, "cfg", with_off("spread")):
            d = GB.build(Q, now=NOW)
        self.assertEqual(d["current_status"]["places"][0]["spread"], [])
        self.assertIsNone(d["current_status"]["spread_line"])
        doc = copy.deepcopy(self.doc)
        doc["id"] = "b-test-steps"
        with mock.patch.object(GB, "cfg", with_off("steps")):
            r = GV.check(self.draft_ok() + FOOT, doc)
        self.assertNotIn("current_research_skipped", {e["code"] for e in r["errors"]})

    def test_refresh_not_recorded(self):
        doc = copy.deepcopy(self.doc)
        doc["id"] = "b-test-refresh"
        doc["research"] = {"targets": []}
        doc["auto_refresh"] = {"pages": [{"name": "筑波山(筑波山神社・宮脇駅周辺)", "url": "https://refresh-test.example.jp/", "result": "changed"}]}
        self.assertIn("refresh_not_recorded", self.codes(self.draft_ok(), doc))
        doc["auto_refresh"]["pages"][0]["result"] = "unchanged"
        self.assertNotIn("refresh_not_recorded", self.codes(self.draft_ok(), doc))


class OtherRecords(unittest.TestCase):
    """part の無い利用者の記録と、同じ発信元の古い発信・新しい発信(作り物)。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ikimono-current-status-2-")
        self.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        self.env.start()
        GB._HOSTS = None

    def tearDown(self):
        self.env.stop()
        GB._HOSTS = None
        self.tmp.cleanup()

    def test_user_record_without_part(self):
        rec = {"subject": "autumn_leaves", "name": "筑波山", "state": "紅葉は少し", "state_date": "2026-11-26", "source_class": "user"}
        res = O.record([rec], now=NOW)
        self.assertEqual((res["written"], res["rejected"]), (1, []))
        self.assertEqual(O.record([rec], now=NOW)["duplicates"], 1)
        err = O.validate({**rec, "source_class": "official"}, O.load_policy())
        self.assertTrue(any("source_class: user" in e for e in err), err)      # URL の無い記録に、利用者の記録の入口を案内する

    def test_same_publisher_is_not_spread(self):
        base = {"subject": "autumn_leaves", "name": "筑波山", "part": "山頂", "url": A, "publisher": "試験の発信元A(作り物)",
                "source_class": "official", "basis": "page"}
        O.record([{**base, "state": "色づき始め", "state_date": "2026-11-14"}, {**base, "state": "見頃", "state_date": "2026-11-22"}],
                 now=NOW - timedelta(hours=1))
        with mock.patch.object(GB, "cfg", _on):
            d = GB.build(Q, now=NOW)
        p = d["current_status"]["places"][0]
        self.assertEqual(p["spread"], [])                                          # 同じ発信元の更新は、ばらつきではない
        self.assertEqual([r["state"] for r in p["current_parts"]], ["見頃"])        # 新しい発信だけを並べる
        self.assertEqual(p["current_parts"][0]["source_class"], "official")


if __name__ == "__main__":
    unittest.main()
