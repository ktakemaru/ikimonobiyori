"""前シーズンの情報の判定(段階50)。通信しない・書き込まない。
東京都公園協会の紅葉情報は、シーズンが終わると「最終情報更新日：令和7年12月18日」の最終版のまま残る。
その日付が今シーズン(方針 season_check.season_start_month 以降の、直近のその月の1日以降)でなければ、今年の現況として使わない。"""
import re
from datetime import date

from .sources import load_policy, val

DATE_RE = re.compile(r"最終情報更新日\s*[:：]\s*(令和|平成)\s*(元|\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日")
WESTERN_RE = re.compile(r"最終情報更新日\s*[:：]\s*(\d{4})\s*年\s*(\d+)\s*月\s*(\d+)\s*日")


def parse_update_date(text, policy=None):
    """ページの本文から「最終情報更新日」を読む。→ date か None(書かれていない・読めない・存在しない日付)。推測しない。"""
    policy = policy or load_policy()
    m = DATE_RE.search(text or "")
    try:
        if m:
            era, n, mo, d = m.groups()
            base = val(policy["season_check"]["era_base_year"][era])
            return date(base + (1 if n == "元" else int(n)), int(mo), int(d))
        m = WESTERN_RE.search(text or "")
        if m:
            return date(*map(int, m.groups()))
    except ValueError:
        return None
    return None


def season_start(today, policy=None):
    """今シーズンの始まり = today 以前でいちばん近い、方針の月の1日。"""
    policy = policy or load_policy()
    month = val(policy["season_check"]["season_start_month"])
    year = today.year if today.month >= month else today.year - 1
    return date(year, month, 1)


def season_status(update, today, policy=None):
    """→ {"update_date", "current": True/False/None, "label", "note"}。
    update が None(日付が読めない)→ current は None(今シーズンと言い切らない)。today より後の日付も None(読み違いの疑い)。"""
    policy = policy or load_policy()
    lab = policy["season_check"]["labels"]
    if update is None or update > today:
        return {"update_date": None if update is None else update.isoformat(), "current": None, "label": None, "note": None}
    cur = update >= season_start(today, policy)
    note = None if cur else lab["note"].format(date=f"{update.year}年{update.month}月{update.day}日")
    return {"update_date": update.isoformat(), "current": cur, "label": None if cur else lab["previous_season"], "note": note}


def is_previous_season(update, today, policy=None):
    return season_status(update, today, policy)["current"] is False


# ---- 段階53: 日付と曜日の整合性（前年以前の情報を見分ける） ----
WEEKDAY_RES = (re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*[（(]\s*([月火水木金土日])"),
               re.compile(r"(\d{1,2})月\s*(\d{1,2})日\s*[（(]\s*([月火水木金土日])"))


def weekday_check(text, year, policy=None):
    """「10/25(土)」「11月15日（土曜日）」のように日付と曜日が書かれている箇所が、year の暦と合うかを確かめる。
    → {"checked": 件数, "mismatches": [原文の断片]}。曜日の書かれた日付がなければ checked は 0（判定しない）。存在しない日付は不一致にする。"""
    policy = policy or load_policy()
    names = val(policy["season_check"]["weekday_names"])
    checked, bad = 0, []
    for rx in WEEKDAY_RES:
        for m in rx.finditer(text or ""):
            mo, d, w = int(m.group(1)), int(m.group(2)), m.group(3)
            checked += 1
            try:
                ok = names[date(year, mo, d).weekday()] == w
            except ValueError:
                ok = False
            if not ok:
                bad.append(m.group(0))
    return {"checked": checked, "mismatches": bad}


def previous_year_by_weekday(text, today, policy=None):
    """今シーズンの暦と曜日が合わなければ前年以前の情報（True）。すべて合えば False。曜日の書かれた日付がなければ None（判定しない）。
    見出しが「2026」でも本文・meta の日付が古いまま残るサイトを落とす。"""
    r = weekday_check(text, season_start(today, policy).year, policy)
    if not r["checked"]:
        return None
    return bool(r["mismatches"])
