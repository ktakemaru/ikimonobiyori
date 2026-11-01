"""テスト用の部品。import すると通信禁止(nonet)が有効になる。
- 提案の検証は tests/contract/biyori-proposal.schema.json(biyori-hub の契約 biyori-proposal/1 の写し。tests/contract/README.md)で行う。
- 子プロセスは run_child で起動する(BIYORI_UNDER_TEST=1 が付く = --live は常に拒否。BIYORI_ALLOW_LIVE は引き継がない)。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import nonet  # noqa: F401  (通信禁止。BIYORI_UNDER_TEST=1 を設定する)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures"
CONTRACT = ROOT / "tests" / "contract"
_VALIDATORS = {}


def schema_errors(name, doc):
    """契約 biyori-proposal/1 の検証。メッセージのリスト(空=合格)。"""
    if name != "biyori-proposal/1":
        raise KeyError(name)
    if name not in _VALIDATORS:
        _VALIDATORS[name] = Draft202012Validator(json.loads((CONTRACT / "biyori-proposal.schema.json").read_text(encoding="utf-8")))
    return ["/".join(map(str, e.path)) + ": " + e.message[:160] for e in sorted(_VALIDATORS[name].iter_errors(doc), key=lambda e: list(e.path))]


_PASS_KEYS = ("PATH", "SYSTEMROOT", "SystemDrive", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PATHEXT", "COMSPEC", "WINDIR", "HOME")
_TEST_KEYS = ("BIYORI_ALLOW_LIVE",)       # 拒否の確認だけ(# gate-test の印)。それ以外は子プロセスに渡さない


def child_env(extra=None):
    """子プロセスの環境(明示して渡す。既存の環境を丸ごと引き継がない)。BIYORI_UNDER_TEST=1 = --live は常に拒否。
    PYTHONPATH に tests/nonet_child を入れて、子プロセスもソケット禁止にする。"""
    e = {k: os.environ[k] for k in _PASS_KEYS if k in os.environ}
    e.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", BIYORI_UNDER_TEST="1", PYTHONPATH=str(ROOT / "tests" / "nonet_child"))
    if os.environ.get("IKIMONOBIYORI_DATA_DIR"):                 # 段階37: 子プロセスも一時フォルダに書く(利用者の置き場所に触れない)
        e["IKIMONOBIYORI_DATA_DIR"] = os.environ["IKIMONOBIYORI_DATA_DIR"]
    for k, v in (extra or {}).items():
        if k in _TEST_KEYS:
            e[k] = v
    return e


def run_child(cmd, env=None, **kw):
    """subprocess.run の代わり(テストから子プロセスを起動するのはここだけ)。"""
    return subprocess.run(cmd, env=child_env(env), **kw)


def run_child_env(cmd, extra_env, **kw):
    """run_child に、子プロセスへ渡す環境変数(IKIMONOBIYORI_DATA_DIR など、拒否の確認以外のもの)を足す。BIYORI_UNDER_TEST=1 は付いたまま。"""
    e = child_env()
    e.update(extra_env)
    return subprocess.run(cmd, env=e, **kw)


def write(path, doc):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
