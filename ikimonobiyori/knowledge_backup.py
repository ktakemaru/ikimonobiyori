"""段階60 第7部: 知識カードのバックアップ(ask knowledge backup)。通信しない(push はしない。本人が行う)。

データ置き場の knowledge フォルダが git のリポジトリ(非公開の ikimonobiyori-knowledge)のとき、
許可したファイル(cards.jsonl・publications.jsonl など。.gitignore の許可の一覧にあるものだけ)の変更を add して commit する。
安全装置: リポジトリがなければ何もしない(作らない)/リモートが想定外なら何もしない/許可外・絶対パスやトークンを含むファイルは add しない。
git は引数配列で呼ぶ(シェルを介さない)。テストでは run を差し替える。値は data/knowledge/policy.yaml の backup。
"""
import re
import subprocess
from datetime import date
from pathlib import Path

from . import pdf_text as PT
from .paths import data_path


def cfg():
    return PT.policy()["backup"]


def _git(run, repo, *args):
    return run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


def _whitelist(repo):
    """.gitignore の許可の一覧(! で始まる行)。"""
    p = Path(repo) / ".gitignore"
    if not p.exists():
        return set()
    return {ln.strip()[1:].strip("/") for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("!")}


def backup(env=None, run=subprocess.run, today=None):
    """戻り値 (終了コード, 表示の行の一覧)。0 = commit した・変更なし / 2 = 設定がない・リモートが想定外。"""
    c = cfg()
    msg = c["messages"]
    repo = Path(data_path(c["dir"], env))
    if not (repo / ".git").exists():
        return 2, [msg["no_repo"]]
    remotes = [ln.split()[1] for ln in (_git(run, repo, "remote", "-v").stdout or "").splitlines() if len(ln.split()) >= 2]
    bad = [r for r in remotes if not re.match(c["allowed_remote_re"], r)]
    if not remotes or bad:
        return 2, [msg["bad_remote"].format(remote=", ".join(bad or ["(なし)"]))]
    allowed = set(c["allowed_files"]) & _whitelist(repo)
    rx = re.compile(c["forbidden_content_re"])
    files, skipped = [], []
    for name in sorted(allowed):
        p = repo / name
        if not p.exists():
            continue
        if rx.search(p.read_text(encoding="utf-8", errors="replace")):
            skipped.append(name)
            continue
        files.append(name)
    lines = [msg["skipped"].format(files="・".join(skipped))] if skipped else []
    if files:
        _git(run, repo, "add", "--", *files)
    if _git(run, repo, "diff", "--cached", "--quiet").returncode == 0:
        return 0, lines + [msg["no_change"]]
    day = (today or date.today()).isoformat()
    _git(run, repo, "commit", "-m", c["commit_message"].format(date=day), "--", *files)
    return 0, lines + [msg["done"]]
