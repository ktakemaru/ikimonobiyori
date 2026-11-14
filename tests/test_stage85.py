"""段階85: 現況の自動の読み直し・出典を短く・取りこぼしの点検・フックの直し。合成データ(通信しない)。"""
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import auto_refresh as AU
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import observations as O

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 15, 9, 0, tzinfo=JST)
URL = "https://www.nagatoro.gr.jp/category/%E7%B4%85%E8%91%89%E6%83%85%E5%A0%B1/"


def _rec(state, text="11/9現在"):
    return {"subject": "autumn_leaves", "name": "試験の渓谷", "city": "長瀞町", "prefecture": "埼玉県", "state": state,
            "state_date": "2026-11-09", "state_date_text": text, "url": URL, "publisher": "長瀞町観光協会",
            "source_class": "official", "basis": "page"}


class FakeGet:
    def __init__(self, body, robots="User-agent: *\nDisallow: /wp-admin/\n", status=200):
        self.body, self.robots, self.status, self.urls = body, robots, status, []

    def __call__(self, url):
        self.urls.append(url)
        if url.endswith("/robots.txt"):
            return 200, self.robots.encode("utf-8"), {}
        return self.status, self.body.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}


def _target():
    return {"url": URL, "name": "試験の渓谷", "subject": "autumn_leaves", "kind": "status", "publisher": "長瀞町観光協会",
            "current_date": "2026-11-09"}


class Unchanged(unittest.TestCase):
    def test_same_text_is_unchanged(self):
        recs = [_rec("見頃迎え始め", "２０２６年１１月９日現在")]
        self.assertTrue(AU.unchanged("<p>2026年11月9日 現在</p> 試験の渓谷 見頃 迎え始め", recs))
        self.assertFalse(AU.unchanged("2026年11月14日現在 試験の渓谷 見頃", recs))
        self.assertFalse(AU.unchanged("なにか", []))                  # 記録がなければ分からない(変わったとみなす)


class Run(unittest.TestCase):
    def setUp(self):
        O.record([_rec("見頃迎え始め")], now=NOW - timedelta(days=4))

    def test_unchanged_page_updates_last_confirmed(self):
        g = FakeGet("<html><body>11/9現在 試験の渓谷 見頃迎え始め</body></html>")
        res = AU.run([_target()], now=NOW, http_get=g, sleep=lambda s: None)
        self.assertEqual(res["pages"][0]["result"], "unchanged")
        self.assertEqual(g.urls[0], "https://www.nagatoro.gr.jp/robots.txt")      # robots.txt を先に読む
        conf = O.read_confirmed("autumn_leaves")
        self.assertTrue(any(v.get("last_confirmed_at", "").startswith("2026-11-15") for v in conf.values()))
        self.assertEqual(len([r for r in O.read_records("autumn_leaves") if r.get("url") == URL]), 1)   # 新しい記録は作らない

    def test_changed_page_keeps_text_for_agent(self):
        g = FakeGet("<html><body>11/14現在 試験の渓谷 見頃</body></html>")
        res = AU.run([_target()], now=NOW, http_get=g, sleep=lambda s: None)
        p = res["pages"][0]
        self.assertEqual(p["result"], "changed")
        from pathlib import Path
        self.assertIn("11/14現在", Path(p["text_path"]).read_text(encoding="utf-8"))
        doc = GB.attach_refresh({"missing": [], "id": "b1"}, res)
        self.assertEqual(doc["missing"], [])

    def test_robots_refusal_and_http_error_are_failed(self):
        res = AU.run([_target()], now=NOW, http_get=FakeGet("x", robots="User-agent: *\nDisallow: /category/\n"), sleep=lambda s: None)
        self.assertEqual(res["pages"][0]["result"], "failed")
        res = AU.run([_target()], now=NOW, http_get=FakeGet("x", status=503), sleep=lambda s: None)
        self.assertEqual(res["pages"][0]["result"], "failed")

    def test_offline_keeps_old_records_and_says_so(self):
        res = AU.run([_target()], now=NOW)                    # テスト中は通信しない(http_get なし)= オフラインと同じ扱い
        self.assertEqual(res["pages"][0]["result"], "failed")
        doc = GB.attach_refresh({"missing": ["前からある行"]}, res)
        self.assertEqual(len(doc["missing"]), 2)
        self.assertIn("読み直せませんでした(11/9時点の記録のまま)", doc["missing"][1])

    def test_limits_pages(self):
        mx = GB.cfg()["auto_refresh"]["max_pages"]["value"]
        ts = [dict(_target(), url=f"https://www.nagatoro.gr.jp/p{i}/") for i in range(mx + 2)]
        res = AU.run(ts, now=NOW, http_get=FakeGet("x"), sleep=lambda s: None)
        self.assertEqual(sum(1 for p in res["pages"] if p["result"] == "skipped"), 2)

    def test_time_limit(self):
        t = [0.0]

        def clock():
            t[0] += 30.0                                   # 1 回ごとに 30 秒進む時計: 2 ページ目は読まない
            return t[0]
        ts = [_target(), dict(_target(), url="https://www.nagatoro.gr.jp/p2/")]
        res = AU.run(ts, now=NOW, http_get=FakeGet("x"), clock=clock, sleep=lambda s: None)
        self.assertEqual(res["pages"][-1]["result"], "skipped")


class StaleMark(unittest.TestCase):
    def test_mark_seven_days(self):
        rows = [{"kind": "current", "observed": "2026-11-08"}, {"kind": "current", "observed": "2026-11-10"}, {"kind": "typical"}]
        GB._mark_stale(rows, {"periods": [["2026-11-15"]]}, NOW, GB.cfg())
        self.assertEqual(rows[0]["fields"]["stale_days"], 7)
        self.assertNotIn("fields", rows[1])

    def test_build_offline_still_makes_brief(self):
        doc = GB.build_refreshed("今週末の紅葉の情報は?", now=NOW)      # テスト中は通信しないが資料はできる
        self.assertTrue(doc["id"])


if __name__ == "__main__":
    unittest.main()


class HookPageReply(unittest.TestCase):
    """段階85 第4部 1: 2026-11-15 に止められた形(ask verify と ask page を 1 回のコマンドで実行・ページのあとで verify をやり直し)。"""
    REPLY = "「今週末の冬鳥のおすすめ」の写真つきページです。答えの内容と写真を、このページにまとめています。\nhttps://claude.ai/artifact/abc"

    def turn(self, extra_verify=False):
        calls = [{"name": "Bash", "input": {"command": 'python -X utf8 -m ikimonobiyori.ask brief "今週末、冬鳥を見に行きたい" --prev b1'}},
                 {"name": "Bash", "input": {"command": "python -X utf8 -m ikimonobiyori.ask verify d7.txt --brief b2 > f7.txt; "
                                                       "python -X utf8 -m ikimonobiyori.ask page"}},
                 {"name": "Artifact", "input": {"file_path": "x.html"}},
                 {"name": "Bash", "input": {"command": "python -X utf8 -m ikimonobiyori.ask page-reply --url https://claude.ai/artifact/abc"}}]
        if extra_verify:
            calls.append({"name": "Bash", "input": {"command": "python -X utf8 -m ikimonobiyori.ask verify d7.txt --brief b2 > f7.txt"}})
        return {"prompt": "今週末、冬鳥を見に行きたい。artifactにして", "calls": calls}

    def decide(self, msg, turn):
        from ikimonobiyori import stop_hook as SH
        from ikimonobiyori.guide_answer_page import loose
        return SH.decide({"last_assistant_message": msg}, turn, guide_ok=lambda m: False, page_ok=lambda m: loose(m) == loose(self.REPLY))

    def test_same_call_verify_then_page_passes(self):
        self.assertFalse(self.decide(self.REPLY, self.turn())["block"])

    def test_verify_rerun_after_page_passes(self):
        self.assertFalse(self.decide(self.REPLY, self.turn(extra_verify=True))["block"])

    def test_link_symbols_ignored(self):
        msg = self.REPLY.replace("\nhttps://claude.ai/artifact/abc", "\n- <https://claude.ai/artifact/abc>")
        self.assertFalse(self.decide(msg, self.turn())["block"])

    def test_other_text_still_blocked(self):
        self.assertTrue(self.decide("ページを作りました。\nhttps://claude.ai/artifact/abc", self.turn())["block"])

    def test_page_before_verify_in_same_call_is_not_after(self):
        from ikimonobiyori import stop_hook as SH
        t = self.turn()
        t["calls"][1]["input"]["command"] = "python -X utf8 -m ikimonobiyori.ask page; python -X utf8 -m ikimonobiyori.ask verify d7.txt --brief b2"
        self.assertTrue(self.decide(self.REPLY, t)["block"])
        self.assertTrue(SH._after(t["calls"], 1, 2, SH.cfg()))
