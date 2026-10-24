"""公式の現況ページをコードで読む(段階16 A-4。ikimonobiyori/fetch/status_pages.py)。通信なし。
ページの見本は、構造(見出し・ラベル・アイコンの並び)だけをまねた**合成のデータ**。本物の HTML・本文はリポジトリに入れない(docs/stage16-decisions.md D-05)。"""
import contextlib
import copy
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

from ikimonobiyori import paths, sources
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import status_pages as sp
from ikimonobiyori.fetch.live import LiveError

POLICY = sources.load_policy()
REG = sources.load_registry("autumn_leaves")
SRC = sources.sources_by_id(REG)
CFG = load_config()

# 合成の見本(日光型): 目次に地点名だけ → 地点ごとに 見出し・画像・現在の状況・紹介文(別の日付を含む)・見頃予測・最終更新日
NIKKO_HTML = """<html><head><title>紅葉情報(見本)</title><script>var x = "現在の状況：✕";</script></head><body>
<ul class="toc"><li>【奥日光】湯ノ湖、湯滝</li><li>【奥日光】竜頭滝</li></ul>
<div class="item"><h3>【奥日光】湯ノ湖、湯滝</h3><img src="/img/a.jpg" alt="【奥日光】湯ノ湖、湯滝">
<p>現在の状況：◎</p><p>10/19現在　見本の紹介文です。色づき始めました。</p><p>見頃予測：10月上旬～10月中旬</p><p>最終更新日：2026年10月20日</p></div>
<div class="item"><h3>【奥日光】竜頭滝</h3><dl><dt>現在の状況</dt><dd>◯</dd><dt>見頃予測</dt><dd>10月下旬～11月中旬（木の種類により異なります）</dd>
<dt>最終更新日</dt><dd>2026年10月22日</dd></dl></div>
<div class="item"><h3>【鬼怒川・川治】鬼怒川温泉 丸山（鬼怒川温泉ロープウェイ）</h3><p>現在の状況：△</p><p>最終更新日：2026年10月22日</p></div>
<div class="item"><h3>【見本】台帳にない地点</h3><p>現在の状況：◎</p><p>最終更新日：2026年10月22日</p></div>
</body></html>"""

# 合成の見本(箱根型): 状況の一覧(アイコン → 地点名 → 日付 → アイコン → 語)と、同じ地点名の「見どころ」(紹介文に別の日付と似た語)
HAKONE_HTML = """<html><body>
<section class="status">
<div><img src="/common/img/icon_lev2.png" alt=""><span>仙石原（長安寺）</span><span>10/16現在</span><img src="/common/img/icon_lev2.png"><span>色づきはじめ</span></div>
<div><img src="/common/img/icon_lev4.png" alt=""><span>強羅（箱根美術館）</span><span>10/06現在</span><img src="/common/img/icon_lev4.png"><span>また来年</span></div>
<div><img src="/common/img/icon_lev1.png" alt=""><span>湖尻</span><span>10/15現在</span><img src="/common/img/icon_lev1.png"><span>まだまだ</span></div>
<div><img src="/common/img/icon_lev1.png" alt=""><span>元箱根</span><span>12/28現在</span><img src="/common/img/icon_lev1.png"></div>
</section>
<section class="midokoro"><h3>湖尻</h3><img src="/photo/kojiri.jpg"><p>10/22現在、湖畔の木々が色づき始めた(見本の紹介文)。</p>
<h3>仙石原（長安寺）</h3><p>見本の紹介文。</p></section>
</body></html>"""


def nikko_covers(*labels):
    return [{"name": lb, "label": lb} for lb in labels]


class Tokens(unittest.TestCase):
    def test_scripts_are_skipped_and_images_give_file_names(self):
        toks = sp.tokens(NIKKO_HTML)
        self.assertNotIn(("text", 'var x = "現在の状況：✕";'), toks)
        self.assertIn(("img", "a.jpg"), toks)
        self.assertTrue(all(k in ("text", "img") for k, _ in toks))


class Nikko(unittest.TestCase):
    COVERS = nikko_covers("【奥日光】湯ノ湖、湯滝", "【奥日光】竜頭滝", "【鬼怒川・川治】鬼怒川温泉 丸山", "【日光】霧降滝")

    def test_reads_the_labelled_fields_not_the_intro_text(self):
        items, diag = sp.parse_nikko(NIKKO_HTML, self.COVERS)
        got = {it["label"]: (it["state"], it["updated"], it.get("forecast")) for it in items}
        self.assertEqual(got, {
            "【奥日光】湯ノ湖、湯滝": ("◎", "2026-10-20", "10月上旬～10月中旬"),          # 紹介文の「10/19現在」「色づき始め」は使わない
            "【奥日光】竜頭滝": ("◯", "2026-10-22", "10月下旬～11月中旬（木の種類により異なります）"),   # 見出しと値が別の要素でも読む
            "【鬼怒川・川治】鬼怒川温泉 丸山": ("△", "2026-10-22", None)})               # 括弧の注記つきの見出し
        self.assertEqual(diag["missing"], ["【日光】霧降滝"])
        self.assertEqual(diag["ambiguous"], [])
        self.assertGreaterEqual(diag["labels_seen"], 5)                                    # 目次の出現も数える(値がないので読まない)

    def test_conflicting_duplicates_are_not_guessed(self):
        html = NIKKO_HTML.replace("</body>", "<div><h3>【奥日光】竜頭滝</h3><p>現在の状況：◎</p><p>最終更新日：2026年10月22日</p></div></body>")
        items, diag = sp.parse_nikko(html, self.COVERS)
        self.assertNotIn("【奥日光】竜頭滝", [it["label"] for it in items])
        self.assertEqual(diag["ambiguous"], ["【奥日光】竜頭滝"])

    def test_labels_match_regardless_of_spaces(self):
        html = "<div><h3>【足尾】CAMP THE　 銀山平</h3><p>現在の状況：△</p><p>最終更新日：2026年10月21日</p></div>"
        items, _ = sp.parse_nikko(html, nikko_covers("【足尾】CAMP THE 銀山平"))
        self.assertEqual([(it["label"], it["state"]) for it in items], [("【足尾】CAMP THE 銀山平", "△")])

    def test_a_changed_page_reads_nothing(self):
        items, diag = sp.parse_nikko("<html><body><p>リニューアルしました</p></body></html>", self.COVERS)
        self.assertEqual(items, [])
        self.assertEqual(len(diag["missing"]), len(self.COVERS))


class Hakone(unittest.TestCase):
    ON = date(2026, 10, 23)

    def parse(self, html=HAKONE_HTML):
        return sp.parse_hakone(html, SRC["hakone-kankou-koyo"]["covers"], SRC["hakone-kankou-koyo"]["notation"], self.ON)

    def test_reads_the_status_list_not_the_highlights(self):
        items, diag = self.parse()
        got = {it["label"]: (it["state"], it["updated"], it["icon"]) for it in items}
        self.assertEqual(got["湖尻"], ("まだまだ", "2026-10-15", "icon_lev1"))                 # 見どころの「10/22現在 色づき始めた」ではない(段階16 A-1)
        self.assertEqual(got["仙石原(長安寺)"], ("色づきはじめ", "2026-10-16", "icon_lev2"))
        self.assertEqual(got["強羅(箱根美術館)"], ("また来年", "2026-10-06", "icon_lev4"))
        self.assertEqual(got["元箱根"], ("まだまだ", "2025-12-28", "icon_lev1"))               # 読んだ日より後の M/D は前の年(年を補う)
        self.assertTrue(all(it["year_inferred"] for it in items))
        self.assertIn("宮ノ下", diag["missing"])
        self.assertEqual(diag["ambiguous"], [])

    def test_icon_and_word_must_agree(self):
        html = HAKONE_HTML.replace("<span>10/15現在</span><img src=\"/common/img/icon_lev1.png\"><span>まだまだ</span>",
                                   "<span>10/15現在</span><img src=\"/common/img/icon_lev1.png\"><span>色づきはじめ</span>")
        items, diag = self.parse(html)
        self.assertNotIn("湖尻", [it["label"] for it in items])
        self.assertIn("湖尻", diag["ambiguous"])

    def test_unknown_icons_are_not_guessed(self):
        html = HAKONE_HTML.replace("icon_lev2.png", "icon_lev3.png")
        items, diag = self.parse(html)
        self.assertNotIn("仙石原(長安寺)", [it["label"] for it in items])
        self.assertIn("icon_lev3", diag["unknown_icons"])

    def test_a_date_without_an_icon_is_not_a_status(self):
        html = "<html><body><h3>湖尻</h3><p>10/22現在</p><p>色づきはじめ</p></body></html>"
        items, diag = self.parse(html)
        self.assertEqual(items, [])
        self.assertEqual(diag["no_fields"], ["湖尻"])


class FakeWeb:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url):
        self.calls.append(url)
        st, body = self.pages.get(url, (404, "not found"))
        return st, body, {}


class ReadSource(unittest.TestCase):
    NIKKO = SRC["nikko-kankou-autumn-leaves"]
    ROBOTS = "https://www.nikko-kankou.org/robots.txt"

    def test_robots_first_then_the_page(self):
        web = FakeWeb({self.ROBOTS: (200, "User-agent: *\nDisallow: /admin/\n"), self.NIKKO["url"]: (200, NIKKO_HTML)})
        reads, rep = sp.read_source(self.NIKKO, http_get=web, cfg=CFG, on=date(2026, 10, 23), max_requests=2)
        self.assertEqual(web.calls, [self.ROBOTS, self.NIKKO["url"]])
        self.assertEqual(rep["status"], "ok")
        r = next(x for x in reads if x["label"] == "【奥日光】湯ノ湖、湯滝")
        self.assertEqual(r, {"source": "nikko-kankou-autumn-leaves", "site": "kouyou-0001", "label": "【奥日光】湯ノ湖、湯滝", "state": "◎",
                             "updated": "2026-10-20", "method": "code", "forecast": "10月上旬～10月中旬",
                             "observed_md": "10-19"})                                       # 本文の先頭の「10/19現在」(段階20。ユーザー承認 2026-10-25)
        self.assertEqual(set(rep), {"source", "requests", "status", "diag"})                # 報告に本文の欄はない
        self.assertNotIn("見本の紹介文", json.dumps(rep, ensure_ascii=False))

    def test_robots_refusal_and_errors_read_nothing(self):
        for robots in ((200, "User-agent: *\nDisallow: /\n"), (404, ""), (503, "")):
            web = FakeWeb({self.ROBOTS: robots, self.NIKKO["url"]: (200, NIKKO_HTML)})
            reads, rep = sp.read_source(self.NIKKO, http_get=web, cfg=CFG, on=date(2026, 10, 23), max_requests=2)
            self.assertEqual((reads, web.calls), ([], [self.ROBOTS]), robots)              # ページは読まない
        web = FakeWeb({self.ROBOTS: (200, ""), self.NIKKO["url"]: (403, "forbidden")})
        reads, rep = sp.read_source(self.NIKKO, http_get=web, cfg=CFG, on=date(2026, 10, 23), max_requests=2)
        self.assertEqual(reads, [])
        self.assertIn("403", rep["status"])

    def test_hosts_and_limits(self):
        other = dict(self.NIKKO, url="https://example.org/autumn-leaves")
        with self.assertRaises(LiveError):
            sp.read_source(other, http_get=FakeWeb({}), cfg=CFG, on=date(2026, 10, 23), max_requests=2)
        with self.assertRaises(LiveError):
            sp.read_source(self.NIKKO, http_get=FakeWeb({self.ROBOTS: (200, "")}), cfg=CFG, on=date(2026, 10, 23), max_requests=1)
        with self.assertRaises(ValueError):
            sp.read_source(SRC["daigo-kanko-koyo"], http_get=FakeWeb({}), cfg=CFG, on=date(2026, 10, 23), max_requests=2)

    def test_only_two_hosts_are_allowed(self):
        self.assertEqual(CFG["live"]["allowed_hosts_by_subject"][sp.SUBJECT_HOSTS], ["www.nikko-kankou.org", "www.hakone.or.jp"])
        self.assertEqual(sorted(sp.PARSERS), sorted(s["id"] for s in REG["sources"] if s.get("reader") == "code"))


class ReadCommand(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-read-"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def run_main(self, argv, http_get=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {paths.ENV_DATA_DIR: str(self.d)}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sources.main(argv, http_get=http_get)
        return code, out.getvalue(), err.getvalue()

    def test_the_gate(self):
        base = ["read", "--source", "nikko-kankou-autumn-leaves", "--now", "2026-10-23T08:00:00+09:00"]
        self.assertEqual(self.run_main(base + ["--max-requests", "2"])[0], 2)                   # --live なし
        code, _, err = self.run_main(base + ["--live", "--max-requests", "2"])                    # テスト中は本物の通信を常に拒否
        self.assertEqual(code, 2)
        self.assertIn("BIYORI_UNDER_TEST", err)
        self.assertEqual(self.run_main(base + ["--live"], http_get=FakeWeb({}))[0], 2)            # --max-requests なし

    def test_reads_and_records_facts_only(self):
        hk = SRC["hakone-kankou-koyo"]
        web = FakeWeb({"https://www.hakone.or.jp/robots.txt": (200, "User-agent: *\n"), hk["url"]: (200, HAKONE_HTML)})
        code, out, _ = self.run_main(["read", "--source", "hakone-kankou-koyo", "--source", "daigo-kanko-koyo", "--now", "2026-10-23T08:00:00+09:00",
                                      "--live", "--max-requests", "4", "--record"], http_get=web)
        res = json.loads(out)
        self.assertEqual(code, 1)                                                                # 大子町はコードで読まない(読めなかった扱い)
        self.assertEqual(res["recorded"]["written"], 4)
        with mock.patch.dict(os.environ, {paths.ENV_DATA_DIR: str(self.d)}):
            recs = sources.read_records("autumn_leaves")
        kojiri = next(r for r in recs if r.get("site") == "kouyou-0033")                        # 湖尻は段階17 の見直しで名所カタログに入った
        self.assertEqual((kojiri["official_state"], kojiri["stage"], kojiri["official_updated"], kojiri["method"], kojiri["updated_year_inferred"]),
                         ("まだまだ", "not_yet", "2026-10-15", "code", True))
        moto = next(r for r in recs if r.get("name") == "元箱根")                                # カタログ外の地点の例(段階17 の見直しで湖尻から差し替え)
        self.assertEqual((moto["official_state"], moto["stage"], moto["method"]), ("まだまだ", "not_yet", "code"))
        raw = (self.d / "status_log" / "autumn_leaves.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("見本の紹介文", raw)                                                    # 本文は残さない
        self.assertNotIn("<", raw)

    def test_user_verified_and_code_disagreeing_is_a_conflict(self):
        """ユーザーが確かめた事実とコードの読み取りが食い違えば、どちらも消さず、答えの材料で conflict として示す(推測で選ばない)。"""
        mk = lambda **kw: sources.make_record(registry=REG, policy=POLICY, source_id="hakone-kankou-koyo", name="宮ノ下", label="宮ノ下",
                                              year_inferred=True, **kw)                          # カタログ外の地点の例(段階17 の見直しで湖尻から差し替え)
        recs = [mk(read_at="2026-10-23T07:10:00+09:00", state="まだまだ", updated="2026-10-15", method="user_verified"),
                mk(read_at="2026-10-23T07:17:00+09:00", state="色づきはじめ", updated="2026-10-22", method="code"),
                sources.make_record(registry=REG, policy=POLICY, source_id="hakone-kankou-koyo", name="元箱根", label="元箱根", year_inferred=True,
                                    read_at="2026-10-23T07:17:00+09:00", state="まだまだ", updated="2026-10-16", method="code")]
        got = sources.summarize(recs, registry=REG, catalog_doc=sources.catalog_mod.load_catalog("autumn_leaves"), policy=POLICY,
                                on=date(2026, 10, 23), dates=[date(2026, 10, 24)])
        self.assertEqual([x["name"] for x in got["conflicts"]], ["宮ノ下"])
        self.assertEqual([(c["method"], c["official_state"]) for c in got["conflicts"][0]["conflict"]],
                         [("user_verified", "まだまだ"), ("code", "色づきはじめ")])
        agree = [recs[0], {**recs[1], "official_state": "まだまだ", "stage": "not_yet", "official_updated": "2026-10-15"}]
        self.assertEqual(sources.conflicts(agree), {})                                          # 同じ事実なら食い違いではない

    def test_a_registry_entry_cannot_claim_code_reading(self):
        r = copy.deepcopy(REG)
        for s in r["sources"]:
            if s["id"] == "daigo-kanko-koyo":
                s["reader"] = "code"
        errs = sources.check_registry(r, name="autumn_leaves", catalog_doc=sources.catalog_mod.load_catalog("autumn_leaves"), policy=POLICY)
        self.assertTrue(any("reader: code" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
