"""段階63b(指示書 docs/stage63b-speed-and-cache-instructions.md): 速く答える。通信しない。合成データだけ。"""
import ast
import json
import os
import tempfile
import time
import unittest
import unittest.mock
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP, ask, page_cache as PC, profiles, warm as WM, yamlcache

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "ikimonobiyori"


class YamlOnce(unittest.TestCase):
    """第1部: YAML は共通の読み込み口から 1 回だけ読む。結果は純 Python の解析器と同じ。"""

    def test_c_loader_gives_same_values_as_pure_python_for_all_package_yaml(self):
        files = sorted(PKG.rglob("*.yaml"))
        self.assertGreater(len(files), 30)
        for f in files:
            text = f.read_text(encoding="utf-8")
            pure = yaml.load(text, Loader=yaml.SafeLoader)
            with self.subTest(f=str(f.relative_to(ROOT))):
                self.assertEqual(yamlcache.parse(text), pure)
                self.assertEqual(yamlcache.load(f), pure)
                self.assertEqual(yamlcache.load(f), yaml.safe_load(text))

    def test_uses_libyaml_when_available(self):
        if hasattr(yaml, "CSafeLoader"):
            self.assertIs(yamlcache.LOADER, yaml.CSafeLoader)
        else:
            self.assertIs(yamlcache.LOADER, yaml.SafeLoader)

    def test_returns_independent_copies(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.yaml"
            p.write_text("a: [1, 2]\nb: {c: x}\n", encoding="utf-8")
            one = yamlcache.load(p)
            one["a"].append(3)
            one["b"]["c"] = "changed"
            self.assertEqual(yamlcache.load(p), {"a": [1, 2], "b": {"c": "x"}})

    def test_rewritten_file_is_read_again_even_with_same_size_and_time(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.yaml"
            p.write_text("v: 1\n", encoding="utf-8")
            self.assertEqual(yamlcache.load(p), {"v": 1})
            st = p.stat()
            p.write_text("v: 2\n", encoding="utf-8")                          # 同じ大きさ
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))                   # 同じ更新時刻にしても
            self.assertEqual(yamlcache.load(p), {"v": 2})

    def test_settled_file_is_not_read_again(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.yaml"
            p.write_text("v: 1\n", encoding="utf-8")
            old = time.time() - 3600
            os.utime(p, (old, old))
            self.assertEqual(yamlcache.load(p), {"v": 1})
            orig = Path.read_bytes
            calls = []

            def spy(self_):
                calls.append(str(self_))
                return orig(self_)
            with unittest.mock.patch.object(Path, "read_bytes", spy):
                for _ in range(5):
                    self.assertEqual(yamlcache.load(p), {"v": 1})
            self.assertEqual(calls, [])

    def test_missing_file_raises_like_read_text(self):
        with self.assertRaises(FileNotFoundError):
            yamlcache.load(Path(tempfile.gettempdir()) / "ikimonobiyori-no-such-file.yaml")

    def test_no_module_parses_yaml_files_directly(self):
        """ファイルを読んで yaml.safe_load / yaml.load に渡す形は、yamlcache だけにある(読み直しを再発させない)。"""
        bad = []
        for f in PKG.rglob("*.py"):
            if f.name == "yamlcache.py":
                continue
            with warnings.catch_warnings():                                   # paths.py の docstring の Windows のパス(\i)の警告は、この検査と関係がない
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(f.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("safe_load", "load") \
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "yaml":
                    bad.append(f"{f.name}:{n.lineno}")
        self.assertEqual(bad, [])

    def test_profile_validation_result_is_the_same_when_memoized(self):
        doc = yamlcache.load(sorted(profiles.PROFILE_DIR.glob("*.yaml"))[0])
        first = profiles.validate_profile(doc)
        self.assertEqual(profiles.validate_profile(doc), first)
        broken = dict(doc)
        broken.pop("profile_id", None)
        errs = profiles.validate_profile(broken)
        self.assertTrue(errs)
        self.assertEqual(profiles.validate_profile(broken), errs)
        errs.append("x")                                                       # 返した一覧を書き換えても次に影響しない
        self.assertNotIn("x", profiles.validate_profile(broken))


JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=JST)


def cand(name, pages, current=None, **kw):
    return {"name": name, "current": current, "pages": [{"url": u, "publisher": "試験市", "source_class": sc} for u, sc in pages], **kw}


def cur(url, state_date, read_at):
    return {"url": url, "state": "見頃", "state_date": state_date, "read_at": read_at.isoformat(), "publisher": "試験市", "source_class": "official"}


def fdoc(cands, subject="autumn_leaves"):
    return {"now": NOW.isoformat(), "dates": ["2026-11-08"], "subjects": {subject: {"subject": subject, "candidates": cands}}}


def plan_of(names, subject="autumn_leaves"):
    return {"subject": subject, "picks": [{"name": n} for n in names]}


class PageCache(unittest.TestCase):
    """第2部: 読み直しは「最後に読んだ時刻」で決める。上限 3 ページ。本文は保存しない。"""

    def targets(self, cands, names=None, reads=None, subject="autumn_leaves"):
        return AP.refresh_targets(fdoc(cands, subject), plan_of(names or [c["name"] for c in cands], subject), reads=reads or {}, now=NOW)

    def test_page_read_within_ttl_is_not_a_target(self):
        c = cand("試験の谷", [("https://a.example/koyo", "official")])
        self.assertEqual([x["url"] for x in self.targets([c])], ["https://a.example/koyo"])                    # 読んだことがない
        self.assertEqual(self.targets([c], reads={"https://a.example/koyo": NOW - timedelta(hours=2)}), [])     # 2 時間前に読んだ

    def test_old_page_date_but_read_yesterday_is_not_a_target(self):
        u = "https://a.example/koyo"
        c = cand("試験の谷", [(u, "official")], current=cur(u, "2026-11-01", NOW - timedelta(hours=20)))       # ページの日付は 7 日前、読んだのは 20 時間前
        self.assertEqual(self.targets([c]), [])

    def test_only_expired_pages_are_targets(self):
        u1, u2 = "https://a.example/1", "https://a.example/2"
        c = cand("試験の谷", [(u1, "official"), (u2, "official")], current=cur(u1, "2026-11-06", NOW - timedelta(hours=30)))
        got = self.targets([c], reads={u1: NOW - timedelta(hours=30), u2: NOW - timedelta(hours=3)})
        self.assertEqual([(x["url"], x["reason"]) for x in got], [(u1, "expired")])

    def test_at_most_three_pages(self):
        self.assertEqual(AP.load_policy()["refresh"]["max_pages"], 3)
        cs = [cand(f"試験の谷{i}", [(f"https://a.example/{i}/{j}", "official") for j in range(3)]) for i in range(3)]
        got = self.targets(cs)
        self.assertEqual(len(got), 3)

    def test_candidates_without_status_pages_and_secondary_pages_are_not_targets(self):
        cs = [cand("試験の池", []), cand("試験の山", [("https://intro.example/takao", "secondary")])]
        self.assertEqual(self.targets(cs), [])

    def test_candidates_with_only_event_pages_are_not_targets(self):
        u = "https://a.example/matsuri"
        c = cand("試験の池", [(u, "official")], festivals=[{"url": u, "name": "試験まつり"}])           # 現況の情報源がない(行事のページだけ)
        self.assertEqual(self.targets([c]), [])
        self.assertEqual(self.targets([c], reads={u: NOW - timedelta(days=30)}), [])

    def test_pending_sources_are_not_targets(self):
        """承認待ちの情報源のページは、読んでも答えの材料にならないので読み直しの対象にしない。"""
        from ikimonobiyori import observations as O
        u = "https://pending.example.org/x"
        c = cand("試験の谷", [(u, "official")])
        with unittest.mock.patch.object(O, "_ledger_gated", lambda r, sj, pol: r["url"] == u):
            self.assertEqual(self.targets([c]), [])
        self.assertEqual([x["url"] for x in self.targets([c])], [u])

    def test_event_and_practical_ttls(self):
        self.assertEqual(PC.ttl("event"), timedelta(days=7))
        self.assertEqual(PC.ttl("practical"), timedelta(days=30))
        self.assertEqual(PC.ttl("visitor_center"), timedelta(hours=48))
        self.assertEqual(PC.ttl("status"), timedelta(hours=24))
        self.assertEqual(PC.ttl("birds"), timedelta(hours=24))

    def test_only_picks_are_targets(self):
        cs = [cand("試験の谷", [("https://a.example/1", "official")]), cand("試験の滝", [("https://a.example/2", "official")])]
        self.assertEqual([x["name"] for x in self.targets(cs, names=["試験の滝"])], ["試験の滝"])

    def test_last_reads_use_records_and_confirmed_times(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            obs = Path(d) / "observations"
            obs.mkdir()
            (obs / "autumn_leaves.jsonl").write_text(json.dumps({"url": "https://a.example/r", "read_at": "2026-11-07T10:00:00+09:00"}) + "\n", encoding="utf-8")
            (obs / "autumn_leaves.confirmed.json").write_text(json.dumps({"k": {"url": "https://a.example/r", "last_confirmed_at": "2026-11-08T09:00:00+09:00"}}),
                                                             encoding="utf-8")
            PC.note([{"url": "https://a.example/c", "ok": False, "reason": "403"}], NOW - timedelta(hours=1), env)
            reads = PC.last_reads(NOW, env)
            self.assertEqual(reads["https://a.example/r"], datetime(2026, 11, 8, 9, 0, tzinfo=JST))
            self.assertEqual(reads["https://a.example/c"], NOW - timedelta(hours=1))
            self.assertEqual(PC.fresh_urls(NOW, env, reads=reads), {"https://a.example/r", "https://a.example/c"})

    def test_cache_does_not_keep_page_text(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            body = "本文" * 500
            PC.note([{"url": "https://a.example/x", "ok": True, "body": body, "text": body, "html": body}], NOW, env)
            f = ask.Flow(Path(d) / "w", now=NOW, env=env)
            batch = [{"subject": "autumn_leaves", "name": "試験の谷", "city": "試験町", "state": "見頃", "state_date": "2026-11-07",
                      "url": "https://a.example/y", "publisher": "試験市", "source_class": "official"}]
            bp = Path(d) / "reads.json"
            bp.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
            f.record(bp)
            lines = [json.loads(x) for x in PC.path(env).read_text(encoding="utf-8").splitlines()]
            self.assertEqual({x["url"] for x in lines}, {"https://a.example/x", "https://a.example/y"})
            for x in lines:
                self.assertLessEqual(set(x), set(PC.KEEP))
            raw = PC.path(env).read_text(encoding="utf-8")
            self.assertNotIn("本文", raw)
            self.assertNotIn("見頃", raw)                                    # 事実そのものも書かない(ハッシュだけ)
            self.assertEqual(PC.facts_hash(batch), next(x for x in lines if x["url"].endswith("/y"))["facts_hash"])

    def test_prepare_skips_pages_read_within_ttl(self):
        doc = {"subjects": {"x": {"summary_pages": [], "items": [{"id": "a", "pages": [{"url": "https://a.example/1"}]}]}}}
        ask.drop_fetched(doc, PC.fresh_urls(NOW, reads={"https://a.example/1": NOW - timedelta(hours=5)}))
        self.assertFalse(doc["needs_fetch"])


class SmallDocs(unittest.TestCase):
    """第4部・段階63a 第8部: 指示の文書は小さく、今有効な決まりの一覧。手順は ask answer を 1 回。"""

    def test_sizes(self):
        self.assertLessEqual(len((ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_bytes()), 15000)
        self.assertLessEqual(len((ROOT / "CLAUDE.md").read_bytes()), 30000)
        self.assertLessEqual(len((ROOT / "AGENTS.md").read_bytes()), 30000)

    def test_the_skill_runs_ask_answer_once_and_never_asks_back(self):
        s = (ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("ikimonobiyori.ask answer --question", "**そのまま**答えにする", "**聞き返さない**", "「今は答えを用意できません」と答えない",
                       "ask warm", "docs/rules-history.md"):
            self.assertIn(needle, s)
        head = s.split("---")[1]
        for w in ("紅葉", "花", "野鳥", "見ごろ", "お出かけ", "おすすめ", "観察会", "どこで見られる"):
            self.assertIn(w, head)                                              # 説明(description)で自動で起動する語

    def test_the_users_rules_are_all_kept(self):
        s = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for needle in ("内部用語", "できないことを提案しない", "質問を入れない", "ウェザーニュース", "tenki.jp", "日本気象協会", "SNS", "山と溪谷オンラインは状態の語・日付・URL だけ",
                       "承認待ちの情報源", "台帳の承認の記入は、本人がチャットで対象と条件を示したときだけ", "出典の見出しは「出典」", "手書きの HTML・図で代用しない"):
            self.assertIn(needle, s)
        h = (ROOT / "docs" / "rules-history.md").read_text(encoding="utf-8")
        self.assertIn("### 段階57(最優先", h)                                     # 経緯は消さずに移した
        self.assertIn("### 段階39", h)


class Warm(unittest.TestCase):
    """第3部: 今日の準備(承認済みの情報源のうち、有効期間を過ぎたものを優先順に)。通信しない。"""

    def test_order_is_status_then_centers_then_events_then_practical(self):
        rows = WM.targets(NOW, reads={})
        kinds = [r["kind"] for r in rows]
        self.assertTrue(kinds)
        self.assertEqual(kinds, sorted(kinds, key=WM.KIND_ORDER.index))
        self.assertEqual([r["order"] for r in rows], list(range(1, len(rows) + 1)))

    def test_only_approved_sources(self):
        from ikimonobiyori import visitor_centers as VC
        urls = {r["url"] for r in WM.targets(NOW, reads={})}
        for c in VC.pending_centers():
            self.assertNotIn(c.get("info_url"), urls, c["id"])
        for sj in WM.SUBJECT_ORDER:
            f = PKG / "data" / "sources" / f"{sj}.yaml"
            for e in (yamlcache.load(f) or {}).get("sources") or [] if f.exists() else []:
                if (e.get("approval") or {}).get("status") != "approved" and e.get("url") not in {x.get("url") for x in (yamlcache.load(f) or {}).get("sources") or []
                                                                                                    if (x.get("approval") or {}).get("status") == "approved"}:
                    self.assertNotIn(e.get("url"), urls, e.get("id"))

    def test_pages_read_within_ttl_are_left_out(self):
        rows = WM.targets(NOW, reads={})
        first = rows[0]
        again = WM.targets(NOW, reads={first["url"]: NOW - timedelta(hours=1)})
        self.assertNotIn(first["url"], {r["url"] for r in again})
        later = WM.targets(NOW, reads={first["url"]: NOW - timedelta(hours=25)})
        self.assertIn(first["url"], {r["url"] for r in later})

    def test_mark_keeps_only_the_read_time(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            WM.mark(["https://a.example/1"], NOW, env)
            WM.mark(["https://a.example/2"], NOW, env, failed="403")
            lines = [json.loads(x) for x in PC.path(env).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(x["url"], x["ok"]) for x in lines], [("https://a.example/1", True), ("https://a.example/2", False)])
            self.assertEqual(set(PC.last_reads(NOW, env)), {"https://a.example/1", "https://a.example/2"})

    def test_second_question_of_the_day_needs_no_fetch(self):
        """同じ日の 2 回目は、1 回目に読んだページを読み直さない(通信なしで答えが出る)。"""
        u = "https://a.example/koyo"
        c = cand("試験の谷", [(u, "official")], current=cur(u, "2026-11-01", NOW - timedelta(hours=1)))
        self.assertEqual(AP.refresh_targets(fdoc([c]), plan_of(["試験の谷"]), reads={u: NOW - timedelta(hours=1)}, now=NOW), [])


if __name__ == "__main__":
    unittest.main()
