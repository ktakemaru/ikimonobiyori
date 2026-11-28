"""見つけた公式ページを覚えて、広く探すときに最初に読む(指示書 open-question-breadth の続き 第1部。2026-11-28)。通信しない。
行はすべて作り物(発行元の名前に「作り物」・ホストは example)。一時のデータ置き場にだけ書く。"""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import observations as O
from ikimonobiyori import pending_sources as PS
from ikimonobiyori import research as RS

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 9, 0, tzinfo=JST)


def item(**kw):
    base = {"publisher": "試験の公園の指定管理者(作り物)", "publisher_kind": "指定管理者", "official_reason": "フッターの著作権表示が指定管理者",
            "url": "https://park-test.example.jp/flower/", "subject": "flowers", "content": "開花情報(サザンカ・ツバキ)", "kinds": ["サザンカ", "ツバキ"],
            "date_style": "photo", "update_style": "rewrite", "place": {"name": "試験の公園(作り物)", "prefecture": "神奈川県", "city": "横浜市",
                                                                      "lat": 35.45, "lon": 139.63},
            "question": "ツバキやサザンカが見られるところを教えて"}
    base.update(kw)
    return base


class PendingFirst(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ikimono-pending-first-")
        self.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_add_then_same_url_updates_last_read_only(self):
        r = PS.add([item()], brief="b-1", now=NOW)
        self.assertEqual((r["added"], r["updated"], r["rejected"]), (1, 0, []), r)
        later = NOW + timedelta(days=2)
        r2 = PS.add([item(content="別の内容", url="https://park-test.example.jp/flower")], brief="b-2", now=later)
        self.assertEqual((r2["added"], r2["updated"]), (0, 1), r2)
        rows = PS.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "開花情報(サザンカ・ツバキ)")       # ほかの項目は変えない
        self.assertEqual(rows[0]["found_at"], NOW.isoformat())
        self.assertEqual(rows[0]["last_read_at"], later.isoformat())
        self.assertEqual(rows[0]["approval"], "pending")
        self.assertTrue(rows[0]["id"].startswith("ps-"))

    def test_existing_old_rows_are_kept(self):
        p = PS.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        old = {"url": "https://old-test.example.jp/hotaru/", "publisher": "試験の観光協会(作り物)", "name": "試験のホタルの里", "kind": "ゲンジボタル",
               "found_at": "2026-11-11T06:28:49+09:00", "brief": "b-old", "approval": "pending"}
        p.write_text(json.dumps(old, ensure_ascii=False) + "\n", encoding="utf-8")
        PS.add([item()], now=NOW)
        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0]), old)                                # 今ある行は変えない
        self.assertEqual(len(lines), 2)
        self.assertEqual(PS.pick(["flowers"], origin="横浜"), [x for x in PS.pick(["flowers"], origin="横浜") if x["name"] != "試験のホタルの里"])

    def test_rejects(self):
        cases = [item(publisher_kind="紹介サイト"), item(official_reason=""), item(url="https://www.instagram.com/p/xyz/"),
                 item(url="https://tenki.jp/kouyou/"), item(date_style="sometimes"), item(update_style="monthly_url"),
                 item(place={"name": "試験の公園(作り物)"}), item(subject="weather")]
        for it in cases:
            r = PS.add([it], now=NOW)
            self.assertEqual(r["added"], 0, it)
            self.assertTrue(r["rejected"], it)
        self.assertEqual(PS.rows(), [])

    def test_ledger_exact_url_is_rejected_but_page_inside_range_is_not(self):
        rows = [("park-test.example.jp", "/flower/", "approved", "flowers", "test-ledger")]
        with mock.patch.object(O, "_ledger_urls", lambda: rows):
            self.assertEqual(PS.in_ledger("https://park-test.example.jp/flower"), "test-ledger")
            self.assertIsNone(PS.in_ledger("https://park-test.example.jp/flower/news/1"))
            self.assertTrue(PS.add([item()], now=NOW)["rejected"])
            self.assertEqual(PS.add([item(url="https://park-test.example.jp/flower/news/1")], now=NOW)["added"], 1)

    def test_monthly_url(self):
        it = item(url="https://blog-test.example.jp/blog/2026/11/", url_template="https://blog-test.example.jp/blog/{yyyy}/{mm}/",
                  start_url="https://blog-test.example.jp/blog/", update_style="monthly_url", date_style="article")
        self.assertEqual(PS.add([it], now=NOW)["added"], 1)
        r = PS.add([dict(it, url="https://blog-test.example.jp/blog/2026/12/")], now=NOW + timedelta(days=5))
        self.assertEqual((r["added"], r["updated"]), (0, 1))                       # 月が違っても同じページ
        self.assertEqual(PS.build_url(PS.rows()[0], date(2027, 1, 9)), "https://blog-test.example.jp/blog/2027/01/")
        self.assertTrue(PS.add([dict(it, url="https://blog-test.example.jp/other/2026/11/", url_template="https://blog-test.example.jp/x/{yyyy}/{mm}/")], now=NOW)["rejected"])
        self.assertEqual(PS.seen("https://blog-test.example.jp/blog/2027/01/", brief="b-9", now=NOW)["id"], PS.rows()[0]["id"])
        r8 = item(url="https://pref-test.example.jp/leaves/r811kouyou.html", url_template="https://pref-test.example.jp/leaves/r{ry}{mm}kouyou.html",
                  update_style="monthly_url", publisher_kind="自治体")
        self.assertEqual(PS.add([r8], now=NOW)["added"], 1)
        row = next(x for x in PS.rows() if "pref-test" in x["url"])
        self.assertEqual(PS.build_url(row, date(2027, 1, 9)), "https://pref-test.example.jp/leaves/r901kouyou.html")

    def test_pick_order_range_subject_species(self):
        PS.add([item(),
                item(url="https://far-test.example.jp/", place={"name": "遠い試験の園(作り物)", "prefecture": "北海道", "lat": 43.06, "lon": 141.35}),
                item(url="https://leaf-test.example.jp/", subject="autumn_leaves", kinds=["モミジ"]),
                item(url="https://rose-test.example.jp/", kinds=["バラ"], place={"name": "試験のばら園(作り物)", "prefecture": "東京都", "lat": 35.68, "lon": 139.76}),
                item(url="https://nocoord-test.example.jp/", kinds=[], place={"name": "座標の無い試験の園(作り物)", "prefecture": "千葉県"})], now=NOW)
        got = PS.pick(["flowers"], origin="横浜")
        names = [x["name"] for x in got]
        self.assertNotIn("遠い試験の園(作り物)", names)                           # 範囲の外
        self.assertEqual(names[0], "試験の公園(作り物)")                           # 近い順(距離の分からない行は後)
        self.assertEqual(names[-1], "座標の無い試験の園(作り物)")
        self.assertEqual(len([x for x in PS.rows() if x["subject"] == "autumn_leaves"]), 1)
        self.assertNotIn("https://leaf-test.example.jp/", [x["url"] for x in got])  # 対象が違う
        sp = [x["name"] for x in PS.pick(["flowers"], origin="横浜", species_words=["サザンカ"])]
        self.assertNotIn("試験のばら園(作り物)", sp)                              # 種が合わない行は外す(種の無い行は残す)
        self.assertIn("座標の無い試験の園(作り物)", sp)
        self.assertEqual(len(PS.pick(["flowers"], origin="横浜", limit=1)), 1)
        self.assertEqual([x["name"] for x in PS.pick(["flowers"], origin="横浜", places=["試験の公園"])], ["試験の公園(作り物)"])

    def test_max_reads_from_config(self):
        self.assertEqual(PS._v(PS.cfg()["max_reads"]), 8)
        PS.add([item(url=f"https://many{i}-test.example.jp/") for i in range(12)], now=NOW)
        t = [{"kind": "open_breadth", "where": "横浜から行ける範囲", "max_pages": 16}]
        PS.attach(t, {"subjects": ["flowers"], "origin": "横浜"}, NOW)
        self.assertEqual(len(t[0]["read_first"]), 8)
        lines = PS.step_lines("b-x", t[0])
        self.assertIn("最初に読む", lines[0])
        self.assertIn("ask research seen", lines[0])
        self.assertEqual(sum(1 for l in lines if "-test.example.jp" in l), 8)

    def test_seen_counts_reads_by_brief(self):
        PS.add([item()], now=NOW)
        pid = PS.rows()[0]["id"]
        self.assertIsNone(PS.seen("https://nothing.example.jp/", brief="b-1", now=NOW))
        PS.seen(pid, brief="b-1", now=NOW + timedelta(hours=1))
        self.assertEqual(len(PS.reads_by_brief("b-1")), 1)
        self.assertEqual(PS.rows()[0]["last_read_at"], (NOW + timedelta(hours=1)).isoformat())

    def test_brief_lists_read_first_before_search_steps(self):
        PS.add([item()], now=NOW)
        doc = GB.build("ツバキやサザンカが見られるところを教えて", now=NOW)
        tg = [t for t in doc["research"]["targets"] if t.get("kind") == "open_breadth"]
        self.assertTrue(tg, doc["research"])
        self.assertEqual([x["url"] for x in tg[0]["read_first"]], ["https://park-test.example.jp/flower/"])
        md = GB.render_md(doc)
        self.assertIn("0. 最初に読む", md)
        self.assertIn("https://park-test.example.jp/flower/", md)
        self.assertIn("ask research pending", md)                                 # 使えた公式ページを残す手順
        self.assertLess(md.index("0. 最初に読む"), md.index("1. 広く探す"))

    def test_listing_has_ids(self):
        PS.add([item()], now=NOW)
        self.assertTrue(all(x.get("id") for x in RS.listing()["pending_sources"]))


if __name__ == "__main__":
    unittest.main()
