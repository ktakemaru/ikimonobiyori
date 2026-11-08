"""段階63b(指示書 docs/stage63b-speed-and-cache-instructions.md): 速く答える。通信しない。合成データだけ。"""
import ast
import os
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

import yaml

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import profiles, yamlcache

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
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
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


if __name__ == "__main__":
    unittest.main()
