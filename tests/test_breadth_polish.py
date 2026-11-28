"""本人の返事 2・3・4・6(2026-11-28。指示書 open-question-breadth の続きの決めてほしいことへの返事)。通信しない。
記録はすべて作り物(ホストは example)。一時のデータ置き場にだけ書く。"""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import observations as O
from ikimonobiyori import pending_sources as PS
from ikimonobiyori import season_place as SP

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=JST)
HOST = "park-polish.example.jp"

_ORIG = GB.cfg


def _on():
    c = copy.deepcopy(_ORIG())
    c["official_hosts"] = list(c.get("official_hosts") or []) + [HOST]
    return c


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ikimono-polish-")
        self.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        self.env.start()
        GB._HOSTS = None

    def tearDown(self):
        self.env.stop()
        GB._HOSTS = None
        self.tmp.cleanup()


class OffSeason(Tmp):
    def test_helper(self):
        rows = [{"start": "06-11", "end": "07-20"}, {"start": "07-11", "end": "07-31"}]
        self.assertTrue(SP.off_season(rows, [date(2026, 11, 28)]))
        self.assertFalse(SP.off_season(rows, [date(2026, 7, 1)]))
        self.assertFalse(SP.off_season([{"start": None, "end": None}], [date(2026, 11, 28)]))   # 時期が分からなければ時期の外と言わない
        self.assertFalse(SP.off_season([{"start": "11-01", "end": "02-28"}], [date(2027, 1, 5)]))  # 年をまたぐ時期

    def test_species_level_uses_all_rows_recent_and_empty(self):
        d = [date(2026, 11, 28)]
        rows = [{"name": f"冬の園{i}", "start": "02-01", "end": "03-31"} for i in range(6)] + [{"name": "今の園", "start": "11-01", "end": "12-31"}]
        self.assertFalse(SP.off_season_species({"サザンカ": rows}, d))                  # 並べる件数(先頭 6 件)で切っても、全部で見る
        self.assertTrue(SP.off_season(rows[:6], d))                                     # 切った分だけなら時期の外になってしまう
        self.assertTrue(SP.off_season_species({"サザンカ": rows[:6]}, d))
        self.assertFalse(SP.off_season_species({"サザンカ": rows[:6]}, d, recent=["サザンカ"]))   # 14 日以内の公式の現況があれば時期の外にしない
        self.assertFalse(SP.off_season_species({"サザンカ": []}, d))                    # その種の名所が 1 件も無ければ時期の外にしない
        self.assertFalse(SP.off_season_species({"ツバキ": rows[:6], "サザンカ": rows}, d))   # どれか 1 つでも時期なら時期の外にしない

    def test_catalog_growth_does_not_make_in_season_off(self):
        """今が時期の花が、カタログの名所の増減(並べる件数からあふれる)で時期の外にならない。"""
        real = SP.gather
        def more(sp, origin, c=None, env=None):
            rows = real(sp, origin, c, env)
            extra = [{**rows[0], "name": f"増えた冬の園{i}(作り物)", "start": "02-01", "end": "03-31", "km": 1, "season": "2月"} for i in range(20)] if rows else []
            return extra + rows
        q = "ツバキやサザンカが見られるところを教えて"
        base = SP.compose(q, today=date(2026, 11, 28), origin="横浜")
        self.assertFalse(SP.off_season_species(base["season_rows"], [date(2026, 11, 28)]))
        with mock.patch.object(SP, "gather", more):
            grown = SP.compose(q, today=date(2026, 11, 28), origin="横浜", max_items=3)
        self.assertFalse(SP.off_season_species(grown["season_rows"], [date(2026, 11, 28)]))
        self.assertGreater(len(grown["season_rows"]["サザンカ"]), len([r for r in grown["spots"] if "サザンカ" in (r.get("kinds") or [])]))   # 並べたのは一部

    def test_brief_off_season_no_breadth_no_weather(self):
        doc = GB.build("ニッコウキスゲはいつどこへ行けばいい?", now=NOW)
        self.assertEqual(doc["route"], "season_place")
        self.assertTrue(doc["off_season"])
        self.assertFalse([t for t in doc["research"]["targets"] if t.get("kind") == "open_breadth"])   # 返事 4: 広く探さない
        self.assertIsNone(GV.weather_line(doc, "霧降高原は例年6月中旬〜7月中旬です。", GB.cfg()))       # 返事 2: 天気の一言を付けない

    def test_in_season_keeps_weather(self):
        doc = GB.build("ツバキやサザンカが見られるところを教えて", now=NOW)
        self.assertFalse(doc["off_season"])
        self.assertEqual(GV.weather_line(doc, "本文", GB.cfg()), GB.cfg()["weather_line"]["line"])


def row(name, pref, url, lat=None, lon=None):
    pl = {"name": name, "prefecture": pref, **({"lat": lat, "lon": lon} if lat else {})}
    return {"publisher": "試験の運営者(作り物)", "publisher_kind": "運営者", "official_reason": "フッター(作り物)", "url": url, "subject": "flowers",
            "content": "開花情報", "date_style": "article", "update_style": "append", "place": pl, "question": "試験"}


class Wide(Tmp):
    def test_current_first_and_prefecture_cap(self):
        PS.add([row("神奈川の園A(作り物)", "神奈川県", "https://a.example.jp/", 35.45, 139.63),
                row("神奈川の園B(作り物)", "神奈川県", "https://b.example.jp/", 35.40, 139.60),
                row("神奈川の園C(作り物)", "神奈川県", "https://c.example.jp/", 35.35, 139.55),
                row("群馬の園(作り物)", "群馬県", "https://d.example.jp/", 36.26, 139.07),
                row("静岡の園(作り物)", "静岡県", "https://e.example.jp/", 34.97, 138.38)], now=NOW)
        self.assertEqual(PS._v(PS.cfg()["wide_max_same_prefecture"]), 2)
        near = [x["name"] for x in PS.pick(["flowers"], origin="横浜", limit=3)]
        self.assertTrue(all("神奈川" in n for n in near))                              # wide でなければ近い順のまま
        got = PS.pick(["flowers"], origin="横浜", wide=True, current_names=["静岡の園"])
        names = [x["name"] for x in got]
        self.assertEqual(names[0], "静岡の園(作り物)")                                # 今年の現況がある場所を先に
        self.assertEqual(sum(1 for n in names if "神奈川" in n), 2)                    # 同じ都県は 2 つまで
        self.assertIn("群馬の園(作り物)", names)
        t = [{"kind": "open_breadth", "where": "横浜から行ける範囲", "max_pages": 16}]
        PS.attach(t, {"subjects": ["flowers"], "origin": "横浜"}, NOW, wide=True, current_names=["静岡の園"])
        self.assertEqual([x["name"] for x in t[0]["read_first"]], names)               # 資料に付けるときも同じ選び方
        t = [{"kind": "open_breadth", "where": "横浜から行ける範囲", "max_pages": 16}]
        PS.attach(t, {"subjects": ["flowers"], "origin": "横浜"}, NOW)
        self.assertEqual(len(t[0]["read_first"]), 5)                                    # wide でなければ都県で絞らない


class ApprovedNotPicked(Tmp):
    def test_approved_rows_are_not_read_first(self):
        PS.add([row("試験の園(作り物)", "神奈川県", "https://ok-polish.example.jp/", 35.45, 139.63),
                row("台帳の園(作り物)", "神奈川県", "https://ledger-polish.example.jp/flower/", 35.45, 139.63)], now=NOW)
        lines = PS._raw_lines()
        PS._write_lines([l.replace('"approval": "pending"', '"approval": "approved"') if "ok-polish" in l else l for l in lines])
        rows_ = [("ledger-polish.example.jp", "/flower/", "approved", "flowers", "test-ledger")]
        with mock.patch.object(O, "_ledger_urls", lambda: rows_):
            self.assertEqual(PS.pick(["flowers"], origin="横浜"), [])                    # 一覧の欄が approved の行・台帳に approved の行
        self.assertEqual([x["name"] for x in PS.pick(["flowers"], origin="横浜")], ["台帳の園(作り物)"])


class AutoPending(Tmp):
    def rec(self, **kw):
        base = {"subject": "flowers", "name": "試験の公園(作り物)", "prefecture": "神奈川県", "city": "横浜市", "kind": "サザンカ",
                "state": "サザンカが見頃", "state_date": "2026-11-27", "url": f"https://{HOST}/flower", "publisher": "試験の公園(作り物)",
                "source_class": "official"}
        base.update(kw)
        return base

    def test_official_host_is_added_unverified(self):
        with mock.patch.object(GB, "cfg", _on):
            res = O.record([self.rec()], now=NOW)
            out = PS.after_record(res["records"], now=NOW)
        self.assertEqual(len(out["added"]), 1)
        r = PS.rows()[0]
        self.assertEqual(r["publisher_kind"], "未確認")
        self.assertIs(r["operator_checked"], False)
        self.assertEqual(r["approval"], "pending")
        self.assertIn("運営者は未確認", "".join(PS.step_lines("b-1", {"read_first": PS.pick(["flowers"], origin="横浜"), "max_pages": 16})))
        with mock.patch.object(GB, "cfg", _on):
            again = PS.after_record(O.record([self.rec(state="サザンカが満開", state_date="2026-11-28")], now=NOW)["records"], now=NOW)
        self.assertEqual(again["added"], [])                                            # 一覧に既にある
        # 区分は上げない: 記録の区分はホストで決まる(一覧に載っても同じ)
        self.assertEqual(GB._source_class("https://other-polish.example.com/x", "official"), "secondary")

    def test_secondary_host_gives_hint_only(self):
        res = O.record([self.rec(url="https://intro-polish.example.com/sazanka", source_class="secondary")], now=NOW)
        out = PS.after_record(res["records"], now=NOW)
        self.assertEqual(out["added"], [])
        self.assertEqual(len(out["hints"]), 1)
        self.assertIn("ask research pending", out["hints"][0])
        self.assertEqual(PS.rows(), [])

    def test_not_this_year_or_ledger_or_user_is_skipped(self):
        with mock.patch.object(GB, "cfg", _on):
            res = O.record([self.rec(state_date="2025-11-27", url=f"https://{HOST}/old"),
                            self.rec(source_class="user", url=None, name="試験の公園2(作り物)")], now=NOW)
            self.assertEqual(PS.after_record(res["records"], now=NOW), {"added": [], "hints": []})
            with mock.patch.object(PS, "in_ledger", lambda u: "test-ledger"):
                res = O.record([self.rec(url=f"https://{HOST}/ledger")], now=NOW)
                self.assertEqual(PS.after_record(res["records"], now=NOW)["added"], [])

    def test_ask_record_prints_hint(self):
        from ikimonobiyori import ask
        b = os.path.join(self.tmp.name, "reads.json")
        with open(b, "w", encoding="utf-8") as f:
            json.dump([self.rec(url="https://intro-polish.example.com/sazanka2", source_class="secondary")], f, ensure_ascii=False)
        err = io.StringIO()
        flow = ask.Flow(os.path.join(self.tmp.name, "work"), now=NOW, clock=lambda: NOW)
        with redirect_stderr(err):
            flow.record(b)
        self.assertIn("一覧に残せるか確かめる", err.getvalue())


if __name__ == "__main__":
    unittest.main()
