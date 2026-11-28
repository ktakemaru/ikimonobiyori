"""開いた質問の手元の現況: 少し前の様子(15〜30 日前の公式の記録。続き 第4部)と、行事の終了だけの記録を入れない(続き 第6部)。
指示書 open-question-breadth の続き(本人の返事 6・9、2026-11-28)。通信しない。記録はすべて作り物。一時のデータ置き場にだけ書く。"""
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
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=JST)
Q = "桜が見られるところはある?"
HOST = "sakura-test.example.jp"
URL = f"https://{HOST}/news"


def r(name, state, d, **kw):
    return {"subject": "flowers", "name": name, "prefecture": "埼玉県", "city": "神川町", "kind": "冬桜", "state": state, "state_date": d,
            "url": f"{URL}/{abs(hash(name)) % 1000}", "publisher": "試験の観光協会(作り物)", "source_class": "official", **kw}


RECS = [
    r("試験の冬桜の丘(作り物)", "冬桜が見頃", "2026-11-12"),                    # 16 日前 → 少し前の様子
    r("試験の古い桜の園(作り物)", "冬桜が見頃", "2026-10-20"),                  # 39 日前 → 出さない
    r("試験の両方の公園(作り物)", "冬桜が咲き始め", "2026-11-10"),              # 同じ場所に 14 日以内の記録がある → 少し前は出さない
    r("試験の両方の公園(作り物)", "冬桜が見頃", "2026-11-25"),
    r("試験の花の国(作り物)", "さくらまつり終了について", "2026-11-26"),        # 行事の終了だけ → 手元の現況の節に入れない
    r("試験の祭りの庭(作り物)", "さくらまつり開催中、冬桜は見頃", "2026-11-26"),  # 行事の語と状態の語 → 入れる
]

_ORIG = GB.cfg


def _on():
    c = copy.deepcopy(_ORIG())
    c["official_hosts"] = list(c.get("official_hosts") or []) + [HOST]
    return c


class Earlier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-open-earlier-")
        GB._HOSTS = None
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        with mock.patch.object(GB, "cfg", _on):
            res = O.record(RECS, now=NOW - timedelta(hours=1))
            assert res["written"] == len(RECS), res
            cls.doc = GB.build(Q, now=NOW)
            cls.md = GB.render_md(cls.doc)
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def ob(self):
        return self.doc["current_status"]["open"]

    def test_config(self):
        self.assertEqual(CS._v(CS.open_cfg()["recent_days"]), 14)
        self.assertEqual(CS._v(CS.open_cfg()["earlier_days"]), 30)

    def test_earlier_section(self):
        names = [k["name"] for k in self.ob()["earlier"]]
        self.assertEqual(names, ["試験の冬桜の丘(作り物)"])
        known = [k["name"] for k in self.ob()["known"]]
        self.assertNotIn("試験の冬桜の丘(作り物)", known)
        self.assertIn("試験の両方の公園(作り物)", known)
        self.assertIn("## 少し前の様子", self.md)
        self.assertLess(self.md.index("## 聞かれた対象の今年の現況"), self.md.index("## 少し前の様子"))
        fx = {f["id"]: f for f in self.doc["facts"]}
        f = fx[self.ob()["earlier"][0]["fact"]]
        self.assertIn("その後の様子は確かめられていない", f["content"])
        cand = [c for c in self.doc["candidates"] if c["name"] == "試験の冬桜の丘(作り物)"]
        self.assertTrue(all(c.get("basis") != "current" for c in cand))            # 少し前の様子で候補の今年の現況にしない

    def test_verify_stops_earlier_as_now(self):
        fid = self.ob()["earlier"][0]["fact"]
        err = lambda code, s, detail, fix: {"code": code}
        bad = [{"clean": "試験の冬桜の丘では冬桜が見頃です。", "ids": [fid]}]
        good = [{"clean": "試験の冬桜の丘は11月12日時点では見頃でした。", "ids": [fid]}, {"clean": "その後の様子は確かめられていません。", "ids": []}]
        self.assertEqual([e["code"] for e in CS.earlier_errors(bad, self.doc, None, err)], ["earlier_as_now"])
        self.assertEqual(CS.earlier_errors(good, self.doc, None, err), [])


if __name__ == "__main__":
    unittest.main()
