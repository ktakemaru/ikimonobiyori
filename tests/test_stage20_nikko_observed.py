"""段階20(確認の反映 2026-10-25): 日光のコードの読み取りで、地点の本文の先頭の「M/D現在」(年なし)を状態の観察日として取る。通信なし。
ページは構造だけをまねた合成のデータ(本物の HTML・本文はリポジトリに入れない)。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import paths, sources
from ikimonobiyori.fetch import status_pages as sp

POLICY = sources.load_policy()
REG = sources.load_registry("autumn_leaves")
NIKKO = sources.sources_by_id(REG)["nikko-kankou-autumn-leaves"]
ROBOTS = "https://www.nikko-kankou.org/robots.txt"
MARK = POLICY["freshness"]["observed_year_from_update_mark"]

# 合成の見本: 本文に日付あり(見出しと値が同じ断片 / 別の断片)・日付なし・書き出しが違う(部位ごとの書き方)・本文の途中の日付
HTML = """<html><body>
<div><h3>【奥日光】湯ノ湖、湯滝</h3><p>現在の状況：◎</p><p>10/20現在　見本の本文です。</p><p>最終更新日：2026年10月21日</p></div>
<div><h3>【奥日光】竜頭滝</h3><dl><dt>現在の状況</dt><dd>◯</dd></dl><p>１０/２２現在　見本の本文です。</p><dl><dt>最終更新日</dt><dd>2026年10月22日</dd></dl></div>
<div><h3>【奥日光】中禅寺湖、華厳滝</h3><p>現在の状況：◯</p><p>見本の本文です。</p><p>最終更新日：2026年10月22日</p></div>
<div><h3>【鬼怒川・川治】日塩もみじライン</h3><p>現在の状況：◎</p><p>10/18山頂 終盤・中腹 見ごろ・山麓 色づき始め(見本)</p><p>最終更新日：2026年10月22日</p></div>
<div><h3>【奥日光】いろは坂</h3><p>現在の状況：◯</p><p>見本の本文です。10/21現在の写真です。</p><p>最終更新日：2026年10月22日</p></div>
</body></html>"""
LABELS = ["【奥日光】湯ノ湖、湯滝", "【奥日光】竜頭滝", "【奥日光】中禅寺湖、華厳滝", "【鬼怒川・川治】日塩もみじライン", "【奥日光】いろは坂"]


def covers():
    return [c for c in NIKKO["covers"] if c["label"] in LABELS]


class Parse(unittest.TestCase):
    def test_the_date_at_the_head_of_the_body_only(self):
        items, _ = sp.parse_nikko(HTML, covers())
        got = {it["label"]: (it["state"], it["updated"], it.get("observed_md")) for it in items}
        self.assertEqual(got, {
            "【奥日光】湯ノ湖、湯滝": ("◎", "2026-10-21", "10-20"),            # 本文の先頭に日付あり
            "【奥日光】竜頭滝": ("◯", "2026-10-22", "10-22"),                  # 見出しと値が別の断片・全角の数字
            "【奥日光】中禅寺湖、華厳滝": ("◯", "2026-10-22", None),           # 本文に日付なし → 更新日だけ
            "【鬼怒川・川治】日塩もみじライン": ("◎", "2026-10-22", None),     # 書き出しが違う → 取らない。状態は「現在の状況」の原文のまま
            "【奥日光】いろは坂": ("◯", "2026-10-22", None)})                  # 本文の途中の日付は取らない


class Recorded(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-s20obs-"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_the_year_comes_from_the_same_items_update_date_with_a_mark(self):
        web = lambda url: (200, "User-agent: *\n", {}) if url == ROBOTS else (200, HTML, {})
        out = io.StringIO()
        env = {paths.ENV_DATA_DIR: str(self.d)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            sources.main(["read", "--source", NIKKO["id"], "--now", "2026-10-25T08:10:00+09:00", "--live", "--max-requests", "2", "--record"],
                         http_get=web)
        self.assertEqual(json.loads(out.getvalue())["recorded"]["gaps"], {})
        with mock.patch.dict(os.environ, env):
            recs = {r["label"]: r for r in sources.read_records("autumn_leaves")}
        r = recs["【奥日光】湯ノ湖、湯滝"]
        self.assertEqual((r["official_observed"], r["observed_year_inferred"], r["freshness_basis"]), ("2026-10-20", MARK, "observed_date"))
        self.assertEqual(recs["【奥日光】竜頭滝"]["official_observed"], "2026-10-22")
        for lb in ("【奥日光】中禅寺湖、華厳滝", "【鬼怒川・川治】日塩もみじライン", "【奥日光】いろは坂"):
            self.assertNotIn("official_observed", recs[lb])
            self.assertEqual(recs[lb]["freshness_basis"], "updated_date")
        self.assertEqual(recs["【鬼怒川・川治】日塩もみじライン"]["official_state"], "◎")
        raw = (self.d / "status_log" / "autumn_leaves.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("見本の本文", raw)                                       # 本文は残さない
        self.assertEqual(recs["【鬼怒川・川治】日塩もみじライン"]["official_parts"][0], {"part": "山頂", "state": "終盤"})   # 段階21: 本文の部位ごとの状態は記録に残る
        self.assertNotIn("見本の本文", raw)


if __name__ == "__main__":
    unittest.main()
