"""PDF の本文の読み取りと発行物台帳(段階59 第6部)。通信しない(読む PDF は手元のファイルか、呼び出し側が取った本文)。

- 上から順に試して、読めた最初の方法を使う(a: web-fetch の本文 / b: Read ツール / c: pdfminer.six / d: PDF 未読)。どの方法で読めたかを台帳に残す。
- 縦書きが 1 文字ずつ改行される PDF は、1 文字の行の並びを連結して読む。
- 全文は保存しない。台帳に残すのはメタデータ・内容のハッシュ・読み取りの状況だけ(IKIMONOBIYORI_DATA_DIR の下)。
値は data/knowledge/policy.yaml。"""
import hashlib
import json
import re
from pathlib import Path

import yaml

from .paths import DATA_FILES_DIR, data_path

POLICY = DATA_FILES_DIR / "knowledge" / "policy.yaml"
JP = re.compile(r"[ぁ-んァ-ヶ一-龠]")


def policy():
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


def join_vertical(text):
    """1 行 1 文字の並びを連結する(縦書きの PDF)。ほかの行はそのまま。"""
    mn = policy()["pdf"]["vertical_min_run"]
    out, run = [], []

    def flush():
        if len(run) >= mn:
            out.append("".join(run))
        else:
            out.extend(run)
        run.clear()
    for line in (text or "").splitlines():
        s = line.strip()
        if len(s) == 1:
            run.append(s)
        elif not s and run:
            continue
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def assess(text):
    """読み取りの状況。読めた / 一部 / 画像のみ(日本語の文字がほとんどない)/ 読めない(本文なし)。"""
    c = policy()["pdf"]
    t = text or ""
    jp = len(JP.findall(t))
    if not t.strip():
        return "読めない"
    if jp < c["image_only_max_jp"]:
        return "画像のみ"
    return "読めた" if jp >= c["ok_min_jp"] else "一部"


def extract_with_pdfminer(path, max_pages=None):
    """方法 c。→ 本文(連結済み)。ライブラリがなければ ImportError。保存しない。"""
    from pdfminer.high_level import extract_text
    mx = max_pages or policy()["pdf"]["max_pages"]
    return join_vertical(extract_text(str(path), maxpages=mx))


def read_with_methods(methods):
    """methods: [(名前, 関数)]。上から順に試し、読めた最初の方法の結果。→ {"method", "status", "text"}。どれも読めなければ method=d・status=PDF 未読。"""
    last = None
    for name, fn in methods:
        try:
            text = fn()
        except Exception as ex:                    # 取得の失敗・ライブラリの失敗は次の方法へ(回避しない)
            last = str(ex)[:120]
            continue
        st = assess(text)
        if st in ("読めた", "一部"):
            return {"method": name, "status": st, "text": text}
        last = st
    return {"method": "d", "status": policy()["pdf"]["unread_label"], "text": None, "reason": last}


def ledger_path(env=None):
    return data_path(policy()["publications_file"], env)


def record_publication(entry, text=None, env=None, read_method=None, status=None):
    """発行物台帳に 1 件足す(施設・題・号・発行年月・URL・形式・取得日・読み取りの状況・ハッシュ)。本文は保存しない。"""
    p = ledger_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {k: entry.get(k) for k in ("facility", "title", "issue", "published", "url", "format", "taken_on", "pages_used")}
    row["status"] = status or (assess(text) if text is not None else policy()["pdf"]["unread_label"])
    row["method"] = read_method
    row["hash"] = hashlib.sha256((text or "").encode("utf-8")).hexdigest() if text else None
    with p.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_publications(env=None):
    p = Path(ledger_path(env))
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def latest_issue(rows):
    """最新号(発行年月の新しい順。年の分からない号は最新にしない)。"""
    dated = [r for r in rows if r.get("published") and re.match(r"\d{4}", str(r["published"]))]
    return max(dated, key=lambda r: str(r["published"])) if dated else None
