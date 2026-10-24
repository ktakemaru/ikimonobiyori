"""段階20 ⑥: 記録の漏れ。前の日と同じ内容でも、今日読んだ地点は今日の記録として残る。読んだ数と記録した数を照らす。通信なし。
ページは構造だけをまねた合成のデータ(本物の HTML・本文はリポジトリに入れない)。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

import test_answer as TA
from ikimonobiyori import answer, paths, sources

POLICY = sources.load_policy()
REG = sources.load_registry("autumn_leaves")
NIKKO = sources.sources_by_id(REG)["nikko-kankou-autumn-leaves"]
ROBOTS = "https://www.nikko-kankou.org/robots.txt"
STATES = ("◎", "◯", "△")


def page(states):
    """台帳の日光の全地点を並べた合成のページ。states: {label: (状態, 最終更新日の日)}。"""
    blocks = [f"<div class='item'><h3>{lb}</h3><p>現在の状況：{st}</p><p>最終更新日：2026年10月{d}日</p></div>" for lb, (st, d) in states.items()]
    return "<html><body>" + "".join(blocks) + "</body></html>"


class Web:
    def __init__(self, html):
        self.html = html

    def __call__(self, url):
        return (200, "User-agent: *\n", {}) if url == ROBOTS else (200, self.html, {})


class EveryPlaceReadIsRecordedToday(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s20rec-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {paths.ENV_DATA_DIR: str(self.d)}
        self.labels = [c["label"] for c in NIKKO["covers"]]

    def read(self, now, states):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sources.main(["read", "--source", NIKKO["id"], "--now", now, "--live", "--max-requests", "2", "--record"],
                                http_get=Web(page(states)))
        self.assertEqual(code, 0, err.getvalue())
        return json.loads(out.getvalue()), err.getvalue()

    def today(self, day):
        with mock.patch.dict(os.environ, self.env):
            return sources.records_on("autumn_leaves", day)

    def test_all_places_are_recorded_even_when_some_are_unchanged_from_the_day_before(self):
        self.assertGreaterEqual(len(self.labels), 24)                                   # 日光の台帳は 24 地点(10/25 の漏れの再現)
        day1 = {lb: (STATES[i % 3], 21) for i, lb in enumerate(self.labels)}
        self.read("2026-10-24T16:45:00+09:00", day1)
        same = set(self.labels[:6])                                                     # 6 地点は前の日とまったく同じ内容
        day2 = {lb: (day1[lb] if lb in same else ("◎", 24)) for lb in self.labels}
        res, err = self.read("2026-10-25T08:10:00+09:00", day2)
        self.assertEqual((res["results"][0]["covers"], res["results"][0]["read"]), (len(self.labels), len(self.labels)))
        self.assertEqual((res["recorded"]["written"], res["recorded"]["duplicates"]), (len(self.labels), 0))
        self.assertEqual(res["recorded"]["gaps"], {})
        self.assertEqual(err, "")
        got = self.today(date(2026, 10, 25))
        self.assertEqual(sorted(r["label"] for r in got), sorted(self.labels))           # 24 地点すべてが今日の記録
        self.assertTrue(all(r["read_at"] == "2026-10-25T08:10:00+09:00" for r in got))   # 読んだ日時は今日
        self.assertFalse(any(r.get("superseded") for r in got))                         # 置き換えの印は使わない
        kinds = {("site" in r, "name" in r) for r in got}
        self.assertEqual(kinds, {(True, False), (False, True)})                         # 名所 ID の地点もラベル(名前)の地点も落ちない
        self.assertEqual(len(self.today(date(2026, 10, 24))), len(self.labels))          # 前の日の記録はそのまま

    def test_a_second_read_on_the_same_day_is_not_written_twice_and_nothing_is_lost(self):
        states = {lb: ("◎", 22) for lb in self.labels}
        self.read("2026-10-25T08:10:00+09:00", states)
        res, _ = self.read("2026-10-25T09:00:00+09:00", states)
        self.assertEqual((res["recorded"]["written"], res["recorded"]["duplicates"]), (0, len(self.labels)))
        self.assertEqual(res["recorded"]["gaps"], {})                                   # 同じ日の重複は漏れではない
        self.assertEqual(len(self.today(date(2026, 10, 25))), len(self.labels))

    def test_two_labels_of_one_site_are_both_recorded(self):
        two = [c["label"] for c in NIKKO["covers"] if c.get("site") == "kouyou-0002"]
        self.assertEqual(len(two), 2)                                                   # 戦場ヶ原・小田代原の木々 / 小田代原の草紅葉
        self.read("2026-10-24T16:45:00+09:00", {lb: ("◎", 21) for lb in self.labels})
        self.read("2026-10-25T08:10:00+09:00", {lb: ("◎", 21) for lb in self.labels})
        self.assertEqual(sorted(r["label"] for r in self.today(date(2026, 10, 25)) if r.get("site") == "kouyou-0002"), sorted(two))


class AgentBatchAcrossDays(unittest.TestCase):
    """要約の道具で読んだ記録(record --batch)も、前の日と同じ内容で今日の記録として残る。"""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s20batch-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {paths.ENV_DATA_DIR: str(self.d)}
        self.batch = self.d / "reads.json"
        self.batch.write_text(json.dumps([
            {"source": NIKKO["id"], "site": "kouyou-0003", "label": "【奥日光】いろは坂", "state": "◯", "updated": "2026-10-22"},
            {"source": NIKKO["id"], "name": "川治温泉", "label": "【鬼怒川・川治】川治温泉", "state": "△", "updated": "2026-10-22"}],
            ensure_ascii=False), encoding="utf-8")

    def record(self, at):
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out):
            self.assertEqual(sources.main(["--subject", "autumn_leaves", "record", "--read-at", at, "--batch", str(self.batch)]), 0)
        return json.loads(out.getvalue())

    def test_same_batch_on_the_next_day_is_written_again(self):
        self.assertEqual(self.record("2026-10-24T16:45:00+09:00")["written"], 2)
        res = self.record("2026-10-25T08:10:00+09:00")
        self.assertEqual((res["written"], res["duplicates"], res["gaps"]), (2, 0, {}))
        self.assertEqual(res["check"][NIKKO["id"]], {"read": 2, "recorded": 2, "missing": []})
        self.assertEqual(self.record("2026-10-25T12:00:00+09:00")["written"], 0)         # 同じ日の同じ事実は二重に書かない


class GapsAreNotSilent(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s20gap-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {paths.ENV_DATA_DIR: str(self.d)}

    def mk(self, label, at="2026-10-25T08:10:00+09:00"):
        return sources.make_record(registry=REG, policy=POLICY, source_id=NIKKO["id"], read_at=at, state="◎", updated="2026-10-21",
                                   **({"site": c["site"]} if "site" in (c := next(x for x in NIKKO["covers"] if x["label"] == label))
                                      else {"name": c["name"]}), label=label)

    def test_a_read_place_missing_from_todays_records_is_reported(self):
        labels = [c["label"] for c in NIKKO["covers"]]
        with mock.patch.dict(os.environ, self.env):
            sources.append_records([self.mk(lb) for lb in labels[:18]], registry=REG, policy=POLICY)
            check = sources.recording_check([self.mk(lb) for lb in labels], "autumn_leaves")
            gaps = sources.recording_gaps(check)
            self.assertEqual((gaps[NIKKO["id"]]["read"], gaps[NIKKO["id"]]["recorded"]), (len(labels), 18))
            self.assertEqual(gaps[NIKKO["id"]]["missing"], labels[18:])
            got = sources.record_gaps_for_answer([f"{NIKKO['id']}={len(labels)}"], ["autumn_leaves"], date(2026, 10, 25))
            self.assertEqual(got, [{"source": NIKKO["id"], "publisher": NIKKO["publisher"], "read": len(labels), "recorded": 18}])
            self.assertEqual(sources.record_gaps_for_answer([f"{NIKKO['id']}=18"], ["autumn_leaves"], date(2026, 10, 25)), [])

    def test_the_answer_warns_under_notes_without_internal_terms(self):
        gap = [{"source": "test-koyo", "publisher": "試験の観光協会", "read": 24, "recorded": 18}]
        recs = [sources.make_record(registry=TA.REG, policy=POLICY, read_at=TA.NOW.isoformat(), source_id="test-koyo", site="kouyou-0001",
                                    label="渓谷", state="◎", updated="2026-10-22")]
        t = answer.compose(TA.parts(recs), now=TA.NOW, dates=TA.DATES, policy=POLICY, record_gaps=gap)
        warn = POLICY["answer"]["record_gap"].format(publisher="試験の観光協会", read=24, recorded=18)
        self.assertIn(f"- {warn}", TA.body_lines(t, POLICY["answer"]["headings"]["notes"]))
        self.assertEqual(answer.forbidden_found(t, POLICY), [])
        self.assertNotIn(warn, answer.compose(TA.parts(recs), now=TA.NOW, dates=TA.DATES, policy=POLICY))


if __name__ == "__main__":
    unittest.main()
