"""公式の機械可読データ(山梨県の紅葉状況 CSV)のパーサー(段階57 第11部)。通信しない。取得はエージェントの道具で行い、読んだ本文をここへ渡す。

- ページの HTML が「現在、情報がありません」でも、CSV へのリンクがあれば CSV を優先する。CSV のファイル名は推測で作らず、ページのリンクを辿る。
- 状態の語は CSV に書かれた語をそのまま使う。日付は CSV の行にないので、ページの更新日を 1 つ付ける。
- 備考の【紅葉まつり】M/D～M/D は、まつりの型に分ける(例年の見頃に使わない)。形が想定と違えば ValueError で止める(推測で補わない)。"""
import csv
import io
import re
from datetime import date
from urllib.parse import urljoin

COLUMNS = ["エリア名", "市町村名", "スポット名", "URL", "見頃", "標高", "備考", "状況"]
_READING = re.compile(r"[\s　]+[ぁ-ん]+$")
_CAMERA = re.compile(r"[\s　]*[（(]ライブカメラ[）)]")
_FEST = re.compile(r"【([^】]+)】\s*(\d{1,2})/(\d{1,2})\s*[～〜~-]\s*(\d{1,2})/(\d{1,2})")


def find_csv_link(html, base_url):
    """ページの .csv へのリンク(最初の 1 本)。なければ None。"""
    m = re.search(r'href=["\']([^"\']+\.csv)["\']', html or "", re.IGNORECASE)
    return urljoin(base_url, m.group(1)) if m else None


def page_updated(html):
    """「更新日：2026年11月6日」→ ISO。なければ None。"""
    m = re.search(r"更新日[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", html or "")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat() if m else None


def clean_name(name):
    """スポット名の読み仮名・注記を外す(「日川渓谷竜門峡　りゅうもんきょう」→「日川渓谷竜門峡」)。"""
    n = _CAMERA.sub("", name or "").strip(" 　")
    return _READING.sub("", n).strip(" 　")


def parse(text):
    """CSV の本文 → 行の一覧。列が想定と違えば ValueError。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV が空です")
    head = [c.strip() for c in rows[0]]
    missing = [c for c in COLUMNS if c not in head]
    if missing:
        raise ValueError(f"CSV の列が想定と違います: {missing}")
    idx = {c: head.index(c) for c in COLUMNS}
    out = []
    for r in rows[1:]:
        cell = lambda c: r[idx[c]].strip() if idx[c] < len(r) else ""
        if not cell("スポット名"):
            continue
        m = re.match(r"^\s*(\d+)\s*[:：]\s*(.+)$", cell("状況"))
        out.append({"area": cell("エリア名"), "city": cell("市町村名"), "name": clean_name(cell("スポット名")), "url": cell("URL"), "typical": cell("見頃") or None,
                    "elevation_m": int(cell("標高").rstrip("m")) if re.fullmatch(r"\d+m", cell("標高")) else None, "note": cell("備考") or None,
                    "state": m.group(2).strip() if m else None, "state_code": int(m.group(1)) if m else None})
    return out


def festivals_of(row, year):
    """備考のまつり → [{name, start, end}](年つき)。"""
    out = []
    for m in _FEST.finditer(row.get("note") or ""):
        out.append({"name": f"{row['name']} {m.group(1)}", "start": date(year, int(m.group(2)), int(m.group(3))).isoformat(),
                    "end": date(year, int(m.group(4)), int(m.group(5))).isoformat()})
    return out


def to_records(rows, *, csv_url, updated, subject="autumn_leaves", prefecture, publisher, label):
    """行 → 観察の記録の形(ask record)。状態のない行は除く。日付はページの更新日。例年の見頃は県の目安として typical に入れる。"""
    d = date.fromisoformat(updated)
    out = []
    for r in rows:
        if not r["state"]:
            continue
        rec = {"subject": subject, "name": r["name"], "city": r["city"], "prefecture": prefecture, "area": r["area"], "state": r["state"], "state_date": updated,
               "state_date_text": label.format(md=f"{d.month}/{d.day}"), "url": csv_url, "publisher": publisher, "source_class": "official"}
        if r["typical"]:
            rec["typical"] = r["typical"]
        fest = festivals_of(r, d.year)
        if fest:
            rec["event"] = fest[0]
        out.append(rec)
    return out
