"""自己完結の検査(段階12): ikimonobiyori/ のコードが、自分のフォルダの外を指さず、biyori-hub のモジュールを import しない。
書き込み先は環境変数 IKIMONOBIYORI_DATA_DIR(未設定のときの既定は <リポジトリ>/runtime/ikimonobiyori。.gitignore に入れてある)。
実通信の許可の判定(ikimonobiyori/livegate.py)の表と、テストの書き方の規則(通信禁止・子プロセスは run_child だけ)もここ。"""
import ast
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import helpers as H
from helpers import ROOT

from ikimonobiyori import livegate, paths

PKG = ROOT / "ikimonobiyori"
ALLOWED_TOP = {"ikimonobiyori", "yaml", "jsonschema", "requests"}
OUTSIDE_WORDS = {"agents", "hub", "vendor", "adapters", "tests", "snapshots", "schemas/biyori"}
# パッケージの外を指してよいのは、この2行だけ(未設定のときの書き込み先の既定、スクリプトとして起動されたときの import のため)
ALLOWED_OUTSIDE = {("paths.py", 'DEFAULT_DATA_DIR = PKG.parent / "runtime" / "ikimonobiyori"'),
                   ("main.py", "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))")}


class SelfContained(unittest.TestCase):
    def sources(self):
        return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)

    def test_no_import_of_hub_modules(self):
        bad = []
        for p in self.sources():
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                       [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
                for m in mods:
                    top = m.split(".")[0]
                    if top not in ALLOWED_TOP and top not in sys.stdlib_module_names:
                        bad.append(f"{p.relative_to(ROOT).as_posix()}:{node.lineno} import {m}")
        self.assertEqual(bad, [])

    def test_no_path_outside_the_package(self):
        bad = []
        for p in self.sources():
            rel = p.relative_to(PKG).as_posix()
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#")[0]
                if ("parent.parent" in code or "parents[" in code or re.search(r"""["']\.\.(["'/\\])""", code)) and (p.name, code.strip()) not in ALLOWED_OUTSIDE:
                    bad.append(f"{rel}:{i}: {code.strip()}")
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    v = node.value.strip("/")
                    if v in OUTSIDE_WORDS or any(v.startswith(w + "/") for w in OUTSIDE_WORDS):
                        bad.append(f"{rel}:{node.lineno}: 文字列 {node.value!r}")
        self.assertEqual(bad, [])

    def test_the_allowed_lines_still_exist(self):                       # 許可の一覧が古くなっていない
        for name, line in ALLOWED_OUTSIDE:
            self.assertIn(line, (PKG / name).read_text(encoding="utf-8"), name)

    def test_data_files_live_in_the_package(self):
        for rel in ("profiles/autumn_leaves.yaml", "profiles/birds.yaml", "data/sites.yaml", "data/density_survey.yaml", "data/window_survey.yaml",
                    "config.yaml", "schemas/ikimono-profile.schema.json"):
            self.assertTrue((PKG / rel).is_file(), rel)

    def test_no_threshold_or_site_data_outside_the_package(self):
        self.assertFalse((ROOT / "agents").exists())                      # ハブの manifest はこのリポジトリにない(ハブが持つ)


class WritePaths(unittest.TestCase):
    def test_write_paths_follow_the_env(self):
        d = Path(tempfile.mkdtemp(prefix="ikimono-s12-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(paths.data_dir({"IKIMONOBIYORI_DATA_DIR": str(d)}), d)
        self.assertEqual(paths.data_path("cache", {"IKIMONOBIYORI_DATA_DIR": str(d)}), d / "cache")
        self.assertEqual(paths.data_dir({}), ROOT / "runtime" / "ikimonobiyori")          # 未設定の既定
        self.assertEqual(paths.data_dir({"IKIMONOBIYORI_DATA_DIR": ""}), ROOT / "runtime" / "ikimonobiyori")

    def test_the_default_write_location_is_ignored_by_git(self):
        lines = [l.strip() for l in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
        self.assertIn("/runtime/", lines)                                  # IKIMONOBIYORI_DATA_DIR 未設定のときの既定の書き込み先
        rel = paths.DEFAULT_DATA_DIR.relative_to(ROOT).as_posix()
        self.assertTrue(rel.startswith("runtime/"), rel)

    def test_config_paths_are_relative_to_the_write_base(self):
        from ikimonobiyori.config import load_config
        cfg = load_config()
        for v in (cfg["cache"]["dir"], cfg["cache"]["unparsed_dir"], cfg["compose"]["component_dir"]):
            self.assertFalse(Path(v).is_absolute(), v)
            self.assertNotIn("runtime", v)                                 # 基準(IKIMONOBIYORI_DATA_DIR)からの相対。リポジトリの場所を持たない


class OwnLiveGate(unittest.TestCase):
    """実通信の許可: BIYORI_ALLOW_LIVE=1 が要り、BIYORI_UNDER_TEST=1 なら常に拒否(biyori-hub の hub/livegate.py と同じ判定。ハブ側のテストが両方を比べる)。"""
    ENVS = [  # (env, 親プロセスが UNDER_TEST でないときの live_allowed)
        ({}, False), ({"BIYORI_ALLOW_LIVE": "1"}, True),  # gate-test
        ({"BIYORI_ALLOW_LIVE": "0"}, False), ({"BIYORI_ALLOW_LIVE": "true"}, False), ({"BIYORI_ALLOW_LIVE": ""}, False),
        ({"BIYORI_ALLOW_LIVE": "1", "BIYORI_UNDER_TEST": "1"}, False),  # gate-test
        ({"BIYORI_UNDER_TEST": "1"}, False), ({"BIYORI_UNDER_TEST": "0", "BIYORI_ALLOW_LIVE": "1"}, True)]  # gate-test

    def test_decisions(self):
        from unittest import mock
        import os
        with mock.patch.dict(os.environ):
            os.environ.pop("BIYORI_UNDER_TEST", None)                             # 判定の関数だけを見る(何も起動しない)
            for env, want in self.ENVS:
                with self.subTest(env=env):
                    self.assertIs(livegate.live_allowed(env), want)
                    self.assertEqual(livegate.refusal(env) is None, want)
            os.environ["BIYORI_UNDER_TEST"] = "1"                                  # 親がテスト中なら、env を上書きしても常に拒否
            for env, _ in self.ENVS:
                with self.subTest(env=env, parent_under_test=True):
                    self.assertFalse(livegate.live_allowed(env))
                    self.assertIn("テスト中", livegate.refusal(env))

    def test_main_uses_it_and_keeps_the_hook_requirement(self):
        src = (PKG / "main.py").read_text(encoding="utf-8")
        self.assertIn("from ikimonobiyori import engine, livegate, paths, profiles", src)
        self.assertEqual(src.count('os.environ.get("BIYORI_REQ_LOG")'), 2)       # --live は計測フック必須(フェール・クローズ)のまま
        self.assertNotIn("BIYORI_ALLOW_LIVE", src.replace("BIYORI_ALLOW_LIVE=1", ""))      # 判定は livegate だけ(散らさない)

    def test_only_livegate_reads_the_allow_variable(self):
        offenders = [p.relative_to(ROOT).as_posix() for p in PKG.rglob("*.py")
                     if p.name != "livegate.py" and re.search(r"""environ(\.get\(|\[)\s*["']BIYORI_ALLOW_LIVE""", p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


class Docs(unittest.TestCase):
    def test_claude_md_and_agents_md_are_the_same_rules(self):
        c = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
        a = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual((c[0], a[0]), ("# CLAUDE.md", "# AGENTS.md"))
        self.assertEqual(c[1:], a[1:])                                     # 見出し以外は同じ(Claude Code と Codex で同じ規則)

    def test_contract_copy_is_recorded(self):
        import hashlib
        raw = (ROOT / "tests" / "contract" / "biyori-proposal.schema.json").read_bytes()
        h = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()      # 改行を LF にそろえる(チェックアウトの設定に左右されない)
        self.assertIn(h, (ROOT / "tests" / "contract" / "README.md").read_text(encoding="utf-8"))

    def test_license_is_mit_and_readme_states_the_terms(self):
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in ("CC BY 4.0", "Open-Meteo", "iNaturalist", "ユーザー確認済み(2026-10-21、data-sources.md の記録)", "biyori-hub", "IKIMONOBIYORI_DATA_DIR"):   # 段階17 の見直し(2026-10-24、ユーザー承認)で文言を変えた
            self.assertIn(needle, readme)

    def test_no_real_inaturalist_response_in_the_repo(self):
        self.assertEqual(sorted(p.name for p in (ROOT / "tests" / "fixtures").glob("*inaturalist*")),
                         ["make_synthetic_inaturalist.py", "synthetic_inaturalist_sparse.json"])      # 実際の応答の記録は置かない(利用条件の目視が済むまで)


class TestRules(unittest.TestCase):
    """再発防止を壊す書き方が混ざっていないことを、ソースを走査して確かめる。"""
    TESTS = sorted((ROOT / "tests").glob("test_*.py"))

    def test_no_test_sets_allow_live_except_marked_gate_tests(self):
        pat = re.compile(r"""BIYORI_ALLOW_LIVE["']?\]?\s*=\s*["']1|BIYORI_ALLOW_LIVE["']\s*:\s*["']1""")
        bad = []
        for p in self.TESTS + [ROOT / "tests" / "helpers.py"]:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if pat.search(line) and "# gate-test" not in line:
                    bad.append(f"{p.name}:{i}")
        self.assertEqual(bad, [], "BIYORI_ALLOW_LIVE を設定する行には『# gate-test』(拒否の確認専用)の印が要る")

    def test_tests_start_children_only_through_helpers(self):
        bad = []
        for p in self.TESTS:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"subprocess\.(run|Popen|call|check_output|check_call)\(", line):
                    bad.append(f"{p.name}:{i}")
        self.assertEqual(bad, [])

    def test_every_test_module_blocks_sockets(self):
        for p in self.TESTS:
            src = p.read_text(encoding="utf-8")
            self.assertTrue("import helpers" in src or "import nonet" in src or "from helpers" in src, p.name)       # nonet.py が通信禁止と UNDER_TEST を設定する

    def test_sockets_are_blocked_now(self):
        import socket
        with self.assertRaises(AssertionError):
            socket.create_connection(("example.invalid", 80))


if __name__ == "__main__":
    unittest.main()
