"""公式ページに載った発行元自身の投稿(指示書 open-question-breadth の続き 第3部。本人の返事 4、2026-11-28)。通信しない。
投稿の文はすべて作り物(リポジトリに本物の SNS の文を入れない)。一時のデータ置き場にだけ書く。"""
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
HOST = "post-test.example.jp"
URL = f"https://{HOST}/koyo/"
POST = "試験の山の紅葉の様子です。まだ見頃ですが落ち葉が目立つようになってきました。作り物の文です。"


def rec(**kw):
    base = {"subject": "autumn_leaves", "name": "試験の山の寺(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "モミジ",
            "state": "まだ見頃、落葉が目立つ", "state_date": "2026-11-27", "url": URL, "publisher": "試験の観光協会(作り物)", "source_class": "official",
            "embedded_post": {"own_account": True, "own_account_basis": "公式サイトのフッターの「Instagram でフォロー」がこのアカウント(作り物)", "account": "test_kanko", "posted_on": "2026-11-27", "posted_on_inferred": True, "text": POST}}
    base.update(kw)
    return base


_ORIG = GB.cfg


def _on():
    c = copy.deepcopy(_ORIG())
    c["official_hosts"] = list(c.get("official_hosts") or []) + [HOST]
    return c


class Validate(unittest.TestCase):
    def test_conditions(self):
        pol = O.load_policy()
        self.assertEqual(O.validate(rec(), pol), [])
        bad = [rec(embedded_post={**rec()["embedded_post"], "own_account": False}),              # ほかの人の投稿
               rec(embedded_post={**rec()["embedded_post"], "posted_on": "11/27"}),               # 年まで決まらない
               rec(embedded_post={**rec()["embedded_post"], "text": ""}),                         # 写しが無い
               rec(embedded_post={**rec()["embedded_post"], "account": ""}),
               rec(embedded_post={**rec()["embedded_post"], "own_account_basis": ""}),            # 公式サイトの案内が無い
               rec(source_class="secondary"),
               rec(state_date="2026-11-26"),                                                      # 状態の日付は投稿の日付
               rec(url="https://www.instagram.com/p/xyz/"),                                       # SNS のサイトそのもの
               rec(embedded_post="投稿")]
        for r in bad:
            self.assertTrue(O.validate(r, pol), r)

    def test_record_keeps_copy(self):
        with tempfile.TemporaryDirectory(prefix="ikimono-post-") as d, mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": d}):
            res = O.record([rec()], now=NOW)
            self.assertEqual(res["written"], 1, res)
            got = [r for r in O.read_records("autumn_leaves", None, O.load_policy(), include_detail=True) if r.get("url") == URL]
            self.assertEqual(got[0]["embedded_post"]["text"], POST)


class BriefAndVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ikimono-post-brief-")
        GB._HOSTS = None
        cls.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": cls.tmp.name})
        cls.env.start()
        with mock.patch.object(GB, "cfg", _on):
            O.record([rec()], now=NOW - timedelta(hours=1))
            cls.doc = GB.build("横浜から行ける場所で紅葉情報を教えて", now=NOW)
        GB._HOSTS = None

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        GB._HOSTS = None
        cls.tmp.cleanup()

    def fact(self):
        return next(f for f in self.doc["facts"] if f.get("url") == URL)

    def test_fact_has_mark(self):
        self.assertIn("公式ページに載った発行元の投稿、投稿日 11/27", self.fact()["content"])

    def test_quote_is_stopped_and_own_words_pass(self):
        fid = self.fact()["id"]
        err = lambda code, s, detail, fix: {"code": code}
        long = f"試験の山の寺は「まだ見頃ですが落ち葉が目立つようになってきました」とのことです。[{fid}]"
        own = f"試験の山の寺は11月27日時点では見頃で、落葉が目立ち始めていました。[{fid}]"
        self.assertEqual([e["code"] for e in CS.embedded_post_quote_errors(long, self.doc, None, err)], ["embedded_post_quoted"])
        self.assertEqual(CS.embedded_post_quote_errors(own, self.doc, None, err), [])


if __name__ == "__main__":
    unittest.main()
