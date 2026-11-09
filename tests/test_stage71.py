"""段階71: --out など書き込み先の相対パスは、データ置き場からの相対(実行したフォルダ = リポジトリの中に書かない)。合成データ(通信しない)。"""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import paths

ROOT = Path(__file__).resolve().parent.parent
NOW = "2026-11-10T09:00:00+09:00"


class Stop(Exception):
    pass


class InCwd:
    """別の一時フォルダを実行したフォルダにする(相対パスがそこに書かれないことを確かめる)。"""

    def __enter__(self):
        self.old = os.getcwd()
        self.cwd = tempfile.mkdtemp()
        os.chdir(self.cwd)
        return Path(self.cwd)

    def __exit__(self, *exc):
        os.chdir(self.old)


class ResolveWriteArgs(unittest.TestCase):
    def test_relative_absolute_and_missing(self):
        base = tempfile.mkdtemp()
        env = {"IKIMONOBIYORI_DATA_DIR": base}
        absolute = str(Path(tempfile.mkdtemp()) / "a.json")
        a = argparse.Namespace(out="pages/x.html", out_dir=None, cache_dir="cache/c", inputs_out=absolute, other="keep/me")
        paths.resolve_write_args(a, env=env)
        self.assertEqual(Path(a.out), Path(base) / "pages" / "x.html")
        self.assertIsNone(a.out_dir)
        self.assertEqual(Path(a.cache_dir), Path(base) / "cache" / "c")
        self.assertEqual(a.inputs_out, absolute)
        self.assertEqual(a.other, "keep/me")                              # 書き込み先でない引数は変えない


class Commands(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.base})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_guide_page_relative_out(self):
        from ikimonobiyori import guide
        with InCwd() as cwd, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            rc = guide.main(["page", "--theme", "野鳥", "--out", "rel/g.html", "--no-ensure-photos"])
        self.assertEqual(rc, 0)
        self.assertTrue((Path(self.base) / "rel" / "g.html").exists())
        self.assertFalse((cwd / "rel").exists())
        self.assertEqual(Path(out.getvalue().strip()), (Path(self.base) / "rel" / "g.html").resolve())

    def test_sources_proposals_relative_out(self):
        from ikimonobiyori import sources
        with InCwd() as cwd, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = sources.main(["--subject", "autumn_leaves", "proposals", "--now", NOW, "--out", "rel/p.json"])
        self.assertEqual(rc, 0)
        doc = json.loads((Path(self.base) / "rel" / "p.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "biyori-proposal/1")
        self.assertFalse((cwd / "rel").exists())

    def _parsed(self, mod, argv):
        got = {}
        real = paths.resolve_write_args

        def capture(a, *k, **kw):
            real(a, *k, **kw)
            got.update(vars(a))
            raise Stop
        with mock.patch.object(paths, "resolve_write_args", side_effect=capture), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(Stop):
                mod.main(argv)
        return got

    def test_main_py_out_inputs_out_cache_dir(self):
        from ikimonobiyori import main as M
        got = self._parsed(M, ["--request", "r.json", "--inputs", "i.json", "--now", NOW, "--out", "o/out.json", "--inputs-out", "o/in.json",
                               "--cache-dir", "o/cache"])
        self.assertEqual(Path(got["out"]), Path(self.base) / "o" / "out.json")
        self.assertEqual(Path(got["inputs_out"]), Path(self.base) / "o" / "in.json")
        self.assertEqual(Path(got["cache_dir"]), Path(self.base) / "o" / "cache")
        self.assertEqual(got["request"], "r.json")                        # 読むファイルは変えない
        self.assertEqual(got["inputs"], "i.json")

    def test_backtest_run_cache_dir(self):
        from ikimonobiyori import backtest_run as B
        got = self._parsed(B, ["plan", "--cache-dir", "bt/cache", "--now", NOW])
        self.assertEqual(Path(got["cache_dir"]), Path(self.base) / "bt" / "cache")


class RepoMaintenanceToolsAreUnchanged(unittest.TestCase):
    """リポジトリのファイルを作り直す手入れの道具(出力先がリポジトリの中)は、これまでどおり実行したフォルダからの相対。"""

    def test_not_resolved(self):
        for name in ("catalog_audit.py", "jma_normals.py", "jma_phenology.py"):
            self.assertNotIn("resolve_write_args", (ROOT / "ikimonobiyori" / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
